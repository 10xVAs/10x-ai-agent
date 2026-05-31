"""Supabase client + helpers."""
from datetime import datetime, timezone
from supabase import create_client, Client
from app.config import settings

supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
)


# ============================================================
# USERS
# ============================================================
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


# ============================================================
# CONVERSATIONS
# ============================================================
def get_or_create_active_conversation(user_id: str) -> dict:
    """Return the user's most recent non-archived conversation, or create one."""
    result = (
        supabase.table("conversations")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_archived", False)
        .order("last_message_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]

    # Create a new one
    new = (
        supabase.table("conversations")
        .insert({"user_id": user_id})
        .execute()
    )
    return new.data[0]


def start_new_conversation(user_id: str) -> dict:
    """Archive the current active conversation and create a fresh one."""
    supabase.table("conversations").update({"is_archived": True}).eq(
        "user_id", user_id
    ).eq("is_archived", False).execute()
    new = supabase.table("conversations").insert({"user_id": user_id}).execute()
    return new.data[0]


def touch_conversation(conversation_id: str) -> None:
    """Update last_message_at on a conversation."""
    supabase.table("conversations").update(
        {"last_message_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", conversation_id).execute()


# ============================================================
# MESSAGES
# ============================================================
def save_message(
    conversation_id: str,
    role: str,
    content: list,
    source: str | None = None,
) -> dict:
    """Save a message and bump the conversation's last_message_at."""
    result = (
        supabase.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "source": source,
            }
        )
        .execute()
    )
    touch_conversation(conversation_id)
    return result.data[0]


def get_conversation_messages(conversation_id: str) -> list[dict]:
    """Return all messages in a conversation, oldest first."""
    result = (
        supabase.table("messages")
        .select("role, content")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


# ============================================================
# USAGE LOG
# ============================================================
def log_usage(
    user_id: str,
    conversation_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int,
    cache_read_input_tokens: int,
    estimated_cost_usd: float,
) -> None:
    """Insert a usage_log row."""
    supabase.table("usage_log").insert(
        {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
            "estimated_cost_usd": estimated_cost_usd,
        }
    ).execute()


def sum_usage(user_id: str) -> dict:
    """Return totals across all usage_log rows for this user."""
    result = (
        supabase.table("usage_log")
        .select("input_tokens, output_tokens, estimated_cost_usd")
        .eq("user_id", user_id)
        .execute()
    )
    rows = result.data
    return {
        "turns": len(rows),
        "total_input_tokens": sum(r["input_tokens"] for r in rows),
        "total_output_tokens": sum(r["output_tokens"] for r in rows),
        "total_cost_usd": sum(float(r["estimated_cost_usd"] or 0) for r in rows),
    }