"""Google OAuth flow + token management.

Handles the multi-step OAuth dance:
1. Build an authorization URL the user visits in their browser.
2. Receive the callback with an authorization code.
3. Exchange the code for access + refresh tokens.
4. Persist tokens in Supabase.
5. Refresh expired access tokens automatically.
"""
import logging
from datetime import datetime, timedelta, timezone
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from app.config import settings
from app.db import supabase

logger = logging.getLogger(__name__)

# Scopes the agent needs. If we add scopes later, the user must re-authorize.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]


def _client_config() -> dict:
    """Build the OAuth client config from env vars."""
    return {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_redirect_uri()],
        }
    }


def _redirect_uri() -> str:
    """Build the redirect URI based on the current environment."""
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/auth/google/callback"


def build_authorization_url(user_id: str) -> str:
    """Return a URL the user can visit to authorize the agent.

    user_id is encoded in `state` so the callback knows which user authorized.
    """
    flow = Flow.from_client_config(
        _client_config(),
        scopes=GOOGLE_SCOPES,
        redirect_uri=_redirect_uri(),
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",       # request a refresh token
        include_granted_scopes="true",
        prompt="consent",            # force consent so we always get refresh_token
        state=user_id,
    )
    return auth_url


def exchange_code_for_tokens(code: str) -> Credentials:
    """Exchange an authorization code (from the callback) for tokens."""
    flow = Flow.from_client_config(
        _client_config(),
        scopes=GOOGLE_SCOPES,
        redirect_uri=_redirect_uri(),
    )
    flow.fetch_token(code=code)
    return flow.credentials


def save_tokens(user_id: str, creds: Credentials) -> None:
    """Persist tokens to Supabase. Upserts: one row per user."""
    expiry = creds.expiry
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    payload = {
        "user_id": user_id,
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_expiry": expiry.isoformat() if expiry else None,
        "scopes": creds.scopes or GOOGLE_SCOPES,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Upsert by user_id (which is UNIQUE in the table)
    supabase.table("google_oauth_tokens").upsert(
        payload, on_conflict="user_id"
    ).execute()
    logger.info(f"Saved Google tokens for user {user_id}")


def load_credentials(user_id: str) -> Credentials | None:
    """Load saved tokens for a user. Returns None if not connected."""
    result = (
        supabase.table("google_oauth_tokens")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None

    row = result.data[0]
    expiry = None
    if row.get("token_expiry"):
        expiry = datetime.fromisoformat(row["token_expiry"].replace("Z", "+00:00"))
        # google-auth library wants naive UTC datetime
        if expiry.tzinfo is not None:
            expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)

    creds = Credentials(
        token=row["access_token"],
        refresh_token=row["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=row["scopes"],
        expiry=expiry,
    )

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_tokens(user_id, creds)
            logger.info(f"Refreshed Google access token for user {user_id}")
        except Exception as e:
            logger.exception(f"Token refresh failed for user {user_id}: {e}")
            return None

    return creds


def is_connected(user_id: str) -> bool:
    """True if we have working Google tokens for this user."""
    creds = load_credentials(user_id)
    return creds is not None and not creds.expired