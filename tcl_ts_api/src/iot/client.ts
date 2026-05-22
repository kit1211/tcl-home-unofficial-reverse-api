import {
  GetThingShadowCommand,
  IoTDataPlaneClient,
  PublishCommand,
} from "@aws-sdk/client-iot-data-plane";
import { APP_ENV } from "../env.ts";
import { loadConfig, type AppConfig } from "../config.ts";
import { clientToken, iotNonce, md5 } from "../util.ts";
import type { Session } from "../auth/session.ts";

export type AwsCreds = {
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken: string;
};

export type LoadBalance = {
  cognitoId: string;
  cognitoToken: string;
  mqttEndpoint: string;
  saasToken: string;
};

type IotContext = {
  lb: LoadBalance;
  creds: AwsCreds;
  endpoint: string;
  at: number;
};

let ctx: IotContext | null = null;
const CTX_TTL_MS = 45 * 60 * 1000;

function iotHeaders(cfg: AppConfig, ssoToken: string, accessToken = ""): Record<string, string> {
  const env = APP_ENV.iot;
  const timestamp = String(Date.now());
  const nonce = iotNonce();
  return {
    Accept: "*/*",
    "Content-Type": "application/json",
    "User-Agent": env.userAgent,
    Platform: env.platform,
    Appversion: env.appVersion,
    Thomeversion: env.thomeVersion,
    "Accept-Language": env.acceptLanguage,
    Appid: cfg.iot.appId,
    Ssotoken: ssoToken,
    Timestamp: timestamp,
    Nonce: nonce,
    Sign: md5(timestamp + nonce + accessToken),
    Countrycode: cfg.iot.countryCode,
    Accesstoken: accessToken,
    Timezone: cfg.iot.timezone,
  };
}

function mqttDataEndpoint(mqttEndpoint: string): string {
  const host = mqttEndpoint.replace(/^wss:\/\//, "").replace(/:\d+$/, "");
  return `https://${host}`;
}

export async function getIotContext(session: Session): Promise<IotContext> {
  if (ctx && Date.now() - ctx.at < CTX_TTL_MS) return ctx;

  const cfg = loadConfig();
  const lbRes = await fetch(`https://${cfg.iot.host}/v1/auth/service/loadBalance`, {
    headers: iotHeaders(cfg, session.token),
  });
  if (!lbRes.ok) throw new Error(`loadBalance HTTP ${lbRes.status}`);
  const lbPayload = (await lbRes.json()) as Record<string, unknown>;
  if (lbPayload.code !== 200) throw new Error(`loadBalance: ${lbPayload.message ?? "failed"}`);

  const data = (lbPayload.data ?? {}) as Record<string, unknown>;
  const lb: LoadBalance = {
    cognitoId: String(data.cognitoId ?? ""),
    cognitoToken: String(data.cognitoToken ?? ""),
    mqttEndpoint: String(data.mqttEndpoint ?? ""),
    saasToken: String(data.saasToken ?? ""),
  };
  if (!lb.cognitoId || !lb.cognitoToken || !lb.mqttEndpoint) {
    throw new Error("loadBalance: incomplete data");
  }

  const credRes = await fetch(`https://${cfg.iot.cognitoHost}/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
    },
    body: JSON.stringify({
      IdentityId: lb.cognitoId,
      Logins: { "cognito-identity.amazonaws.com": lb.cognitoToken },
    }),
  });
  if (!credRes.ok) throw new Error(`Cognito HTTP ${credRes.status}`);
  const credPayload = (await credRes.json()) as Record<string, unknown>;
  const c = (credPayload.Credentials ?? {}) as Record<string, unknown>;
  if (!c.AccessKeyId) throw new Error("Cognito: no credentials");

  ctx = {
    lb,
    creds: {
      accessKeyId: String(c.AccessKeyId),
      secretAccessKey: String(c.SecretKey),
      sessionToken: String(c.SessionToken),
    },
    endpoint: mqttDataEndpoint(lb.mqttEndpoint),
    at: Date.now(),
  };
  return ctx;
}

function iotClient(context: IotContext, region: string): IoTDataPlaneClient {
  return new IoTDataPlaneClient({
    region,
    endpoint: context.endpoint,
    credentials: context.creds,
  });
}

export async function getDeviceShadow(session: Session, deviceId: string) {
  const cfg = loadConfig();
  const context = await getIotContext(session);
  const client = iotClient(context, cfg.iot.region);
  const out = await client.send(new GetThingShadowCommand({ thingName: deviceId }));
  const raw = out.payload ? JSON.parse(new TextDecoder().decode(out.payload)) : {};
  return raw as {
    state?: {
      reported?: Record<string, unknown>;
      desired?: Record<string, unknown>;
    };
  };
}

export async function updateDeviceShadow(
  session: Session,
  deviceId: string,
  desired: Record<string, unknown>,
) {
  const cfg = loadConfig();
  const context = await getIotContext(session);
  const client = iotClient(context, cfg.iot.region);
  const payload = {
    state: { desired },
    clientToken: clientToken(),
  };
  const topic = `$aws/things/${deviceId}/shadow/update`;
  await client.send(
    new PublishCommand({
      topic,
      qos: 1,
      payload: new TextEncoder().encode(JSON.stringify(payload)),
    }),
  );
  return { topic, payload };
}
