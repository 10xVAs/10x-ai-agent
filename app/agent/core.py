"""Core Claude agent loop. Phase 2: conversational only, no tools yet."""
import logging
from anthropic import Anthropic
from app.config import settings
from app.agent.prompts import SYSTEM_PROMPT
from app.db import (
    get_or_create_active_conversation,
    save_message,
    get_conversation_messages,
    log_usage,
    start_new_conversation,
)

logger = logging.getLogger(__name__)

client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# Sonnet 4.5 pricing as of late 2025 (USD per million tokens)
PRICING = {
    "input": 3.00,
    "output": 15.00,
    "cache_write": 3.75,
    "cache_read": 0.30,
}


def estimate_cost(usage) -> float:
    """Calculate the dollar cost of one API call."""
    input_cost = (usage.input_tokens / 1_000_000) * PRICING["input"]
    output_cost = (usage.output_tokens / 1_000_000) * PRICING["output"]
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write_cost = (cache_write / 1_000_000) * PRICING["cache_write"]
    cache_read_cost = (cache_read / 1_000_000) * PRICING["cache_read"]
    return input_cost + output_cost + cache_write_cost + cache_read_cost


async def chat(user_id: str, user_message: str, source: str = "telegram_bot") -> str:
    """Run one turn of conversation. Returns the assistant's reply text."""
    # Get or create active conversation
    conversation = get_or_create_active_conversation(user_id)
    conversation_id = conversation["id"]

    # Save user message
    save_message(
        conversation_id=conversation_id,
        role="user",
        content=[{"type": "text", "text": user_message}],
        source=source,
    )

    # Load full message history for this conversation, in Claude format
    history = get_conversation_messages(conversation_id)
    claude_messages = [{"role": m["role"], "content": m["content"]} for m in history]

    # Call Claude
    logger.info(f"Calling Claude with {len(claude_messages)} messages")
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=claude_messages,
    )

    # Extract text from response
    assistant_text = ""
    for block in response.content:
        if block.type == "text":
            assistant_text += block.text

    # Save assistant message
    save_message(
        conversation_id=conversation_id,
        role="assistant",
        content=[{"type": "text", "text": assistant_text}],
        source=source,
    )

    # Log token usage and cost
    cost = estimate_cost(response.usage)
    log_usage(
        user_id=user_id,
        conversation_id=conversation_id,
        model=settings.CLAUDE_MODEL,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_creation_input_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        estimated_cost_usd=cost,
    )
    logger.info(
        f"Turn cost: ${cost:.5f} | in={response.usage.input_tokens} out={response.usage.output_tokens}"
    )

    return assistant_text


def reset_conversation(user_id: str) -> None:
    """Archive the current conversation; the next message starts a new one."""
    start_new_conversation(user_id)


def get_usage_summary(user_id: str) -> dict:
    """Return total token usage and cost for this user."""
    from app.db import sum_usage
    return sum_usage(user_id)