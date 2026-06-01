"""Receives Telegram webhook updates, sends replies."""
import asyncio
import logging
import httpx
from app.config import settings
from app.auth import is_authorized
from app.db import get_user_by_telegram_id
from app.agent.core import chat, reset_conversation, get_usage_summary
from app.integrations.google_oauth import build_authorization_url, is_connected

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"


async def send_message(chat_id: int, text: str, markdown: bool = True) -> None:
    """Send a message. Tries Markdown first; falls back to plain text if Telegram rejects it."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        if markdown:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
            if resp.status_code == 200:
                return
            logger.warning(f"Telegram Markdown rejected: {resp.text[:200]}. Retrying as plain text.")
        await client.post(
            f"{TELEGRAM_API_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )


async def send_typing(chat_id: int) -> None:
    """Show 'typing...' indicator once."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(
                f"{TELEGRAM_API_BASE}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
            )
        except Exception:
            pass


async def _keep_typing(chat_id: int) -> None:
    """Background task: refresh typing indicator every 4 seconds until cancelled."""
    try:
        while True:
            await send_typing(chat_id)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def handle_update(update: dict) -> None:
    """Process one Telegram update."""
    message = update.get("message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    from_user = message.get("from", {})
    telegram_user_id = from_user.get("id")
    text = message.get("text", "")

    if not telegram_user_id or not is_authorized(telegram_user_id):
        await send_message(
            chat_id,
            "Sorry, this AI agent is in private pilot. Contact 10xVAs for access.",
        )
        return

    user = get_user_by_telegram_id(telegram_user_id)
    if not user:
        await send_message(chat_id, "User not found in database. Contact admin.")
        return
    user_id = user["id"]

    if text.startswith("/start"):
        await send_message(
            chat_id,
            "Hello! I'm the 10xVAs AI Agent.\n\n"
            "Just send me a message and I'll respond. I have memory across this conversation.\n\n"
            "Commands:\n"
            "/new — start a fresh conversation\n"
            "/usage — see token usage and cost so far\n"
            "/connect_google — connect Google Workspace\n"
            "/google_status — check Google connection status\n"
            "/disconnect_google — disconnect Google Workspace",
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

    if text.startswith("/connect_google"):
        if is_connected(user_id):
            await send_message(
                chat_id,
                "✓ Google is already connected. Use /disconnect_google first to reconnect.",
            )
            return
        url = build_authorization_url(user_id=user_id)
        await send_message(
            chat_id,
            "Connect Google Workspace:\n\n"
            f"{url}\n\n"
            "Open the link, sign in with info@10xvas.com, and approve. "
            "Come back here after you see the success page.",
            markdown=False,
        )
        return

    if text.startswith("/disconnect_google"):
        from app.db import supabase
        supabase.table("google_oauth_tokens").delete().eq("user_id", user_id).execute()
        await send_message(chat_id, "✓ Google disconnected. Use /connect_google to reconnect.")
        return

    if text.startswith("/google_status"):
        connected = is_connected(user_id)
        await send_message(
            chat_id,
            f"Google: {'✓ connected' if connected else '✗ not connected'}",
        )
        return

    if not text:
        await send_message(chat_id, "I only handle text messages right now.")
        return

    typing_task = asyncio.create_task(_keep_typing(chat_id))
    try:
        reply = await chat(user_id=user_id, user_message=text)
        typing_task.cancel()
        await send_typing(chat_id)
        await send_message(chat_id, reply)
    except Exception as e:
        logger.exception(f"Agent error: {e}")
        err_str = str(e).lower()
        if "rate_limit" in err_str or "429" in err_str:
            await send_message(
                chat_id,
                "⏳ I'm processing requests faster than my current API tier allows. "
                "Give me 30-60 seconds and try again.",
            )
        elif "overloaded" in err_str or "529" in err_str:
            await send_message(
                chat_id,
                "⚠️ Claude's servers are temporarily overloaded. Try again in a moment.",
            )
        else:
            await send_message(
                chat_id,
                "⚠️ Something went wrong on my end. Try again, or use /new to reset.",
            )
    finally:
        if not typing_task.done():
            typing_task.cancel()