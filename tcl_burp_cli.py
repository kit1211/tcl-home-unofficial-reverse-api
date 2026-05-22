#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

from tcl_burp.history import BurpHistoryItem, filter_items, summarize_item


def _load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--env-file", default=".env")
    pre_args, _ = pre.parse_known_args()
    _load_env_file(pre_args.env_file)

    parser = argparse.ArgumentParser(description="กรอง/สรุป Burp history ที่ export เป็น JSON")
    parser.add_argument("--env-file", default=pre_args.env_file)
    parser.add_argument("input", nargs="?", help="ไฟล์ JSON array ของ Burp MCP items")
    parser.add_argument("--since", help="HH:MM หรือ HH:MM:SS (default จาก TCL_BURP_SINCE)")
    parser.add_argument("--until", help="HH:MM หรือ HH:MM:SS (default จาก TCL_BURP_UNTIL)")
    parser.add_argument("--date", help="YYYY-MM-DD (default จาก TCL_BURP_DATE หรือวันนี้)")
    parser.add_argument("--summary", action="store_true", help="พิมพ์บรรทัดสรุปแทน JSON เต็ม")
    args = parser.parse_args()

    if not args.input:
        print("ใช้กับไฟล์ JSON ที่เก็บผลจาก Burp MCP", file=sys.stderr)
        return 2

    payload = json.loads(open(args.input, encoding="utf-8").read())
    if isinstance(payload, dict) and "request" in payload:
        items = [BurpHistoryItem.from_mcp(payload)]
    elif isinstance(payload, list):
        items = [BurpHistoryItem.from_mcp(x) if isinstance(x, dict) else x for x in payload]
    else:
        print("รูปแบบ input ไม่รองรับ", file=sys.stderr)
        return 2

    day = None
    if args.date:
        from datetime import date

        day = date.fromisoformat(args.date)

    filtered = filter_items(
        items,
        since_clock=args.since,
        until_clock=args.until,
        day=day,
    )

    if args.summary:
        for item in filtered:
            print(summarize_item(item))
        print(f"\n{len(filtered)} item(s)")
        return 0

    print(json.dumps([item.__dict__ for item in filtered], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
