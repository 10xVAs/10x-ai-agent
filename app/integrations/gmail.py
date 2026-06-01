"""Gmail API wrapper."""
import base64
import logging
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app.config import settings
from app.integrations.google_oauth import load_credentials

logger = logging.getLogger(__name__)


class GmailError(Exception):
    pass


def _service(user_id: str):
    creds = load_credentials(user_id)
    if not creds:
        raise GmailError("Google account not connected. Use /connect_google in Telegram.")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def is_live_mode() -> bool:
    return settings.GMAIL_WRITE_MODE.lower() == "live"


def search_messages(user_id: str, query: str, max_results: int = 10) -> list[dict]:
    """Search Gmail with the same syntax as the search bar (from:, subject:, etc.)."""
    try:
        svc = _service(user_id)
        result = svc.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results,
        ).execute()
        messages = result.get("messages", [])
        out = []
        for m in messages:
            full = svc.users().messages().get(
                userId="me",
                id=m["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()
            out.append(_simplify_message(full))
        return out
    except HttpError as e:
        raise GmailError(f"Gmail API error: {e}")


def get_message_body(user_id: str, message_id: str) -> dict:
    """Fetch the full message body for one specific email."""
    try:
        svc = _service(user_id)
        full = svc.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        return {
            **_simplify_message(full),
            "body": _extract_body(full.get("payload", {})),
        }
    except HttpError as e:
        raise GmailError(f"Gmail API error: {e}")


def _simplify_message(msg: dict) -> dict:
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "snippet": msg.get("snippet"),
        "from": headers.get("From"),
        "to": headers.get("To"),
        "subject": headers.get("Subject"),
        "date": headers.get("Date"),
        "labels": msg.get("labelIds", []),
    }


def _extract_body(payload: dict) -> str:
    """Walk payload parts to find text body."""
    if "body" in payload and payload["body"].get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        nested = _extract_body(part)
        if nested:
            return nested
    return ""


def create_draft(user_id: str, to: str, subject: str, body: str) -> dict:
    """Create an email draft (NOT sent)."""
    try:
        svc = _service(user_id)
        message = _build_raw_message(to=to, subject=subject, body=body)
        result = svc.users().drafts().create(
            userId="me",
            body={"message": {"raw": message}},
        ).execute()
        return {
            "draft_id": result.get("id"),
            "message_id": result.get("message", {}).get("id"),
            "status": "draft_created",
        }
    except HttpError as e:
        raise GmailError(f"Gmail API error: {e}")


def send_message(user_id: str, to: str, subject: str, body: str) -> dict:
    """Send an email directly."""
    try:
        svc = _service(user_id)
        message = _build_raw_message(to=to, subject=subject, body=body)
        result = svc.users().messages().send(
            userId="me",
            body={"raw": message},
        ).execute()
        return {
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
            "status": "sent",
        }
    except HttpError as e:
        raise GmailError(f"Gmail API error: {e}")


def _build_raw_message(to: str, subject: str, body: str) -> str:
    msg = MIMEText(body)
    msg["To"] = to
    msg["Subject"] = subject
    raw_bytes = msg.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")