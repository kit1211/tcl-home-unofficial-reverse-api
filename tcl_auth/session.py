from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class TclSession:
    username: str
    login_account: str
    token: str
    refresh_token: str
    client_id: str = "54148614"
    account_host: str = "sg.account.tcl.com"
    auth_flow: str = "ha"
    user_id: str | None = None
    cloud_url: str | None = None
    cloud_region: str | None = None

    @classmethod
    def from_api_response(
        cls,
        *,
        username: str,
        response: dict[str, Any],
        client_id: str = "54148614",
        account_host: str = "sg.account.tcl.com",
        auth_flow: str = "ios_encrypted",
        user_id: str | None = None,
        cloud_url: str | None = None,
        cloud_region: str | None = None,
    ) -> "TclSession":
        data = response.get("data") or {}
        login_account = data.get("loginAccount") or username
        token = response.get("token") or ""
        refresh_token = response.get("refreshtoken") or response.get("refreshToken") or ""
        if not token or not refresh_token:
            raise ValueError("response ไม่มี token หรือ refreshtoken")
        user = response.get("user") or {}
        resolved_user_id = user_id or (str(user.get("username")) if user.get("username") else None)
        return cls(
            username=username,
            login_account=login_account,
            token=token,
            refresh_token=refresh_token,
            client_id=client_id,
            account_host=account_host,
            auth_flow=auth_flow,
            user_id=resolved_user_id,
            cloud_url=cloud_url,
            cloud_region=cloud_region,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TclSession":
        return cls(
            username=payload["username"],
            login_account=payload.get("login_account") or payload["username"],
            token=payload["token"],
            refresh_token=payload["refresh_token"],
            client_id=payload.get("client_id", "54148614"),
            account_host=payload.get("account_host", "sg.account.tcl.com"),
            auth_flow=payload.get("auth_flow", "ha"),
            user_id=payload.get("user_id"),
            cloud_url=payload.get("cloud_url"),
            cloud_region=payload.get("cloud_region"),
        )


class SessionStore:
    def __init__(self, path: str | Path | None = None) -> None:
        default = Path.home() / ".tcl-home" / "session.json"
        raw = path or os.environ.get("TCL_SESSION_FILE", default)
        self.path = Path(str(raw).replace("~", str(Path.home()), 1)).expanduser()

    def load(self) -> TclSession | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return TclSession.from_dict(payload)

    def save(self, session: TclSession) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
