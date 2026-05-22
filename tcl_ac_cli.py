#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from tcl_auth.client import TclAuthClient
from tcl_iot.client import DEFAULT_DEVICE_ID, TclIotClient


def _load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _session_token(*, allow_refresh: bool) -> str:
    auth = TclAuthClient()
    session = auth.ensure_token(allow_refresh=allow_refresh)
    return session.token


def main() -> int:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--env-file", default=".env")
    pre_args, _ = pre.parse_known_args()
    _load_env_file(pre_args.env_file)

    parser = argparse.ArgumentParser(description="TCL Home AC control (ไม่ kick session แอป)")
    parser.add_argument("--env-file", default=pre_args.env_file)
    parser.add_argument(
        "--refresh-token",
        action="store_true",
        help="อนุญาต refresh account token (อาจ rotate refreshToken — ใช้เมื่อจำเป็น)",
    )
    parser.add_argument(
        "--device-id",
        default=os.environ.get("TCL_DEVICE_ID", DEFAULT_DEVICE_ID),
        help="AWS thing / device id",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("on", help="เปิดแอร์")
    sub.add_parser("off", help="ปิดแอร์")

    test = sub.add_parser("test", help="เปิดแอร์ N วินาทีแล้วปิด")
    test.add_argument("--seconds", type=int, default=10)

    args = parser.parse_args()
    token = _session_token(allow_refresh=args.refresh_token)
    iot = TclIotClient(token)
    device_id = args.device_id

    if args.command == "on":
        result = iot.set_power(device_id=device_id, on=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("เปิดแอร์แล้ว")
        return 0

    if args.command == "off":
        result = iot.set_power(device_id=device_id, on=False)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("ปิดแอร์แล้ว")
        return 0

    if args.command == "test":
        print(f"เปิดแอร์ {args.seconds} วินาที...")
        lb = iot.load_balance()
        creds = iot.get_aws_credentials(lb)
        on_result = iot.set_power(device_id=device_id, on=True, load_balance=lb, credentials=creds)
        print(json.dumps(on_result, ensure_ascii=False, indent=2))
        time.sleep(args.seconds)
        off_result = iot.set_power(device_id=device_id, on=False, load_balance=lb, credentials=creds)
        print(json.dumps(off_result, ensure_ascii=False, indent=2))
        print(f"ทดสอบเสร็จ: เปิด {args.seconds} วิ แล้วปิด")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
