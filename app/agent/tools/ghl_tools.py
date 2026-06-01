"""Claude tool definitions + executors for GHL operations."""
import json
import logging
from app.integrations import ghl

logger = logging.getLogger(__name__)


def _dry_run_response(action: str, **details) -> str:
    """Standard dry-run response that the agent will see as a tool result."""
    return json.dumps({
        "dry_run": True,
        "would_have": action,
        "details": details,
        "note": "DRY RUN MODE: this action was NOT actually executed in GHL. Set GHL_WRITE_MODE=live to enable real writes.",
    })


# ============================================================
# TOOL DEFINITIONS (sent to Claude)
# ============================================================
GHL_TOOL_DEFINITIONS = [
    # ---------- READ ----------
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
                "query": {"type": "string", "description": "Name, email, or phone number. Partial matches work."},
                "limit": {"type": "integer", "description": "Max results. Default 10.", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "ghl_read_conversations",
        "description": (
            "Read recent conversations (SMS, email, etc.) from GoHighLevel. "
            "If contact_id is provided, returns only that contact's conversations. "
            "Set include_messages=true to also fetch the actual message bodies inside each conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "Optional. GHL contact ID."},
                "limit": {"type": "integer", "description": "Max conversations. Default 10.", "default": 10},
                "include_messages": {"type": "boolean", "description": "Also fetch message bodies.", "default": False},
                "messages_per_conversation": {"type": "integer", "default": 10},
            },
        },
    },
    # ---------- WRITE ----------
    {
        "name": "ghl_send_sms",
        "description": (
            "Send an SMS to a GoHighLevel contact. Requires the contact's GHL contact_id (use ghl_find_contact first). "
            "IMPORTANT: This is a real action that sends a real message to a real phone. "
            "Always confirm the recipient and message body with the user before calling this tool, "
            "unless the user has been explicit (e.g. 'send it now', 'don't ask me')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "GHL contact ID of recipient."},
                "message": {"type": "string", "description": "SMS body text."},
            },
            "required": ["contact_id", "message"],
        },
    },
    {
        "name": "ghl_create_contact",
        "description": (
            "Create a new contact in GoHighLevel. At minimum, provide email OR phone. "
            "Confirm with the user before creating, unless they've been explicit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string", "description": "E.164 format preferred, e.g. +639171234567"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags."},
            },
        },
    },
    {
        "name": "ghl_update_contact",
        "description": (
            "Update fields on an existing GoHighLevel contact (find them first with ghl_find_contact to get the ID). "
            "Only include the fields you want to change. Use tags_to_add to add tags (it appends, does not replace)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "tags_to_add": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["contact_id"],
        },
    },
    {
        "name": "ghl_add_note",
        "description": (
            "Add a note to a GoHighLevel contact's record. Useful for logging what the agent did, "
            "summarizing a conversation, or recording context for the human team."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "body": {"type": "string", "description": "Note text."},
            },
            "required": ["contact_id", "body"],
        },
    },
    {
        "name": "ghl_manage_pipeline",
        "description": (
            "Multi-purpose pipeline tool. Three actions:\n"
            "  - 'list_pipelines': returns all pipelines and their stages (use this first to discover IDs).\n"
            "  - 'find_opportunities': search opportunities, optionally filtered by pipeline_id or contact_id.\n"
            "  - 'move_opportunity': move an opportunity to a different stage. "
            "Requires opportunity_id, pipeline_id, and pipeline_stage_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_pipelines", "find_opportunities", "move_opportunity"],
                },
                "pipeline_id": {"type": "string"},
                "contact_id": {"type": "string"},
                "opportunity_id": {"type": "string"},
                "pipeline_stage_id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["action"],
        },
    },
]


# ============================================================
# READ EXECUTORS
# ============================================================
async def execute_ghl_find_contact(query: str, limit: int = 10) -> str:
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
    try:
        convos = await ghl.search_conversations(contact_id=contact_id, limit=limit)
        if not convos:
            return json.dumps({"conversations": [], "message": "No conversations found."})

        if include_messages:
            for c in convos:
                try:
                    msgs = await ghl.get_conversation_messages(c["id"], limit=messages_per_conversation)
                    c["messages"] = msgs
                except ghl.GHLAPIError as e:
                    c["messages_error"] = str(e)

        return json.dumps({"conversations": convos, "count": len(convos)})
    except ghl.GHLAPIError as e:
        return json.dumps({"error": str(e)})


# ============================================================
# WRITE EXECUTORS (with dry-run support)
# ============================================================
async def execute_ghl_send_sms(contact_id: str, message: str) -> str:
    if not ghl.is_live_mode():
        return _dry_run_response(
            "send an SMS",
            contact_id=contact_id,
            message=message,
        )
    try:
        result = await ghl.send_sms(contact_id=contact_id, message=message)
        return json.dumps({"success": True, "result": result})
    except ghl.GHLAPIError as e:
        return json.dumps({"error": str(e)})


async def execute_ghl_create_contact(
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    tags: list[str] | None = None,
) -> str:
    if not email and not phone:
        return json.dumps({"error": "Need at least email or phone to create a contact."})

    if not ghl.is_live_mode():
        return _dry_run_response(
            "create a new contact",
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            tags=tags,
        )
    try:
        contact = await ghl.create_contact(
            first_name=first_name, last_name=last_name,
            email=email, phone=phone, tags=tags,
        )
        return json.dumps({"success": True, "contact": contact})
    except ghl.GHLAPIError as e:
        return json.dumps({"error": str(e)})


async def execute_ghl_update_contact(
    contact_id: str,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    tags_to_add: list[str] | None = None,
) -> str:
    changes = {
        k: v for k, v in {
            "first_name": first_name, "last_name": last_name,
            "email": email, "phone": phone, "tags_to_add": tags_to_add,
        }.items() if v is not None
    }
    if not changes:
        return json.dumps({"error": "No fields to update."})

    if not ghl.is_live_mode():
        return _dry_run_response(
            "update a contact",
            contact_id=contact_id,
            changes=changes,
        )
    try:
        contact = await ghl.update_contact(
            contact_id=contact_id,
            first_name=first_name, last_name=last_name,
            email=email, phone=phone, tags_to_add=tags_to_add,
        )
        return json.dumps({"success": True, "contact": contact})
    except ghl.GHLAPIError as e:
        return json.dumps({"error": str(e)})


async def execute_ghl_add_note(contact_id: str, body: str) -> str:
    if not ghl.is_live_mode():
        return _dry_run_response(
            "add a note to a contact",
            contact_id=contact_id,
            body=body,
        )
    try:
        note = await ghl.add_contact_note(contact_id=contact_id, body=body)
        return json.dumps({"success": True, "note": note})
    except ghl.GHLAPIError as e:
        return json.dumps({"error": str(e)})


async def execute_ghl_manage_pipeline(
    action: str,
    pipeline_id: str | None = None,
    contact_id: str | None = None,
    opportunity_id: str | None = None,
    pipeline_stage_id: str | None = None,
    limit: int = 20,
) -> str:
    try:
        if action == "list_pipelines":
            pipelines = await ghl.list_pipelines()
            return json.dumps({"pipelines": pipelines, "count": len(pipelines)})

        if action == "find_opportunities":
            opps = await ghl.search_opportunities(
                pipeline_id=pipeline_id, contact_id=contact_id, limit=limit,
            )
            return json.dumps({"opportunities": opps, "count": len(opps)})

        if action == "move_opportunity":
            if not (opportunity_id and pipeline_id and pipeline_stage_id):
                return json.dumps({
                    "error": "move_opportunity requires opportunity_id, pipeline_id, and pipeline_stage_id."
                })
            if not ghl.is_live_mode():
                return _dry_run_response(
                    "move an opportunity to a new stage",
                    opportunity_id=opportunity_id,
                    pipeline_id=pipeline_id,
                    pipeline_stage_id=pipeline_stage_id,
                )
            result = await ghl.update_opportunity_stage(
                opportunity_id=opportunity_id,
                pipeline_id=pipeline_id,
                pipeline_stage_id=pipeline_stage_id,
            )
            return json.dumps({"success": True, "opportunity": result})

        return json.dumps({"error": f"Unknown action: {action}"})
    except ghl.GHLAPIError as e:
        return json.dumps({"error": str(e)})


# ============================================================
# DISPATCH MAP
# ============================================================
GHL_TOOL_EXECUTORS = {
    "ghl_find_contact": execute_ghl_find_contact,
    "ghl_read_conversations": execute_ghl_read_conversations,
    "ghl_send_sms": execute_ghl_send_sms,
    "ghl_create_contact": execute_ghl_create_contact,
    "ghl_update_contact": execute_ghl_update_contact,
    "ghl_add_note": execute_ghl_add_note,
    "ghl_manage_pipeline": execute_ghl_manage_pipeline,
}