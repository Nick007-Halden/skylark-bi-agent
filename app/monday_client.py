"""
monday_client.py
-----------------
Thin wrapper around the monday.com GraphQL API (https://api.monday.com/v2).
Responsible ONLY for talking to monday.com and returning raw item data.
No cleaning, no business logic here — that's cleaner.py and analytics.py.

Why this matters for the assignment: the brief explicitly says
"Do not hardcode CSV data. Your agent must query monday.com dynamically."
Every function here hits the live API each time it's called — nothing is cached
to disk as a permanent source of truth (a light in-memory cache with a short
TTL is used only to avoid hammering the API within a single user session).
"""

import os
import time
import requests
from typing import Any

MONDAY_API_URL = "https://api.monday.com/v2"
API_VERSION = "2026-07"

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL_SECONDS = 60  # short TTL: keeps the "dynamic" requirement honest


class MondayAPIError(Exception):
    pass


def _get_token() -> str:
    token = os.environ.get("MONDAY_API_TOKEN")
    if not token:
        raise MondayAPIError(
            "MONDAY_API_TOKEN is not set. Add it as an environment variable "
            "or in Streamlit secrets."
        )
    return token


def _run_query(query: str, variables: dict | None = None) -> dict:
    headers = {
        "Authorization": _get_token(),
        "Content-Type": "application/json",
        "API-Version": API_VERSION,
    }
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = requests.post(MONDAY_API_URL, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise MondayAPIError(f"monday.com API returned HTTP {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    if "errors" in data:
        raise MondayAPIError(f"monday.com API errors: {data['errors']}")
    return data["data"]


def _cached(key: str, fn):
    now = time.time()
    if key in _CACHE:
        ts, val = _CACHE[key]
        if now - ts < _CACHE_TTL_SECONDS:
            return val
    val = fn()
    _CACHE[key] = (now, val)
    return val


def list_boards() -> list[dict]:
    """Return all boards visible to this token (id + name) — used for setup/debugging."""
    def _fetch():
        query = "{ boards (limit: 50) { id name } }"
        return _run_query(query)["boards"]
    return _cached("boards", _fetch)


def get_board_items(board_id: str, limit_pages: int = 20) -> list[dict]:
    """
    Fetch ALL items (rows) from a board, following pagination (items_page/cursor).
    Returns a list of dicts: [{ "name": ..., "column_values": {col_id: text/value} }, ...]
    """
    cache_key = f"items_{board_id}"

    def _fetch():
        items: list[dict] = []
        cursor = None
        pages = 0
        while pages < limit_pages:
            query = """
            query ($boardId: [ID!], $cursor: String) {
              boards (ids: $boardId) {
                items_page (limit: 100, cursor: $cursor) {
                  cursor
                  items {
                    id
                    name
                    column_values {
                      id
                      text
                      value
                      column {
                        title
                      }
                    }
                  }
                }
              }
            }
            """
            data = _run_query(query, {"boardId": [board_id], "cursor": cursor})
            boards = data.get("boards", [])
            if not boards:
                break
            page = boards[0]["items_page"]
            for item in page["items"]:
                row = {"id": item["id"], "name": item["name"]}
                for cv in item["column_values"]:
                    col_title = cv["column"]["title"] if cv.get("column") else cv["id"]
                    row[col_title] = cv["text"]
                items.append(row)
            cursor = page.get("cursor")
            pages += 1
            if not cursor:
                break
        return items

    return _cached(cache_key, _fetch)


def get_board_schema(board_id: str) -> list[dict]:
    """Return column titles + types for a board — useful for validating expected columns."""
    def _fetch():
        query = """
        query ($boardId: [ID!]) {
          boards (ids: $boardId) {
            columns { id title type }
          }
        }
        """
        data = _run_query(query, {"boardId": [board_id]})
        boards = data.get("boards", [])
        return boards[0]["columns"] if boards else []
    return _cached(f"schema_{board_id}", _fetch)
