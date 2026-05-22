from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import boto3
import requests

from tcl_auth.crypto import md5_hex


DEFAULT_IOT_HOST = "sgp-iot-api-prod.tcljd.com"
DEFAULT_IOT_APP_ID = "f6hek6hdpt64jrw596"
DEFAULT_DEVICE_ID = "DBbPYSvgAAE"
DEFAULT_COUNTRY_CODE = "TH"
DEFAULT_TIMEZONE = "Asia/Bangkok"
COGNITO_IDENTITY_HOST = "cognito-identity.ap-southeast-1.amazonaws.com"


@dataclass
class LoadBalanceResult:
    cognito_id: str
    cognito_token: str
    mqtt_endpoint: str
    saas_token: str
    user_id: str


@dataclass
class AwsCredentials:
    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: float | None = None


class TclIotClient:
    def __init__(
        self,
        sso_token: str,
        *,
        iot_host: str | None = None,
        app_id: str | None = None,
        country_code: str | None = None,
        timezone: str | None = None,
    ) -> None:
        self.sso_token = sso_token
        self.iot_host = iot_host or os.environ.get("TCL_IOT_HOST", DEFAULT_IOT_HOST)
        self.app_id = app_id or os.environ.get("TCL_IOT_APP_ID", DEFAULT_IOT_APP_ID)
        self.country_code = country_code or os.environ.get("TCL_IOT_COUNTRY_CODE", DEFAULT_COUNTRY_CODE)
        self.timezone = timezone or os.environ.get("TCL_IOT_TIMEZONE", DEFAULT_TIMEZONE)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "*/*",
                "Content-Type": "application/json",
                "User-Agent": os.environ.get(
                    "TCL_USER_AGENT",
                    "TCLHome/6.1.3 (iPhone; iOS 26.4.2; Scale/3.00)",
                ),
                "Platform": os.environ.get("TCL_PLATFORM", "ios"),
                "Appversion": os.environ.get("TCL_IOT_APP_VERSION", "7.4.0"),
                "Thomeversion": os.environ.get("TCL_APP_VERSION", "6.1.3"),
                "Accept-Language": os.environ.get("TCL_IOT_ACCEPT_LANGUAGE", "th"),
            }
        )

    @staticmethod
    def _client_token() -> str:
        return f"mobile_{int(time.time() * 1000)}"

    def _iot_headers(self, *, access_token: str = "") -> dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        nonce = str(uuid.uuid4()).upper()
        sign = md5_hex(timestamp + nonce + access_token)
        return {
            "Appid": self.app_id,
            "Ssotoken": self.sso_token,
            "Timestamp": timestamp,
            "Nonce": nonce,
            "Sign": sign,
            "Countrycode": self.country_code,
            "Accesstoken": access_token,
            "Timezone": self.timezone,
        }

    def load_balance(self) -> LoadBalanceResult:
        url = f"https://{self.iot_host}/v1/auth/service/loadBalance"
        response = self._session.get(url, headers=self._iot_headers(), timeout=30)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            raise RuntimeError(f"loadBalance ล้มเหลว: {payload.get('message') or payload}")
        data = payload.get("data") or {}
        required = ("cognitoId", "cognitoToken", "mqttEndpoint", "saasToken")
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise RuntimeError(f"loadBalance ไม่ครบ field: {', '.join(missing)}")
        return LoadBalanceResult(
            cognito_id=data["cognitoId"],
            cognito_token=data["cognitoToken"],
            mqtt_endpoint=data["mqttEndpoint"],
            saas_token=data["saasToken"],
            user_id=str(data.get("userId") or ""),
        )

    def get_aws_credentials(self, load_balance: LoadBalanceResult) -> AwsCredentials:
        response = requests.post(
            f"https://{COGNITO_IDENTITY_HOST}/",
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
            },
            json={
                "IdentityId": load_balance.cognito_id,
                "Logins": {"cognito-identity.amazonaws.com": load_balance.cognito_token},
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        creds = payload.get("Credentials") or {}
        if not creds.get("AccessKeyId"):
            raise RuntimeError(f"GetCredentialsForIdentity ล้มเหลว: {payload}")
        return AwsCredentials(
            access_key_id=creds["AccessKeyId"],
            secret_access_key=creds["SecretKey"],
            session_token=creds["SessionToken"],
            expiration=creds.get("Expiration"),
        )

    @staticmethod
    def _iot_data_endpoint(mqtt_endpoint: str) -> str:
        parsed = urlparse(mqtt_endpoint)
        host = parsed.hostname or mqtt_endpoint.replace("wss://", "").replace("https://", "").split(":")[0]
        return f"https://{host}"

    def publish_shadow(
        self,
        *,
        device_id: str,
        desired: dict[str, Any],
        load_balance: LoadBalanceResult,
        credentials: AwsCredentials,
    ) -> dict[str, Any]:
        topic = f"$aws/things/{device_id}/shadow/update"
        payload = {
            "state": {"desired": desired},
            "clientToken": self._client_token(),
        }
        body = json.dumps(payload, separators=(",", ":"))
        client = boto3.client(
            "iot-data",
            region_name="ap-southeast-1",
            endpoint_url=self._iot_data_endpoint(load_balance.mqtt_endpoint),
            aws_access_key_id=credentials.access_key_id,
            aws_secret_access_key=credentials.secret_access_key,
            aws_session_token=credentials.session_token,
        )
        client.publish(topic=topic, qos=1, payload=body)
        return {"topic": topic, "payload": payload}

    def set_power(
        self,
        *,
        device_id: str,
        on: bool,
        load_balance: LoadBalanceResult | None = None,
        credentials: AwsCredentials | None = None,
    ) -> dict[str, Any]:
        lb = load_balance or self.load_balance()
        creds = credentials or self.get_aws_credentials(lb)
        return self.publish_shadow(
            device_id=device_id,
            desired={"powerSwitch": 1 if on else 0},
            load_balance=lb,
            credentials=creds,
        )
