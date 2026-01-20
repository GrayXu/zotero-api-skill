#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter, Retry

REQUEST_TIMEOUT = 20
DEFAULT_LIMIT = 100


def build_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=10,
        backoff_factor=1,
        allowed_methods=None,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def resolve_auth(args: argparse.Namespace) -> Tuple[str, str]:
    user = args.user or os.getenv("ZOTERO_USER")
    api_key = args.api_key or os.getenv("ZOTERO_API_KEY")
    if not user:
        raise SystemExit("Missing ZOTERO_USER (or pass --user)")
    if not api_key:
        raise SystemExit("Missing ZOTERO_API_KEY (or pass --api-key)")
    return user, api_key


def zotero_headers(api_key: str) -> Dict[str, str]:
    return {
        "Zotero-API-Key": api_key,
        "Zotero-API-Version": "3",
        "Content-Type": "application/json",
    }


def fetch_items_page(
    session: requests.Session,
    user: str,
    api_key: str,
    start: int,
    limit: int,
    query: Optional[str] = None,
    qmode: Optional[str] = None,
    item_type: Optional[str] = None,
    tag: Optional[str] = None,
) -> Tuple[list, Optional[int]]:
    params: Dict[str, str] = {
        "format": "json",
        "start": str(start),
        "limit": str(limit),
    }
    if query:
        params["q"] = query
    if qmode:
        params["qmode"] = qmode
    if item_type:
        params["itemType"] = item_type
    if tag:
        params["tag"] = tag
    response = session.get(
        f"https://api.zotero.org/users/{user}/items",
        headers=zotero_headers(api_key),
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    total = response.headers.get("Total-Results")
    total_int = int(total) if total and total.isdigit() else None
    return response.json(), total_int


def fetch_item(
    session: requests.Session,
    user: str,
    api_key: str,
    key: str,
) -> Dict[str, Any]:
    response = session.get(
        f"https://api.zotero.org/users/{user}/items/{key}",
        headers=zotero_headers(api_key),
        params={"format": "json"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def save_item(
    item: Dict[str, Any],
    output_dir: Path,
    snapshot_suffix: Optional[str],
    include_attachments: bool,
) -> bool:
    data = item.get("data", item)
    if data.get("itemType") == "attachment" and not include_attachments:
        return False
    key = item.get("key") or data.get("key")
    if not key:
        return False
    item_dir = output_dir / key
    item_dir.mkdir(parents=True, exist_ok=True)
    with open(item_dir / "original.json", "w", encoding="utf-8") as f:
        json.dump(item, f, indent=2)
    if snapshot_suffix:
        snapshot_path = item_dir / f"original-{snapshot_suffix}.json"
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(item, f, indent=2)
    return True


def load_json_input(path: str) -> Dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_payload(payload: Dict[str, Any], data_only: bool) -> Dict[str, Any]:
    if data_only:
        return payload
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def cmd_download(args: argparse.Namespace) -> None:
    user, api_key = resolve_auth(args)
    session = build_session()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start = args.start
    processed = 0
    saved = 0
    total = None
    snapshot_suffix = None if args.no_snapshot else datetime.now().strftime("%m-%d")

    while True:
        if args.max_items is not None:
            remaining = args.max_items - processed
            if remaining <= 0:
                break
            limit = min(args.limit, remaining)
        else:
            limit = args.limit

        items, total = fetch_items_page(session, user, api_key, start, limit)
        if not items:
            break
        processed += len(items)
        for item in items:
            if save_item(item, output_dir, snapshot_suffix, args.include_attachments):
                saved += 1

        total_display = total if total is not None else "?"
        print(f"Fetched {processed}/{total_display} items, saved {saved}")

        start += limit
        if total is not None and start >= total:
            break


def cmd_get(args: argparse.Namespace) -> None:
    user, api_key = resolve_auth(args)
    session = build_session()

    item = fetch_item(session, user, api_key, args.key)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(item, f, indent=2)
    else:
        print(json.dumps(item, ensure_ascii=False, indent=2))


def cmd_search(args: argparse.Namespace) -> None:
    user, api_key = resolve_auth(args)
    session = build_session()

    items, total = fetch_items_page(
        session,
        user,
        api_key,
        args.start,
        args.limit,
        query=args.query,
        qmode=args.qmode,
        item_type=args.item_type,
        tag=args.tag,
    )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(items, ensure_ascii=False, indent=2))

    if total is not None:
        print(f"Total-Results: {total}")


def normalize_create_payload(payload: Any, data_only: bool) -> list:
    if isinstance(payload, list):
        items = payload
    else:
        items = [payload]

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise SystemExit("Create payload must be a JSON object or list of objects")
        if data_only:
            normalized.append(item)
        elif "data" in item:
            normalized.append(item["data"])
        else:
            normalized.append(item)
    return normalized


def cmd_create(args: argparse.Namespace) -> None:
    user, api_key = resolve_auth(args)
    session = build_session()

    payload = load_json_input(args.input)
    payload = normalize_create_payload(payload, args.data_only)

    response = session.post(
        f"https://api.zotero.org/users/{user}/items",
        headers=zotero_headers(api_key),
        params={"format": "json"},
        data=json.dumps(payload),
        timeout=REQUEST_TIMEOUT,
    )
    print(f"Status: {response.status_code}")
    print(response.text)


def cmd_update(args: argparse.Namespace) -> None:
    user, api_key = resolve_auth(args)
    session = build_session()

    payload = load_json_input(args.input)
    payload = normalize_payload(payload, args.data_only)

    response = session.put(
        f"https://api.zotero.org/users/{user}/items/{args.key}",
        headers=zotero_headers(api_key),
        params={"format": "json"},
        data=json.dumps(payload),
        timeout=REQUEST_TIMEOUT,
    )
    print(f"Status: {response.status_code}")
    print(response.text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Zotero API CLI")
    parser.add_argument("--user", help="Zotero user ID (default: ZOTERO_USER)")
    parser.add_argument("--api-key", help="Zotero API key (default: ZOTERO_API_KEY)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_download = sub.add_parser("download", help="Download items to disk")
    p_download.add_argument("--output-dir", default="output")
    p_download.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p_download.add_argument("--max-items", type=int)
    p_download.add_argument("--include-attachments", action="store_true")
    p_download.add_argument("--start", type=int, default=0)
    p_download.add_argument("--no-snapshot", action="store_true")
    p_download.set_defaults(func=cmd_download)

    p_get = sub.add_parser("get", help="Fetch a single item")
    p_get.add_argument("--key", required=True)
    p_get.add_argument("--output")
    p_get.set_defaults(func=cmd_get)

    p_search = sub.add_parser("search", help="Search items")
    p_search.add_argument("--query", required=True, help="Search query string")
    p_search.add_argument("--qmode", choices=["titleCreatorYear", "everything"])
    p_search.add_argument("--item-type")
    p_search.add_argument("--tag")
    p_search.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p_search.add_argument("--start", type=int, default=0)
    p_search.add_argument("--output")
    p_search.set_defaults(func=cmd_search)

    p_create = sub.add_parser("create", help="Create item(s)")
    p_create.add_argument("--input", required=True, help="Path or '-' for stdin")
    p_create.add_argument("--data-only", action="store_true")
    p_create.set_defaults(func=cmd_create)

    p_update = sub.add_parser("update", help="Update item metadata")
    p_update.add_argument("--key", required=True)
    p_update.add_argument("--input", required=True, help="Path or '-' for stdin")
    p_update.add_argument("--data-only", action="store_true")
    p_update.set_defaults(func=cmd_update)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
