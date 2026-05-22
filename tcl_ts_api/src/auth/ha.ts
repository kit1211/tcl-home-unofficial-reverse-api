import { APP_ENV } from "../env.ts";
import { md5, normalizeUsername } from "../util.ts";
import type { AppConfig } from "../config.ts";

export type HaLoginResult = {
  token: string;
  refreshToken: string;
  loginAccount: string;
  userId: string;
};

export async function haLogin(
  cfg: AppConfig,
  account: string,
  password: string,
): Promise<HaLoginResult> {
  const username = normalizeUsername(account, cfg.account.countryCode);
  const env = APP_ENV.ha;
  const res = await fetch(cfg.auth.loginUrl, {
    method: "POST",
    headers: {
      "content-type": "application/json; charset=UTF-8",
      "th_platform": env.platform,
      "th_version": env.version,
      "th_appbulid": env.appBuild,
      "user-agent": env.userAgent,
    },
    body: JSON.stringify({
      equipment: env.equipment,
      password: md5(password),
      osType: env.osType,
      username,
      clientVersion: env.clientVersion,
      osVersion: env.osVersion,
      deviceModel: env.deviceModel,
      captchaRule: 2,
      channel: "app",
    }),
  });
  if (!res.ok) throw new Error(`HA login HTTP ${res.status}`);
  const payload = (await res.json()) as Record<string, unknown>;
  if (payload.status !== 1) throw new Error(`HA login: ${payload.msg ?? "failed"}`);

  const user = (payload.user ?? {}) as Record<string, unknown>;
  const data = (payload.data ?? {}) as Record<string, unknown>;
  const token = String(payload.token ?? "");
  const refreshToken = String(payload.refreshtoken ?? payload.refreshToken ?? "");
  const userId = String(user.username ?? "");
  if (!token || !refreshToken || !userId) throw new Error("HA login: missing token/userId");

  return {
    token,
    refreshToken,
    loginAccount: String(data.loginAccount ?? username),
    userId,
  };
}

export async function getCloudUrl(
  cfg: AppConfig,
  userId: string,
  ssoToken: string,
): Promise<{ cloudUrl: string; cloudRegion: string }> {
  const res = await fetch(cfg.auth.cloudUrlsEndpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json; charset=UTF-8",
      "user-agent": APP_ENV.ha.userAgent,
    },
    body: JSON.stringify({ ssoId: userId, ssoToken }),
  });
  if (!res.ok) throw new Error(`cloud_url_get HTTP ${res.status}`);
  const payload = (await res.json()) as Record<string, unknown>;
  const data = (payload.data ?? {}) as Record<string, unknown>;
  const cloudUrl = String(data.cloud_url ?? data.cloudUrl ?? "").replace(/\/$/, "");
  if (!cloudUrl) throw new Error("cloud_url_get: no cloud_url");
  return {
    cloudUrl,
    cloudRegion: String(data.cloud_region ?? data.cloudRegion ?? "ap-southeast-1"),
  };
}
