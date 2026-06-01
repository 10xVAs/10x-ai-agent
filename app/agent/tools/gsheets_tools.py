"""Claude tool definitions + executors for Google Sheets."""
import json
import logging
from app.integrations import gsheets

logger = logging.getLogger(__name__)


GSHEETS_TOOL_DEFINITIONS = [
    {
        "name": "gsheets_read_write",
        "description": (
            "Multi-purpose Google Sheets tool. Actions:\n"
            "  - 'metadata': return spreadsheet title and list of sheet tabs (use this first to discover sheet names).\n"
            "  - 'read': read a range in A1 notation (e.g. 'Sheet1!A1:C10' or 'Sheet1!A:C' for whole columns). "
            "Returns a 2D array of cell values.\n"
            "  - 'write': overwrite a range with provided values (2D array, rows of cells).\n"
            "  - 'append': append rows to the end of a sheet (range like 'Sheet1!A:Z' tells where to look).\n\n"
            "Always confirm before write/append unless the user has been explicit. "
            "The spreadsheet_id is the long random string in the sheet's URL between /d/ and /edit. "
            "Ask the user for the sheet URL or ID if they haven't provided one. "
            "All writes are non-destructive in practice — Google Sheets keeps full version history (File → Version history)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["metadata", "read", "write", "append"],
                },
                "spreadsheet_id": {
                    "type": "string",
                    "description": "The spreadsheet ID from the URL.",
                },
                "range": {
                    "type": "string",
                    "description": "A1 notation, e.g. 'Sheet1!A1:C10'. Required for read/write/append.",
                },
                "values": {
                    "type": "array",
                    "items": {"type": "array", "items": {}},
                    "description": "2D array of values (rows of cells). Required for write/append.",
                },
            },
            "required": ["action", "spreadsheet_id"],
        },
    },
]


async def execute_gsheets_read_write(
    user_id: str,
    action: str,
    spreadsheet_id: str,
    range: str | None = None,
    values: list | None = None,
) -> str:
    try:
        if action == "metadata":
            meta = gsheets.get_metadata(user_id=user_id, spreadsheet_id=spreadsheet_id)
            return json.dumps(meta)

        if action == "read":
            if not range:
                return json.dumps({"error": "read requires range."})
            result = gsheets.read_range(user_id=user_id, spreadsheet_id=spreadsheet_id, range_a1=range)
            return json.dumps(result)

        if action == "write":
            if not (range and values):
                return json.dumps({"error": "write requires range and values."})
            result = gsheets.write_range(
                user_id=user_id, spreadsheet_id=spreadsheet_id, range_a1=range, values=values,
            )
            return json.dumps({"success": True, "action_taken": "wrote", "result": result})

        if action == "append":
            if not (range and values):
                return json.dumps({"error": "append requires range and values."})
            result = gsheets.append_rows(
                user_id=user_id, spreadsheet_id=spreadsheet_id, range_a1=range, values=values,
            )
            return json.dumps({"success": True, "action_taken": "appended", "result": result})

        return json.dumps({"error": f"Unknown action: {action}"})
    except gsheets.GSheetsError as e:
        return json.dumps({"error": str(e)})


GSHEETS_TOOL_EXECUTORS = {
    "gsheets_read_write": execute_gsheets_read_write,
}