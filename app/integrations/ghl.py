"""GoHighLevel API wrapper. All HTTP calls to GHL go through here."""
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

GHL_API_BASE = "https://services.leadconnectorhq.com"
GHL_API_VERSION = "2021-07-28"


class GHLAPIError(Exception):
    """Raised when GHL API returns an error."""


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.GHL_PRIVATE_INTEGRATION_TOKEN}",
        "Version": GHL_API_VERSION,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def _get(path: str, params: dict | None = None) -> dict:
    url = f"{GHL_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=_headers(), params=params)
        if resp.status_code >= 400:
            logger.error(f"GHL GET {path} failed: {resp.status_code} {resp.text}")
            raise GHLAPIError(f"GHL API {resp.status_code}: {resp.text}")
        return resp.json()


async def _post(path: str, json: dict) -> dict:
    url = f"{GHL_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, headers=_headers(), json=json)
        if resp.status_code >= 400:
            logger.error(f"GHL POST {path} failed: {resp.status_code} {resp.text}")
            raise GHLAPIError(f"GHL API {resp.status_code}: {resp.text}")
        return resp.json()


async def _put(path: str, json: dict) -> dict:
    url = f"{GHL_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.put(url, headers=_headers(), json=json)
        if resp.status_code >= 400:
            logger.error(f"GHL PUT {path} failed: {resp.status_code} {resp.text}")
            raise GHLAPIError(f"GHL API {resp.status_code}: {resp.text}")
        return resp.json()


def is_live_mode() -> bool:
    """Return True if write tools should actually call GHL; False if dry-run."""
    return settings.GHL_WRITE_MODE.lower() == "live"


# ============================================================
# CONTACTS (READ)
# ============================================================
async def search_contacts(query: str, limit: int = 10) -> list[dict]:
    result = await _post(
        "/contacts/search",
        json={
            "locationId": settings.GHL_LOCATION_ID,
            "pageLimit": limit,
            "filters": [],
            "query": query,
        },
    )
    contacts = result.get("contacts", [])
    return [_simplify_contact(c) for c in contacts]


def _simplify_contact(c: dict) -> dict:
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
# CONTACTS (WRITE)
# ============================================================
async def create_contact(
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    payload = {
        "locationId": settings.GHL_LOCATION_ID,
    }
    if first_name: payload["firstName"] = first_name
    if last_name: payload["lastName"] = last_name
    if email: payload["email"] = email
    if phone: payload["phone"] = phone
    if tags: payload["tags"] = tags

    result = await _post("/contacts/", json=payload)
    return _simplify_contact(result.get("contact", result))


async def update_contact(
    contact_id: str,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    tags_to_add: list[str] | None = None,
) -> dict:
    payload = {}
    if first_name is not None: payload["firstName"] = first_name
    if last_name is not None: payload["lastName"] = last_name
    if email is not None: payload["email"] = email
    if phone is not None: payload["phone"] = phone
    if tags_to_add: payload["tags"] = tags_to_add

    result = await _put(f"/contacts/{contact_id}", json=payload)
    return _simplify_contact(result.get("contact", result))


async def add_contact_note(contact_id: str, body: str) -> dict:
    result = await _post(
        f"/contacts/{contact_id}/notes",
        json={"body": body},
    )
    note = result.get("note", result)
    return {
        "id": note.get("id"),
        "body": note.get("body"),
        "created_at": note.get("dateAdded"),
    }


# ============================================================
# CONVERSATIONS / MESSAGES
# ============================================================
async def search_conversations(contact_id: str | None = None, limit: int = 10) -> list[dict]:
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
    result = await _get(
        f"/conversations/{conversation_id}/messages",
        params={"limit": limit},
    )
    messages = result.get("messages", {}).get("messages", [])
    return [_simplify_message(m) for m in messages]


def _simplify_message(m: dict) -> dict:
    return {
        "id": m.get("id"),
        "type": m.get("type"),
        "direction": m.get("direction"),
        "body": m.get("body"),
        "date": m.get("dateAdded"),
        "status": m.get("status"),
    }


async def send_sms(contact_id: str, message: str) -> dict:
    result = await _post(
        "/conversations/messages",
        json={
            "type": "SMS",
            "contactId": contact_id,
            "message": message,
        },
    )
    return {
        "message_id": result.get("messageId"),
        "conversation_id": result.get("conversationId"),
        "status": "sent",
    }


# ============================================================
# OPPORTUNITIES / PIPELINE
# ============================================================
async def list_pipelines() -> list[dict]:
    result = await _get(
        "/opportunities/pipelines",
        params={"locationId": settings.GHL_LOCATION_ID},
    )
    pipelines = result.get("pipelines", [])
    return [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "stages": [
                {"id": s.get("id"), "name": s.get("name"), "position": s.get("position")}
                for s in p.get("stages", [])
            ],
        }
        for p in pipelines
    ]


async def search_opportunities(
    pipeline_id: str | None = None,
    contact_id: str | None = None,
    limit: int = 20,
) -> list[dict]:
    params = {
        "location_id": settings.GHL_LOCATION_ID,
        "limit": limit,
    }
    if pipeline_id:
        params["pipeline_id"] = pipeline_id
    if contact_id:
        params["contact_id"] = contact_id

    result = await _get("/opportunities/search", params=params)
    opps = result.get("opportunities", [])
    return [
        {
            "id": o.get("id"),
            "name": o.get("name"),
            "monetary_value": o.get("monetaryValue"),
            "pipeline_id": o.get("pipelineId"),
            "pipeline_stage_id": o.get("pipelineStageId"),
            "status": o.get("status"),
            "contact_id": (o.get("contact") or {}).get("id"),
            "contact_name": (o.get("contact") or {}).get("name"),
            "updated_at": o.get("updatedAt"),
        }
        for o in opps
    ]


async def update_opportunity_stage(
    opportunity_id: str,
    pipeline_id: str,
    pipeline_stage_id: str,
) -> dict:
    result = await _put(
        f"/opportunities/{opportunity_id}",
        json={
            "pipelineId": pipeline_id,
            "pipelineStageId": pipeline_stage_id,
        },
    )
    opp = result.get("opportunity", result)
    return {
        "id": opp.get("id"),
        "name": opp.get("name"),
        "pipeline_id": opp.get("pipelineId"),
        "pipeline_stage_id": opp.get("pipelineStageId"),
        "status": opp.get("status"),
    }