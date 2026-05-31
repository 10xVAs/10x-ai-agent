"""Receives Telegram webhook updates, sends replies."""
import httpx
from app.config import settings
from app.auth import is_authorized

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"


async def send_message(chat_id: int, text: str) -> None:
    """Send a plain-text message to a Telegram chat."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"{TELEGRAM_API_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )


async def handle_update(update: dict) -> None:
    """Process one Telegram update. Phase 1: echo authorized messages."""
    message = update.get("message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    from_user = message.get("from", {})
    telegram_user_id = from_user.get("id")
    text = message.get("text", "")

    # Authorization gate
    if not telegram_user_id or not is_authorized(telegram_user_id):
        await send_message(
            chat_id,
            "Sorry, this AI agent is in private pilot. Contact 10xVAs for access.",
        )
        return

    # Handle commands
    if text.startswith("/start"):
        await send_message(
            chat_id,
            "Hello! I'm the 10xVAs AI Agent (Phase 1: Echo Mode).\n\n"
            "Send me any message and I'll echo it back. "
            "Claude integration comes next.",
        )
        return

    if text.startswith("/ping"):
        await send_message(chat_id, "pong")
        return

    # Echo (Phase 1 only - replaced by Claude in Phase 2)
    if text:
        await send_message(chat_id, f"Echo: {text}")
    else:
        await send_message(chat_id, "I only handle text messages right now.")