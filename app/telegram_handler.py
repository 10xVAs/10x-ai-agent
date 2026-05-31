"""Receives Telegram webhook updates, sends replies."""
import logging
import httpx
from app.config import settings
from app.auth import is_authorized
from app.db import get_user_by_telegram_id
from app.agent.core import chat, reset_conversation, get_usage_summary

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"


async def send_message(chat_id: int, text: str) -> None:
    """Send a plain-text message to a Telegram chat."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.post(
            f"{TELEGRAM_API_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )


async def send_typing(chat_id: int) -> None:
    """Show 'typing...' indicator while we think."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(
                f"{TELEGRAM_API_BASE}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
            )
        except Exception:
            pass  # Non-critical


async def handle_update(update: dict) -> None:
    """Process one Telegram update."""
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

    # Resolve internal user_id
    user = get_user_by_telegram_id(telegram_user_id)
    if not user:
        await send_message(chat_id, "User not found in database. Contact admin.")
        return
    user_id = user["id"]

    # Commands
    if text.startswith("/start"):
        await send_message(
            chat_id,
            "Hello! I'm the 10xVAs AI Agent.\n\n"
            "Just send me a message and I'll respond. I have memory across this conversation.\n\n"
            "Commands:\n"
            "/new — start a fresh conversation\n"
            "/usage — see token usage and cost so far",
        )
        return

    if text.startswith("/ping"):
        await send_message(chat_id, "pong")
        return

    if text.startswith("/new"):
        reset_conversation(user_id)
        await send_message(chat_id, "Started a fresh conversation. Memory cleared.")
        return

    if text.startswith("/usage"):
        s = get_usage_summary(user_id)
        await send_message(
            chat_id,
            f"📊 Usage summary\n\n"
            f"Turns: {s['turns']}\n"
            f"Input tokens: {s['total_input_tokens']:,}\n"
            f"Output tokens: {s['total_output_tokens']:,}\n"
            f"Estimated cost: ${s['total_cost_usd']:.4f}",
        )
        return

    if not text:
        await send_message(chat_id, "I only handle text messages right now.")
        return

    # Conversational message → Claude
    await send_typing(chat_id)
    try:
        reply = await chat(user_id=user_id, user_message=text)
        await send_message(chat_id, reply)
    except Exception as e:
        logger.exception(f"Agent error: {e}")
        await send_message(chat_id, f"Something went wrong: {e}")