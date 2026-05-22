from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests

from .crypto import encrypt_by_section, md5_hex
from .ha import (
    DEFAULT_HA_LOGIN_URL,
    RefreshTokensResult,
    do_ha_login,
    get_cloud_urls,
    refresh_tokens as ha_refresh_tokens,
)
from .session import SessionStore, TclSession

DEFAULT_CLIENT_ID = "54148614"
DEFAULT_ACCOUNT_HOST = "sg.account.tcl.com"
DEFAULT_AUTH_MODE = "ha"
DEFAULT_REFRESH_THRESHOLD = 0.3


@dataclass
class TokenStatus:
    token: str
    refresh_token: str
    login_account: str
    remaining_ratio: float | None
    should_refresh: bool
    expires_at: int | None


class TclAuthClient:
    def __init__(
        self,
        *,
        account_host: str | None = None,
        client_id: str | None = None,
        session_store: SessionStore | None = None,
        refresh_threshold: float = DEFAULT_REFRESH_THRESHOLD,
    ) -> None:
        self.account_host = account_host or os.environ.get("TCL_ACCOUNT_HOST", DEFAULT_ACCOUNT_HOST)
        self.client_id = client_id or os.environ.get("TCL_CLIENT_ID", DEFAULT_CLIENT_ID)
        self.store = session_store or SessionStore()
        self.refresh_threshold = refresh_threshold
        self.auth_mode = os.environ.get("TCL_AUTH_MODE", DEFAULT_AUTH_MODE).lower()
        self._public_key: str | None = None
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json; text/json; text/javascript; text/html; text/plain; charset/UTF-8",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": os.environ.get(
                    "TCL_USER_AGENT",
                    "TCLHome/6.1.3 (com.tcl.tclhome; build:1953; iOS 26.4.2) Alamofire/5.6.2",
                ),
                "Th_platform": os.environ.get("TCL_PLATFORM", "ios"),
                "Th_version": os.environ.get("TCL_APP_VERSION", "6.1.3"),
                "Th_appbuild": os.environ.get("TCL_APP_BUILD", "1953"),
            }
        )

    @staticmethod
    def normalize_username(account: str, country_code: str = "66") -> str:
        if account.startswith("+") or "@" in account or not re.fullmatch(r"\d+", account):
            return account
        if account.startswith("0"):
            account = account[1:]
        return f"+{country_code}{account}"

    def _base_url(self) -> str:
        return f"https://{self.account_host}"

    def fetch_public_key(self) -> str:
        url = f"{self._base_url()}/common/getPublicKey"
        response = self._session.get(url, params={"clientId": self.client_id}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        public_key = payload.get("publicKey")
        if not public_key:
            raise RuntimeError(f"getPublicKey ล้มเหลว: {payload}")
        self._public_key = public_key
        return public_key

    def _ensure_public_key(self) -> str:
        if self._public_key:
            return self._public_key
        cached = self.store.load()
        if cached and cached.client_id == self.client_id:
            pass
        return self.fetch_public_key()

    def _encrypt_query(self, value: str) -> str:
        public_key = self._ensure_public_key()
        return encrypt_by_section(value, public_key)

    def _encrypted_post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        encrypted_client_id = self._encrypt_query(self.client_id)
        encrypted_body = self._encrypt_query(json.dumps(body, separators=(",", ":"), ensure_ascii=False))
        url = f"{self._base_url()}{path}?clientId={quote(encrypted_client_id, safe='')}"
        response = self._session.post(
            url,
            data=encrypted_body,
            headers={"Encrypt": "true"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 1:
            msg = payload.get("msg") or payload
            if path.endswith("/refreshToken") and "empty" in str(msg).lower():
                raise RuntimeError(
                    f"{path} ล้มเหลว: {msg} — server decrypt body ไม่ได้ (ปัญหา RSA encrypt เหมือน login)"
                )
            raise RuntimeError(f"{path} ล้มเหลว: {msg}")
        return payload

    @staticmethod
    def _login_body(username: str, password_md5: str) -> dict[str, Any]:
        return {
            "channel": "app",
            "username": username,
            "password": password_md5,
            "captchaRule": 2,
            "osType": int(os.environ.get("TCL_OS_TYPE", "1")),
            "osVersion": os.environ.get("TCL_OS_VERSION", "26.4.2"),
            "equipment": int(os.environ.get("TCL_EQUIPMENT", "2")),
            "clientVersion": os.environ.get("TCL_APP_VERSION", "6.1.3"),
            "deviceModel": os.environ.get("TCL_DEVICE_MODEL", "iPhone17,3"),
        }

    def login(self, account: str, password: str, *, country_code: str = "66", persist: bool = True) -> TclSession:
        if self.auth_mode == "ios_encrypted":
            return self.login_ios_encrypted(account, password, country_code=country_code, persist=persist)
        return self.login_ha(account, password, country_code=country_code, persist=persist)

    def login_ha(
        self,
        account: str,
        password: str,
        *,
        country_code: str = "66",
        persist: bool = True,
    ) -> TclSession:
        username = self.normalize_username(account, country_code)
        result = do_ha_login(self._session, username=username, password=password)
        cloud = get_cloud_urls(self._session, user_id=result.user_id, sso_token=result.token)
        session = TclSession(
            username=username,
            login_account=result.login_account,
            token=result.token,
            refresh_token=result.refresh_token,
            client_id=self.client_id,
            account_host="pa.account.tcl.com",
            auth_flow="ha",
            user_id=result.user_id,
            cloud_url=cloud.cloud_url,
            cloud_region=cloud.cloud_region,
        )
        if persist:
            self.store.save(session)
        return session

    def login_ios_encrypted(
        self,
        account: str,
        password: str,
        *,
        country_code: str = "66",
        persist: bool = True,
    ) -> TclSession:
        username = self.normalize_username(account, country_code)
        payload = self._encrypted_post(
            "/account/login",
            self._login_body(username, md5_hex(password)),
        )
        session = TclSession.from_api_response(
            username=username,
            response=payload,
            client_id=self.client_id,
            account_host=self.account_host,
            auth_flow="ios_encrypted",
        )
        if persist:
            self.store.save(session)
        return session

    def refresh(self, session: TclSession | None = None, *, persist: bool = True) -> TclSession:
        current = session or self.store.load()
        if not current:
            raise RuntimeError("ไม่มี session — ให้ login หรือ import session ก่อน")
        if current.auth_flow == "ha" or self.auth_mode == "ha":
            return self.refresh_ha_account(current, persist=persist)
        return self.refresh_ios_encrypted(current, persist=persist)

    def refresh_ha_account(
        self,
        session: TclSession,
        *,
        account: str | None = None,
        password: str | None = None,
        country_code: str = "66",
        persist: bool = True,
    ) -> TclSession:
        """HA flow: account token ใกล้หมด → login ใหม่ (ไม่ใช้ /account/refreshToken)."""
        account = account or session.username
        password = password or os.environ.get("TCL_PASSWORD")
        if not password:
            raise RuntimeError("HA refresh ต้องมี password ใน .env หรือส่งมา explicit")
        return self.login_ha(account, password, country_code=country_code, persist=persist)

    def refresh_ios_encrypted(self, session: TclSession, *, persist: bool = True) -> TclSession:
        payload = self._encrypted_post(
            "/account/refreshToken",
            {
                "username": session.login_account,
                "refreshToken": session.refresh_token,
            },
        )
        refreshed = TclSession.from_api_response(
            username=session.username,
            response=payload,
            client_id=self.client_id,
            account_host=self.account_host,
            auth_flow="ios_encrypted",
            user_id=session.user_id,
            cloud_url=session.cloud_url,
            cloud_region=session.cloud_region,
        )
        if persist:
            self.store.save(refreshed)
        return refreshed

    def refresh_iot_tokens(self, session: TclSession | None = None) -> RefreshTokensResult:
        current = session or self.store.load()
        if not current:
            raise RuntimeError("ไม่มี session — login ก่อน")

        user_id = current.user_id
        if not user_id:
            payload = self._parse_jwt_payload(current.token)
            user_id = str(payload.get("username") or "")
        if not user_id:
            raise RuntimeError("session ไม่มี user_id — login ใหม่ด้วย `login` (HA mode)")

        cloud_url = current.cloud_url
        if not cloud_url:
            cloud = get_cloud_urls(self._session, user_id=user_id, sso_token=current.token)
            cloud_url = cloud.cloud_url
            current.cloud_url = cloud.cloud_url
            current.cloud_region = cloud.cloud_region
            current.user_id = user_id
            self.store.save(current)

        return ha_refresh_tokens(
            self._session,
            cloud_url=cloud_url,
            user_id=user_id,
            sso_token=current.token,
        )

    def probe_sso_token(self, token: str) -> dict[str, Any]:
        """ทดสอบว่า sso token ยัง valid กับ IoT API ไหม (loadBalance)."""
        from tcl_iot.client import TclIotClient

        try:
            TclIotClient(token).load_balance()
            return {"valid": True}
        except Exception as exc:
            return {"valid": False, "error": str(exc)}

    @staticmethod
    def _parse_jwt_payload(token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("JWT ไม่ถูกต้อง")
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))

    @classmethod
    def should_refresh_token(cls, token: str, threshold_ratio: float = DEFAULT_REFRESH_THRESHOLD) -> bool:
        payload = cls._parse_jwt_payload(token)
        exp = payload.get("exp")
        iat = payload.get("iat")
        if not exp or not iat:
            return True
        total = (exp - iat) * 1000
        remaining = exp * 1000 - int(time.time() * 1000)
        if total <= 0:
            return True
        return (remaining / total) <= threshold_ratio

    @classmethod
    def token_status(cls, session: TclSession, threshold_ratio: float = DEFAULT_REFRESH_THRESHOLD) -> TokenStatus:
        payload = cls._parse_jwt_payload(session.token)
        exp = payload.get("exp")
        iat = payload.get("iat")
        remaining_ratio = None
        if exp and iat:
            total = (exp - iat) * 1000
            remaining = exp * 1000 - int(time.time() * 1000)
            remaining_ratio = remaining / total if total > 0 else 0.0
        return TokenStatus(
            token=session.token,
            refresh_token=session.refresh_token,
            login_account=session.login_account,
            remaining_ratio=remaining_ratio,
            should_refresh=cls.should_refresh_token(session.token, threshold_ratio),
            expires_at=exp,
        )

    def ensure_token(
        self,
        *,
        allow_login: bool = False,
        allow_refresh: bool = False,
        account: str | None = None,
        password: str | None = None,
        country_code: str = "66",
    ) -> TclSession:
        session = self.store.load()
        if session:
            payload = self._parse_jwt_payload(session.token)
            exp = payload.get("exp")
            expired = exp and exp * 1000 <= int(time.time() * 1000)
            near_expiry = self.should_refresh_token(session.token, self.refresh_threshold)
            if expired or (allow_refresh and near_expiry):
                if session.auth_flow == "ha" or self.auth_mode == "ha":
                    if not allow_refresh and not allow_login:
                        if expired:
                            raise RuntimeError(
                                "token หมดอายุแล้ว — ใช้ login หรือ ensure --refresh (HA login อาจ kick session แอพ)"
                            )
                        return session
                    cred_account = account or os.environ.get("TCL_ACCOUNT") or session.username
                    cred_password = password or os.environ.get("TCL_PASSWORD")
                    if not cred_password:
                        raise RuntimeError("token ใกล้หมด/หมดแล้ว — ต้องมี TCL_PASSWORD สำหรับ HA re-login")
                    return self.login_ha(
                        cred_account,
                        cred_password,
                        country_code=country_code,
                    )
                if allow_refresh and near_expiry:
                    return self.refresh_ios_encrypted(session)
                if expired:
                    raise RuntimeError(
                        "token หมดอายุแล้ว — import จากแอพ/Burp หรือใช้ TCL_AUTH_MODE=ha แล้ว login"
                    )
            return session
        if allow_login:
            if not account or not password:
                account = account or os.environ.get("TCL_ACCOUNT")
                password = password or os.environ.get("TCL_PASSWORD")
            if not account or not password:
                raise RuntimeError("ไม่มี session และไม่ได้ส่ง username/password สำหรับ login")
            return self.login(account, password, country_code=country_code)
        raise RuntimeError(
            "ไม่มี session ที่ใช้ได้ — ใช้ `login` หรือ `import` token จากแอป"
        )

    def test_coexistence(
        self,
        account: str | None = None,
        password: str | None = None,
        *,
        country_code: str = "66",
        persist_new_session: bool = False,
    ) -> dict[str, Any]:
        """Login แบบ HA แล้วทดสอบว่า token เก่า (จาก session ปัจจุบัน) ยังใช้ได้ไหม."""
        account = account or os.environ.get("TCL_ACCOUNT")
        password = password or os.environ.get("TCL_PASSWORD")
        if not account or not password:
            raise RuntimeError("ต้องมี TCL_ACCOUNT และ TCL_PASSWORD ใน .env")

        previous = self.store.load()
        old_token = previous.token if previous else None
        old_probe = self.probe_sso_token(old_token) if old_token else {"valid": False, "error": "no previous session"}

        new_session = self.login_ha(account, password, country_code=country_code, persist=persist_new_session)
        new_probe = self.probe_sso_token(new_session.token)
        old_probe_after = self.probe_sso_token(old_token) if old_token else {"valid": False, "error": "no previous session"}

        iot_refresh_ok = False
        iot_error = None
        try:
            self.refresh_iot_tokens(new_session)
            iot_refresh_ok = True
        except Exception as exc:
            iot_error = str(exc)

        ios_kicked = old_token is not None and old_probe.get("valid") and not old_probe_after.get("valid")

        return {
            "had_previous_session": previous is not None,
            "old_token_valid_before": old_probe.get("valid"),
            "old_token_valid_after_ha_login": old_probe_after.get("valid"),
            "new_token_valid": new_probe.get("valid"),
            "ios_session_likely_kicked": ios_kicked,
            "refresh_tokens_ok": iot_refresh_ok,
            "refresh_tokens_error": iot_error,
            "old_token_error_after": old_probe_after.get("error"),
            "new_session_saved": persist_new_session,
            "auth_flow": "ha",
        }

    def import_session(
        self,
        *,
        login_account: str,
        token: str,
        refresh_token: str,
        username: str | None = None,
    ) -> TclSession:
        session = TclSession(
            username=username or login_account,
            login_account=login_account,
            token=token,
            refresh_token=refresh_token,
            client_id=self.client_id,
            account_host=self.account_host,
            auth_flow="import",
        )
        self.store.save(session)
        return session
