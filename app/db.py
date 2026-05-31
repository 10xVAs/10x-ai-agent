"""Supabase client + helpers."""
from supabase import create_client, Client
from app.config import settings

supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
)


def get_user_by_telegram_id(telegram_user_id: int) -> dict | None:
    """Look up a user by their Telegram numeric ID."""
    result = (
        supabase.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None