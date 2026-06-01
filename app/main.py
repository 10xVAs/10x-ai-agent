"""FastAPI entry point for the 10x AI Agent backend."""
import logging
from fastapi import FastAPI, Request, HTTPException, Header
from app.config import settings
from app.telegram_handler import handle_update

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

app = FastAPI(title="10x AI Agent", version="0.1.0")


@app.get("/")
async def root():
    return {"name": "10x AI Agent", "version": "0.1.0", "status": "ok"}


@app.get("/health")
async def health():
    """Health check endpoint for Railway."""
    return {"status": "healthy"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """Receive Telegram updates via webhook."""
    # Verify webhook secret to prevent spoofed requests
    if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    update = await request.json()
    logger.info(f"Received update: {update.get('update_id')}")

    try:
        await handle_update(update)
    except Exception as e:
        logger.exception(f"Error handling update: {e}")

    # Always return 200 to Telegram so it doesn't retry
    return {"ok": True}
# ============================================================
# Google OAuth callback
# ============================================================
from fastapi.responses import HTMLResponse
from app.integrations.google_oauth import exchange_code_for_tokens, save_tokens


@app.get("/auth/google/callback", response_class=HTMLResponse)
async def google_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """Handle the OAuth redirect from Google."""
    if error:
        return HTMLResponse(f"<h1>OAuth error</h1><p>{error}</p>", status_code=400)
    if not code or not state:
        return HTMLResponse("<h1>Missing code or state</h1>", status_code=400)

    try:
        creds = exchange_code_for_tokens(code)
        save_tokens(user_id=state, creds=creds)
        return HTMLResponse(
            "<h1>✓ Google connected</h1>"
            "<p>You can close this tab and return to Telegram.</p>"
        )
    except Exception as e:
        logger.exception(f"OAuth callback failed: {e}")
        return HTMLResponse(f"<h1>OAuth failed</h1><p>{e}</p>", status_code=500)