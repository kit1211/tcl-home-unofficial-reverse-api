from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from .crypto import md5_hex


DEFAULT_HA_LOGIN_URL = "https://pa.account.tcl.com/account/login?clientId=54148614"
DEFAULT_CLOUD_URLS_ENDPOINT = "https://prod-center.aws.tcljd.com/v3/global/cloud_url_get"
DEFAULT_HA_APP_ID = "wx6e1af3fa84fbe523"

HA_ANDROID_HEADERS = {
    "th_platform": "android",
    "th_version": "4.8.1",
    "th_appbulid": "830",
    "user-agent": "Android",
    "content-type": "application/json; charset=UTF-8",
}


@dataclass
class HaLoginResult:
    token: str
    refresh_token: str
    login_account: str
    user_id: str
    country_abbr: str | None
    raw: dict[str, Any]


@dataclass
class CloudUrlsResult:
    cloud_url: str
    cloud_region: str
    device_url: str
    identity_pool_id: str | None
    raw: dict[str, Any]


@dataclass
class RefreshTokensResult:
    saas_token: str
    cognito_token: str
    cognito_id: str
    mqtt_endpoint: str
    raw: dict[str, Any]


def ha_login_body(username: str, password: str) -> dict[str, Any]:
    return {
        "equipment": int(os.environ.get("TCL_HA_EQUIPMENT", "2")),
        "password": md5_hex(password),
        "osType": int(os.environ.get("TCL_HA_OS_TYPE", "1")),
        "username": username,
        "clientVersion": os.environ.get("TCL_HA_APP_VERSION", "4.8.1"),
        "osVersion": os.environ.get("TCL_HA_OS_VERSION", "6.0"),
        "deviceModel": os.environ.get("TCL_HA_DEVICE_MODEL", "AndroidAndroid SDK built for x86"),
        "captchaRule": 2,
        "channel": "app",
    }


def do_ha_login(
    session: requests.Session,
    *,
    username: str,
    password: str,
    login_url: str | None = None,
) -> HaLoginResult:
    url = login_url or os.environ.get("TCL_HA_LOGIN_URL", DEFAULT_HA_LOGIN_URL)
    response = session.post(
        url,
        json=ha_login_body(username, password),
        headers=HA_ANDROID_HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != 1:
        raise RuntimeError(f"HA login ล้มเหลว: {payload.get('msg') or payload}")
    user = payload.get("user") or {}
    data = payload.get("data") or {}
    token = payload.get("token") or ""
    refresh_token = payload.get("refreshtoken") or payload.get("refreshToken") or ""
    if not token or not refresh_token:
        raise RuntimeError("HA login response ไม่มี token/refreshtoken")
    user_id = str(user.get("username") or "")
    if not user_id:
        raise RuntimeError("HA login response ไม่มี user.username (sso user id)")
    return HaLoginResult(
        token=token,
        refresh_token=refresh_token,
        login_account=data.get("loginAccount") or username,
        user_id=user_id,
        country_abbr=user.get("countryAbbr") or user.get("country_abbr"),
        raw=payload,
    )


def get_cloud_urls(
    session: requests.Session,
    *,
    user_id: str,
    sso_token: str,
    cloud_urls_endpoint: str | None = None,
) -> CloudUrlsResult:
    url = cloud_urls_endpoint or os.environ.get("TCL_CLOUD_URLS_ENDPOINT", DEFAULT_CLOUD_URLS_ENDPOINT)
    response = session.post(
        url,
        json={"ssoId": user_id, "ssoToken": sso_token},
        headers={"user-agent": "Android", "content-type": "application/json; charset=UTF-8"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") not in (0, 200, "200", "0", None) and payload.get("message") not in ("SUCCESS", "成功", None):
        if payload.get("code") != 0:
            raise RuntimeError(f"cloud_url_get ล้มเหลว: {payload.get('message') or payload}")
    data = payload.get("data") or {}
    cloud_url = data.get("cloud_url") or data.get("cloudUrl") or ""
    if not cloud_url:
        raise RuntimeError(f"cloud_url_get ไม่มี cloud_url: {payload}")
    return CloudUrlsResult(
        cloud_url=cloud_url.rstrip("/"),
        cloud_region=data.get("cloud_region") or data.get("cloudRegion") or "ap-southeast-1",
        device_url=(data.get("device_url") or data.get("deviceUrl") or cloud_url).rstrip("/"),
        identity_pool_id=data.get("identity_pool_id") or data.get("identityPoolId"),
        raw=payload,
    )


def refresh_tokens(
    session: requests.Session,
    *,
    cloud_url: str,
    user_id: str,
    sso_token: str,
    app_id: str | None = None,
) -> RefreshTokensResult:
    app_id = app_id or os.environ.get("TCL_HA_APP_ID", DEFAULT_HA_APP_ID)
    url = f"{cloud_url.rstrip('/')}/v3/auth/refresh_tokens"
    response = session.post(
        url,
        json={"userId": user_id, "ssoToken": sso_token, "appId": app_id},
        headers={
            "user-agent": "Android",
            "content-type": "application/json; charset=UTF-8",
            "accept-encoding": "gzip, deflate, br",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    code = payload.get("code")
    if code not in (0, 200, "200", "0"):
        raise RuntimeError(f"refresh_tokens ล้มเหลว: {payload.get('message') or payload}")
    data = payload.get("data") or {}
    saas_token = data.get("saasToken") or data.get("saas_token") or ""
    cognito_token = data.get("cognitoToken") or data.get("cognito_token") or ""
    cognito_id = data.get("cognitoId") or data.get("cognito_id") or ""
    mqtt_endpoint = data.get("mqttEndpoint") or data.get("mqtt_endpoint") or ""
    if not saas_token or not cognito_token:
        raise RuntimeError(f"refresh_tokens ไม่ครบ field: {payload}")
    return RefreshTokensResult(
        saas_token=saas_token,
        cognito_token=cognito_token,
        cognito_id=cognito_id,
        mqtt_endpoint=mqtt_endpoint,
        raw=payload,
    )
