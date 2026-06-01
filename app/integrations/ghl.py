"""GoHighLevel API wrapper. All HTTP calls to GHL go through here."""
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

GHL_API_BASE = "https://services.leadconnectorhq.com"
GHL_API_VERSION = "2021-07-28"


def _headers() -> dict:
    """Standard headers for GHL API calls."""
    return {
        "Authorization": f"Bearer {settings.GHL_PRIVATE_INTEGRATION_TOKEN}",
        "Version": GHL_API_VERSION,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def _get(path: str, params: dict | None = None) -> dict:
    """GET helper with standard auth + error handling."""
    url = f"{GHL_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=_headers(), params=params)
        if resp.status_code >= 400:
            logger.error(f"GHL GET {path} failed: {resp.status_code} {resp.text}")
            raise GHLAPIError(f"GHL API {resp.status_code}: {resp.text}")
        return resp.json()


async def _post(path: str, json: dict) -> dict:
    """POST helper with standard auth + error handling."""
    url = f"{GHL_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, headers=_headers(), json=json)
        if resp.status_code >= 400:
            logger.error(f"GHL POST {path} failed: {resp.status_code} {resp.text}")
            raise GHLAPIError(f"GHL API {resp.status_code}: {resp.text}")
        return resp.json()


class GHLAPIError(Exception):
    """Raised when GHL API returns an error."""


# ============================================================
# CONTACTS
# ============================================================
async def search_contacts(query: str, limit: int = 10) -> list[dict]:
    """Search contacts by name, email, or phone. Returns simplified contact list."""
    result = await _post(
        "/contacts/search",
        json={
            "locationId": settings.GHL_LOCATION_ID,
            "pageLimit": limit,
            "filters": [
                {
                    "field": "searchAfter",
                    "operator": "contains",
                    "value": query,
                }
            ] if False else [],  # Use simple query param instead
            "query": query,
        },
    )
    contacts = result.get("contacts", [])
    return [_simplify_contact(c) for c in contacts]


def _simplify_contact(c: dict) -> dict:
    """Strip GHL contact down to fields the agent actually needs."""
    return {
        "id": c.get("id"),
        "first_name": c.get("firstName"),
        "last_name": c.get("lastName"),
        "full_name": c.get("contactName") or f"{c.get('firstName', '')} {c.get('lastName', '')}".strip(),
        "email": c.get("email"),
        "phone": c.get("phone"),
        "tags": c.get("tags", []),
        "created_at": c.get("dateAdded"),
    }


# ============================================================
# CONVERSATIONS
# ============================================================
async def search_conversations(contact_id: str | None = None, limit: int = 10) -> list[dict]:
    """List recent conversations, optionally filtered to one contact."""
    params = {
        "locationId": settings.GHL_LOCATION_ID,
        "limit": limit,
    }
    if contact_id:
        params["contactId"] = contact_id

    result = await _get("/conversations/search", params=params)
    convos = result.get("conversations", [])
    return [_simplify_conversation(c) for c in convos]


def _simplify_conversation(c: dict) -> dict:
    return {
        "id": c.get("id"),
        "contact_id": c.get("contactId"),
        "contact_name": c.get("fullName") or c.get("contactName"),
        "last_message_type": c.get("lastMessageType"),
        "last_message_body": c.get("lastMessageBody"),
        "last_message_date": c.get("lastMessageDate"),
        "unread_count": c.get("unreadCount", 0),
    }


async def get_conversation_messages(conversation_id: str, limit: int = 20) -> list[dict]:
    """Get the messages inside one conversation."""
    result = await _get(
        f"/conversations/{conversation_id}/messages",
        params={"limit": limit},
    )
    messages = result.get("messages", {}).get("messages", [])
    return [_simplify_message(m) for m in messages]


def _simplify_message(m: dict) -> dict:
    return {
        "id": m.get("id"),
        "type": m.get("type"),  # 1=SMS, 3=Email, etc.
        "direction": m.get("direction"),  # inbound/outbound
        "body": m.get("body"),
        "date": m.get("dateAdded"),
        "status": m.get("status"),
    }