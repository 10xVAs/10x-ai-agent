"""Claude tool definitions + executors for GHL operations."""
import json
from app.integrations import ghl

# ============================================================
# TOOL DEFINITIONS (sent to Claude)
# ============================================================
GHL_TOOL_DEFINITIONS = [
    {
        "name": "ghl_find_contact",
        "description": (
            "Search for contacts in GoHighLevel by name, email, or phone number. "
            "Returns a list of matching contacts with their ID, name, email, phone, and tags. "
            "Use this whenever the user references someone by name and you need to look up their details "
            "or get their contact ID for other operations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Name, email, or phone number to search for. Partial matches work.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return. Default 10.",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "ghl_read_conversations",
        "description": (
            "Read recent conversations (SMS, email, etc.) from GoHighLevel. "
            "If contact_id is provided, returns only that contact's conversations. "
            "Otherwise returns the most recent conversations across all contacts. "
            "To read the actual messages inside a conversation, set include_messages=true."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {
                    "type": "string",
                    "description": "Optional. GHL contact ID to filter conversations to one person.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max conversations to return. Default 10.",
                    "default": 10,
                },
                "include_messages": {
                    "type": "boolean",
                    "description": "If true, also fetch the actual messages inside each conversation. Default false.",
                    "default": False,
                },
                "messages_per_conversation": {
                    "type": "integer",
                    "description": "If include_messages is true, how many messages per conversation. Default 10.",
                    "default": 10,
                },
            },
        },
    },
]


# ============================================================
# TOOL EXECUTORS
# ============================================================
async def execute_ghl_find_contact(query: str, limit: int = 10) -> str:
    """Execute the ghl_find_contact tool. Returns a JSON string for Claude."""
    try:
        contacts = await ghl.search_contacts(query=query, limit=limit)
        if not contacts:
            return json.dumps({"contacts": [], "message": "No contacts found matching that query."})
        return json.dumps({"contacts": contacts, "count": len(contacts)})
    except ghl.GHLAPIError as e:
        return json.dumps({"error": str(e)})


async def execute_ghl_read_conversations(
    contact_id: str | None = None,
    limit: int = 10,
    include_messages: bool = False,
    messages_per_conversation: int = 10,
) -> str:
    """Execute the ghl_read_conversations tool. Returns a JSON string for Claude."""
    try:
        convos = await ghl.search_conversations(contact_id=contact_id, limit=limit)
        if not convos:
            return json.dumps({"conversations": [], "message": "No conversations found."})

        if include_messages:
            for c in convos:
                try:
                    msgs = await ghl.get_conversation_messages(
                        c["id"], limit=messages_per_conversation
                    )
                    c["messages"] = msgs
                except ghl.GHLAPIError as e:
                    c["messages_error"] = str(e)

        return json.dumps({"conversations": convos, "count": len(convos)})
    except ghl.GHLAPIError as e:
        return json.dumps({"error": str(e)})


# ============================================================
# DISPATCH MAP
# ============================================================
GHL_TOOL_EXECUTORS = {
    "ghl_find_contact": execute_ghl_find_contact,
    "ghl_read_conversations": execute_ghl_read_conversations,
}