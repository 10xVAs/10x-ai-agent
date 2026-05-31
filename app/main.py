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