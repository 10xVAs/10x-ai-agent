"""Claude tool definitions + executors for Google Calendar."""
import json
import logging
from app.integrations import gcal

logger = logging.getLogger(__name__)


GCAL_TOOL_DEFINITIONS = [
    {
        "name": "gcal_manage_events",
        "description": (
            "Multi-purpose Google Calendar tool. Actions:\n"
            "  - 'list': list events in a time range, optionally filtered by query text. "
            "Defaults to events from now onward. Use ISO 8601 for time_min/time_max.\n"
            "  - 'get': fetch one event by event_id (use 'list' first to find the ID).\n"
            "  - 'create': create an event. Required: summary, start, end. "
            "Use full ISO 8601 datetimes (e.g. '2026-06-05T14:00:00+08:00'). "
            "For all-day events, use bare YYYY-MM-DD date strings.\n"
            "  - 'update': patch an existing event. Provide event_id and only the fields to change.\n"
            "  - 'delete': delete an event. REQUIRES extra explicit user confirmation in the chat. "
            "Recoverable from Google Calendar trash for 30 days.\n\n"
            "ALWAYS confirm before create/update/delete unless the user has been explicit. "
            "For delete: explicitly ask 'Are you sure you want to delete [summary] on [date]?' and require a yes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "get", "create", "update", "delete"],
                },
                "event_id": {"type": "string"},
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "location": {"type": "string"},
                "start": {"type": "string", "description": "ISO 8601 datetime or YYYY-MM-DD for all-day."},
                "end": {"type": "string", "description": "ISO 8601 datetime or YYYY-MM-DD for all-day."},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For create: full attendee list. For update: use add_attendees instead.",
                },
                "add_attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For update only: emails to append to the existing attendee list.",
                },
                "time_min": {"type": "string", "description": "For list: ISO 8601 lower bound."},
                "time_max": {"type": "string", "description": "For list: ISO 8601 upper bound."},
                "query": {"type": "string", "description": "For list: free-text search across event fields."},
                "max_results": {"type": "integer", "default": 20},
                "timezone_name": {
                    "type": "string",
                    "description": "Optional IANA timezone (e.g. 'Asia/Manila'). Defaults to whatever the datetime offset implies.",
                },
            },
            "required": ["action"],
        },
    },
]


async def execute_gcal_manage_events(
    user_id: str,
    action: str,
    event_id: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    location: str | None = None,
    start: str | None = None,
    end: str | None = None,
    attendees: list[str] | None = None,
    add_attendees: list[str] | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
    query: str | None = None,
    max_results: int = 20,
    timezone_name: str | None = None,
) -> str:
    try:
        if action == "list":
            events = gcal.list_events(
                user_id=user_id,
                time_min=time_min,
                time_max=time_max,
                query=query,
                max_results=max_results,
            )
            return json.dumps({"events": events, "count": len(events)})

        if action == "get":
            if not event_id:
                return json.dumps({"error": "get requires event_id."})
            event = gcal.get_event(user_id=user_id, event_id=event_id)
            return json.dumps({"event": event})

        if action == "create":
            if not (summary and start and end):
                return json.dumps({"error": "create requires summary, start, and end."})
            event = gcal.create_event(
                user_id=user_id,
                summary=summary,
                start=start,
                end=end,
                description=description,
                location=location,
                attendees=attendees,
                timezone_name=timezone_name,
            )
            return json.dumps({"success": True, "action_taken": "created", "event": event})

        if action == "update":
            if not event_id:
                return json.dumps({"error": "update requires event_id."})
            event = gcal.update_event(
                user_id=user_id,
                event_id=event_id,
                summary=summary,
                start=start,
                end=end,
                description=description,
                location=location,
                add_attendees=add_attendees,
                timezone_name=timezone_name,
            )
            return json.dumps({"success": True, "action_taken": "updated", "event": event})

        if action == "delete":
            if not event_id:
                return json.dumps({"error": "delete requires event_id."})
            result = gcal.delete_event(user_id=user_id, event_id=event_id)
            return json.dumps({"success": True, "action_taken": "deleted", "result": result})

        return json.dumps({"error": f"Unknown action: {action}"})
    except gcal.GCalError as e:
        return json.dumps({"error": str(e)})


GCAL_TOOL_EXECUTORS = {
    "gcal_manage_events": execute_gcal_manage_events,
}