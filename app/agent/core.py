"""Core Claude agent loop. Phase 3 Pass 1: with GHL read-only tools."""
import logging
import json
from anthropic import Anthropic
from app.config import settings
from app.agent.prompts import get_system_prompt
from app.agent.tools.ghl_tools import GHL_TOOL_DEFINITIONS, GHL_TOOL_EXECUTORS
from app.agent.tools.gmail_tools import GMAIL_TOOL_DEFINITIONS, GMAIL_TOOL_EXECUTORS
from app.agent.tools.gcal_tools import GCAL_TOOL_DEFINITIONS, GCAL_TOOL_EXECUTORS
from app.agent.tools.gsheets_tools import GSHEETS_TOOL_DEFINITIONS, GSHEETS_TOOL_EXECUTORS
from app.db import (
    get_or_create_active_conversation,
    save_message,
    get_conversation_messages,
    log_usage,
    start_new_conversation,
    sum_usage,
    log_tool_call,
)

logger = logging.getLogger(__name__)

client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

PRICING = {
    "input": 3.00,
    "output": 15.00,
    "cache_write": 3.75,
    "cache_read": 0.30,
}

ALL_TOOL_DEFINITIONS = (
    GHL_TOOL_DEFINITIONS
    + GMAIL_TOOL_DEFINITIONS
    + GCAL_TOOL_DEFINITIONS
    + GSHEETS_TOOL_DEFINITIONS
)
ALL_TOOL_EXECUTORS = {
    **GHL_TOOL_EXECUTORS,
    **GMAIL_TOOL_EXECUTORS,
    **GCAL_TOOL_EXECUTORS,
    **GSHEETS_TOOL_EXECUTORS,
}

MAX_AGENT_ITERATIONS = 8


def estimate_cost(usage) -> float:
    input_cost = (usage.input_tokens / 1_000_000) * PRICING["input"]
    output_cost = (usage.output_tokens / 1_000_000) * PRICING["output"]
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write_cost = (cache_write / 1_000_000) * PRICING["cache_write"]
    cache_read_cost = (cache_read / 1_000_000) * PRICING["cache_read"]
    return input_cost + output_cost + cache_write_cost + cache_read_cost


# Tools that require the current user_id injected automatically
USER_SCOPED_TOOLS = {
    "gmail_search_read",
    "gmail_draft_or_send",
    "gcal_manage_events",
    "gsheets_read_write",
}


async def _execute_tool(tool_name: str, tool_input: dict, user_id: str) -> str:
    executor = ALL_TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        if tool_name in USER_SCOPED_TOOLS:
            return await executor(user_id=user_id, **tool_input)
        return await executor(**tool_input)
    except Exception as e:
        logger.exception(f"Tool {tool_name} failed: {e}")
        return json.dumps({"error": f"Tool execution failed: {e}"})


async def chat(user_id: str, user_message: str, source: str = "telegram_bot") -> str:
    """Run one full conversational turn, including any tool use loops."""
    conversation = get_or_create_active_conversation(user_id)
    conversation_id = conversation["id"]

    save_message(
        conversation_id=conversation_id,
        role="user",
        content=[{"type": "text", "text": user_message}],
        source=source,
    )

    history = get_conversation_messages(conversation_id)
    claude_messages = [{"role": m["role"], "content": m["content"]} for m in history]

    final_text = ""
    for iteration in range(MAX_AGENT_ITERATIONS):
        logger.info(
            f"Agent iteration {iteration + 1}, {len(claude_messages)} messages, "
            f"{len(ALL_TOOL_DEFINITIONS)} tools available: "
            f"{[t['name'] for t in ALL_TOOL_DEFINITIONS]}"
        )
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=2048,
            system=get_system_prompt(),
            tools=ALL_TOOL_DEFINITIONS,
            messages=claude_messages,
        )

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
            f"Iter cost ${cost:.5f} | in={response.usage.input_tokens} "
            f"out={response.usage.output_tokens} | stop={response.stop_reason}"
        )

        assistant_content = [block.model_dump() for block in response.content]
        assistant_db_msg = save_message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
            source=source,
        )
        claude_messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason != "tool_use":
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info(f"Tool call: {block.name} with input {block.input}")
                result_str = await _execute_tool(block.name, block.input, user_id=user_id)
                logger.info(f"Tool result ({block.name}): {result_str[:200]}...")

                try:
                    parsed = json.loads(result_str)
                    status = "error" if "error" in parsed else "success"
                    error_msg = parsed.get("error") if status == "error" else None
                except json.JSONDecodeError:
                    status = "success"
                    error_msg = None
                log_tool_call(
                    message_id=assistant_db_msg["id"],
                    tool_name=block.name,
                    input=block.input,
                    output={"raw": result_str},
                    status=status,
                    error_message=error_msg,
                )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })
            elif block.type == "text" and block.text:
                final_text += block.text + "\n\n"

        save_message(
            conversation_id=conversation_id,
            role="user",
            content=tool_results,
            source=source,
        )
        claude_messages.append({"role": "user", "content": tool_results})
    else:
        final_text += "\n\n[Note: agent iteration limit reached]"

    return final_text.strip() or "(no response)"


def reset_conversation(user_id: str) -> None:
    start_new_conversation(user_id)


def get_usage_summary(user_id: str) -> dict:
    return sum_usage(user_id)