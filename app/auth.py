"""Authorization gate for v1 single-tenant."""
from app.config import settings
from app.db import get_user_by_telegram_id


def is_authorized(telegram_user_id: int) -> bool:
    """Check whether a Telegram user is allowed to use the bot."""
    if telegram_user_id != settings.AUTHORIZED_TELEGRAM_USER_ID:
        return False
    user = get_user_by_telegram_id(telegram_user_id)
    return bool(user and user.get("is_authorized"))