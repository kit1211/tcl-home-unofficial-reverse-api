#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

from tcl_auth.client import TclAuthClient


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

    parser = argparse.ArgumentParser(description="TCL Home account auth helper")
    parser.add_argument("--env-file", default=pre_args.env_file, help="ไฟล์ .env สำหรับ credentials")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="login ด้วย username/password (default: HA plain JSON)")
    login.add_argument("--account", default=os.environ.get("TCL_ACCOUNT"))
    login.add_argument("--password", default=os.environ.get("TCL_PASSWORD"))
    login.add_argument("--country-code", default=os.environ.get("TCL_COUNTRY_CODE", "66"))
    login.add_argument(
        "--ios-encrypted",
        action="store_true",
        help="บังคับใช้ iOS encrypted login (มักล้มเหลวจากสคริปต์)",
    )

    refresh = sub.add_parser("refresh", help="renew account session (HA: re-login, iOS: encrypted refresh)")
    refresh_iot = sub.add_parser("refresh-iot", help="เรียก /v3/auth/refresh_tokens ได้ saas/cognito token")
    status = sub.add_parser("status", help="ดูสถานะ token ปัจจุบัน")
    ensure = sub.add_parser("ensure", help="ใช้ token ที่มี (ไม่ login/refresh โดยค่าเริ่มต้น)")
    ensure.add_argument("--login-if-missing", action="store_true", help="login ถ้ายังไม่มี session")
    ensure.add_argument(
        "--refresh",
        action="store_true",
        help="HA: re-login เมื่อ token ใกล้หมด | iOS: encrypted refresh",
    )

    imp = sub.add_parser("import", help="นำเข้า token/refreshtoken จากแอป (ไม่ kick ถ้าไม่ login)")
    imp.add_argument("--login-account", required=True)
    imp.add_argument("--token", required=True)
    imp.add_argument("--refresh-token", required=True)
    imp.add_argument("--username")

    coexist = sub.add_parser("test-coexist", help="HA login แล้วทดสอบว่า token เก่า (แอพ iOS) ยังใช้ได้ไหม")
    coexist.add_argument("--account", default=os.environ.get("TCL_ACCOUNT"))
    coexist.add_argument("--password", default=os.environ.get("TCL_PASSWORD"))
    coexist.add_argument("--country-code", default=os.environ.get("TCL_COUNTRY_CODE", "66"))
    coexist.add_argument(
        "--save",
        action="store_true",
        help="บันทึก session ใหม่หลังทดสอบ (default: ไม่บันทึก)",
    )

    args = parser.parse_args()
    client = TclAuthClient()
    if args.command == "login" and getattr(args, "ios_encrypted", False):
        client.auth_mode = "ios_encrypted"

    if args.command == "login":
        if not args.account or not args.password:
            print("ต้องระบุ --account และ --password หรือตั้ง TCL_ACCOUNT/TCL_PASSWORD ใน .env", file=sys.stderr)
            return 2
        session = client.login(args.account, args.password, country_code=args.country_code)
        print(json.dumps(client.token_status(session).__dict__, ensure_ascii=False, indent=2))
        print(f"auth_flow: {session.auth_flow}, user_id: {session.user_id}")
        print(f"session saved: {client.store.path}")
        return 0

    if args.command == "refresh":
        session = client.refresh()
        print(json.dumps(client.token_status(session).__dict__, ensure_ascii=False, indent=2))
        return 0

    if args.command == "refresh-iot":
        result = client.refresh_iot_tokens()
        print(
            json.dumps(
                {
                    "saas_token_prefix": result.saas_token[:40] + "...",
                    "cognito_id": result.cognito_id,
                    "mqtt_endpoint": result.mqtt_endpoint,
                    "code": result.raw.get("code"),
                    "message": result.raw.get("message"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "status":
        session = client.store.load()
        if not session:
            print("ยังไม่มี session")
            return 1
        status_data = client.token_status(session).__dict__
        status_data["auth_flow"] = session.auth_flow
        status_data["user_id"] = session.user_id
        status_data["cloud_url"] = session.cloud_url
        print(json.dumps(status_data, ensure_ascii=False, indent=2))
        return 0

    if args.command == "ensure":
        session = client.ensure_token(
            allow_login=args.login_if_missing,
            allow_refresh=args.refresh,
            account=os.environ.get("TCL_ACCOUNT"),
            password=os.environ.get("TCL_PASSWORD"),
            country_code=os.environ.get("TCL_COUNTRY_CODE", "66"),
        )
        print(json.dumps(client.token_status(session).__dict__, ensure_ascii=False, indent=2))
        return 0

    if args.command == "import":
        session = client.import_session(
            login_account=args.login_account,
            token=args.token,
            refresh_token=args.refresh_token,
            username=args.username,
        )
        print(json.dumps(client.token_status(session).__dict__, ensure_ascii=False, indent=2))
        print(f"session saved: {client.store.path}")
        return 0

    if args.command == "test-coexist":
        if not args.account or not args.password:
            print("ต้องระบุ --account และ --password หรือตั้ง TCL_ACCOUNT/TCL_PASSWORD ใน .env", file=sys.stderr)
            return 2
        report = client.test_coexistence(
            args.account,
            args.password,
            country_code=args.country_code,
            persist_new_session=args.save,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report.get("ios_session_likely_kicked"):
            print("\nสรุป: token เก่า (แอพ iOS) น่าจะถูก invalidate แล้ว — แอพอาจต้อง login ใหม่")
        elif report.get("had_previous_session"):
            print("\nสรุป: token เก่ายัง valid บน server — co-existence เป็นไปได้ (แต่ควรเช็คแอพจริงด้วย)")
        else:
            print("\nสรุป: ไม่มี session เก่าให้เทียบ — ลอง import token จากแอพก่อน แล้วรัน test-coexist อีกครั้ง")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
