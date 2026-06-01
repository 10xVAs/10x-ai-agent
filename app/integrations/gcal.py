"""Google Calendar API wrapper."""
import logging
from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app.integrations.google_oauth import load_credentials

logger = logging.getLogger(__name__)


class GCalError(Exception):
    pass


def _service(user_id: str):
    creds = load_credentials(user_id)
    if not creds:
        raise GCalError("Google account not connected. Use /connect_google in Telegram.")
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# 'primary' is a special Google Calendar alias for the authenticated user's main calendar
PRIMARY = "primary"


def list_events(
    user_id: str,
    time_min: str | None = None,
    time_max: str | None = None,
    query: str | None = None,
    max_results: int = 20,
) -> list[dict]:
    """List events on the primary calendar within an optional time range and/or matching a query."""
    try:
        svc = _service(user_id)
        kwargs = {
            "calendarId": PRIMARY,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        # Default to "from now" if neither bound provided
        if not time_min and not time_max:
            kwargs["timeMin"] = datetime.now(timezone.utc).isoformat()
        if time_min:
            kwargs["timeMin"] = time_min
        if time_max:
            kwargs["timeMax"] = time_max
        if query:
            kwargs["q"] = query

        result = svc.events().list(**kwargs).execute()
        return [_simplify_event(e) for e in result.get("items", [])]
    except HttpError as e:
        raise GCalError(f"Calendar API error: {e}")


def get_event(user_id: str, event_id: str) -> dict:
    try:
        svc = _service(user_id)
        e = svc.events().get(calendarId=PRIMARY, eventId=event_id).execute()
        return _simplify_event(e)
    except HttpError as e:
        raise GCalError(f"Calendar API error: {e}")


def create_event(
    user_id: str,
    summary: str,
    start: str,
    end: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    timezone_name: str | None = None,
) -> dict:
    """Create a calendar event. start/end are ISO 8601 strings."""
    try:
        svc = _service(user_id)
        body = {
            "summary": summary,
            "start": _format_when(start, timezone_name),
            "end": _format_when(end, timezone_name),
        }
        if description: body["description"] = description
        if location: body["location"] = location
        if attendees: body["attendees"] = [{"email": a} for a in attendees]

        result = svc.events().insert(
            calendarId=PRIMARY,
            body=body,
            sendUpdates="all" if attendees else "none",
        ).execute()
        return _simplify_event(result)
    except HttpError as e:
        raise GCalError(f"Calendar API error: {e}")


def update_event(
    user_id: str,
    event_id: str,
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
    add_attendees: list[str] | None = None,
    timezone_name: str | None = None,
) -> dict:
    """Patch an existing event. Only changes provided fields."""
    try:
        svc = _service(user_id)
        # Fetch current to merge attendees correctly
        current = svc.events().get(calendarId=PRIMARY, eventId=event_id).execute()
        patch = {}
        if summary is not None: patch["summary"] = summary
        if description is not None: patch["description"] = description
        if location is not None: patch["location"] = location
        if start: patch["start"] = _format_when(start, timezone_name)
        if end: patch["end"] = _format_when(end, timezone_name)
        if add_attendees:
            existing = current.get("attendees", []) or []
            existing_emails = {a.get("email") for a in existing}
            new = [{"email": a} for a in add_attendees if a not in existing_emails]
            patch["attendees"] = existing + new

        result = svc.events().patch(
            calendarId=PRIMARY,
            eventId=event_id,
            body=patch,
            sendUpdates="all" if add_attendees else "none",
        ).execute()
        return _simplify_event(result)
    except HttpError as e:
        raise GCalError(f"Calendar API error: {e}")


def delete_event(user_id: str, event_id: str, notify: bool = True) -> dict:
    """Delete an event. Recoverable from Google Calendar trash for 30 days."""
    try:
        svc = _service(user_id)
        svc.events().delete(
            calendarId=PRIMARY,
            eventId=event_id,
            sendUpdates="all" if notify else "none",
        ).execute()
        return {"deleted": True, "event_id": event_id}
    except HttpError as e:
        raise GCalError(f"Calendar API error: {e}")


def _format_when(iso: str, tz: str | None) -> dict:
    """Format an ISO datetime string for Google Calendar.
    If it's a bare date (YYYY-MM-DD), treat as all-day event.
    """
    if len(iso) == 10 and iso.count("-") == 2:
        return {"date": iso}
    payload = {"dateTime": iso}
    if tz:
        payload["timeZone"] = tz
    return payload


def _simplify_event(e: dict) -> dict:
    start = e.get("start", {})
    end = e.get("end", {})
    return {
        "id": e.get("id"),
        "summary": e.get("summary"),
        "description": e.get("description"),
        "location": e.get("location"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "status": e.get("status"),
        "html_link": e.get("htmlLink"),
        "attendees": [
            {"email": a.get("email"), "response_status": a.get("responseStatus")}
            for a in e.get("attendees", []) or []
        ],
        "organizer_email": (e.get("organizer") or {}).get("email"),
        "creator_email": (e.get("creator") or {}).get("email"),
    }