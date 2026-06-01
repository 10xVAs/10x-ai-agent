"""Google Sheets API wrapper."""
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app.integrations.google_oauth import load_credentials

logger = logging.getLogger(__name__)


class GSheetsError(Exception):
    pass


def _service(user_id: str):
    creds = load_credentials(user_id)
    if not creds:
        raise GSheetsError("Google account not connected. Use /connect_google in Telegram.")
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def get_metadata(user_id: str, spreadsheet_id: str) -> dict:
    """Return spreadsheet title and list of sheets/tabs with their names."""
    try:
        svc = _service(user_id)
        meta = svc.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties.title,sheets.properties",
        ).execute()
        return {
            "spreadsheet_id": spreadsheet_id,
            "title": meta.get("properties", {}).get("title"),
            "sheets": [
                {
                    "name": s["properties"]["title"],
                    "sheet_id": s["properties"]["sheetId"],
                    "row_count": s["properties"].get("gridProperties", {}).get("rowCount"),
                    "col_count": s["properties"].get("gridProperties", {}).get("columnCount"),
                }
                for s in meta.get("sheets", [])
            ],
        }
    except HttpError as e:
        raise GSheetsError(f"Sheets API error: {e}")


def read_range(user_id: str, spreadsheet_id: str, range_a1: str) -> dict:
    """Read a range. range_a1 uses A1 notation: 'Sheet1!A1:C10' or 'Sheet1!A:C'."""
    try:
        svc = _service(user_id)
        result = svc.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
        ).execute()
        return {
            "range": result.get("range"),
            "values": result.get("values", []),
            "row_count": len(result.get("values", [])),
        }
    except HttpError as e:
        raise GSheetsError(f"Sheets API error: {e}")


def write_range(
    user_id: str,
    spreadsheet_id: str,
    range_a1: str,
    values: list[list],
) -> dict:
    """Overwrite a range with provided values. values is a 2D array (rows of cells)."""
    try:
        svc = _service(user_id)
        result = svc.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
            valueInputOption="USER_ENTERED",  # parse formulas, dates, etc.
            body={"values": values},
        ).execute()
        return {
            "updated_range": result.get("updatedRange"),
            "updated_rows": result.get("updatedRows"),
            "updated_columns": result.get("updatedColumns"),
            "updated_cells": result.get("updatedCells"),
        }
    except HttpError as e:
        raise GSheetsError(f"Sheets API error: {e}")


def append_rows(
    user_id: str,
    spreadsheet_id: str,
    range_a1: str,
    values: list[list],
) -> dict:
    """Append rows to the end of a sheet. range_a1 sets where to start looking, e.g. 'Sheet1!A:Z'."""
    try:
        svc = _service(user_id)
        result = svc.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()
        return {
            "updated_range": (result.get("updates") or {}).get("updatedRange"),
            "updated_rows": (result.get("updates") or {}).get("updatedRows"),
            "updated_cells": (result.get("updates") or {}).get("updatedCells"),
        }
    except HttpError as e:
        raise GSheetsError(f"Sheets API error: {e}")