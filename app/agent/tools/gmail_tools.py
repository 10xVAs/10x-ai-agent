"""Claude tool definitions + executors for Gmail."""
import json
import logging
from app.integrations import gmail

logger = logging.getLogger(__name__)


GMAIL_TOOL_DEFINITIONS = [
    {
        "name": "gmail_search_read",
        "description": (
            "Search Gmail using the same query syntax as the Gmail search bar "
            "(e.g., 'from:jane@example.com', 'subject:invoice', 'is:unread', 'newer_than:7d'). "
            "Returns a list of matching messages with sender, subject, date, and a snippet. "
            "Set include_body=true to also fetch the full body of each matched message "
            "(use sparingly — expensive on large result sets)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gmail search query (same syntax as the Gmail UI).",
                },
                "max_results": {"type": "integer", "default": 10},
                "include_body": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
    },
    {
        "name": "gmail_draft_or_send",
        "description": (
            "Create an email draft OR send an email. Default behavior is to create a draft "
            "(safer — user can review in Gmail before sending). Set send_now=true ONLY if the user "
            "has explicitly said to send it directly. ALWAYS confirm the recipient, subject, and body "
            "with the user before calling this tool, unless the user has been explicit "
            "(e.g. 'just send it', 'go ahead')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string"},
                "body": {"type": "string", "description": "Plain text body."},
                "send_now": {
                    "type": "boolean",
                    "description": "If true, send immediately. If false (default), create a draft.",
                    "default": False,
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
]


async def execute_gmail_search_read(
    user_id: str,
    query: str,
    max_results: int = 10,
    include_body: bool = False,
) -> str:
    try:
        messages = gmail.search_messages(user_id=user_id, query=query, max_results=max_results)
        if include_body:
            for m in messages:
                try:
                    full = gmail.get_message_body(user_id=user_id, message_id=m["id"])
                    m["body"] = full.get("body", "")
                except gmail.GmailError as e:
                    m["body_error"] = str(e)
        if not messages:
            return json.dumps({"messages": [], "message": "No emails matched."})
        return json.dumps({"messages": messages, "count": len(messages)})
    except gmail.GmailError as e:
        return json.dumps({"error": str(e)})


async def execute_gmail_draft_or_send(
    user_id: str,
    to: str,
    subject: str,
    body: str,
    send_now: bool = False,
) -> str:
    # Force draft if global write mode is "draft" — even if Claude asked to send
    if not gmail.is_live_mode() and send_now:
        result = gmail.create_draft(user_id=user_id, to=to, subject=subject, body=body)
        return json.dumps({
            "success": True,
            "action_taken": "draft_created",
            "note": (
                "GMAIL_WRITE_MODE is 'draft' globally, so I created a draft even though "
                "send_now was true. The user can send it from Gmail. Set GMAIL_WRITE_MODE=live "
                "to allow direct sending."
            ),
            "result": result,
        })

    try:
        if send_now:
            result = gmail.send_message(user_id=user_id, to=to, subject=subject, body=body)
            return json.dumps({"success": True, "action_taken": "sent", "result": result})
        else:
            result = gmail.create_draft(user_id=user_id, to=to, subject=subject, body=body)
            return json.dumps({"success": True, "action_taken": "draft_created", "result": result})
    except gmail.GmailError as e:
        return json.dumps({"error": str(e)})


GMAIL_TOOL_EXECUTORS = {
    "gmail_search_read": execute_gmail_search_read,
    "gmail_draft_or_send": execute_gmail_draft_or_send,
}