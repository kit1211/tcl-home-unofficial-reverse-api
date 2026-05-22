import { loadConfig } from "../config.ts";
import { tokenRemainingRatio, jwtExp } from "../util.ts";
import { getCloudUrl, haLogin } from "./ha.ts";
import { loadSession, saveSession, type Session } from "./session.ts";

function userIdFromToken(token: string): string {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]!)) as Record<string, unknown>;
    return String(payload.username ?? "");
  } catch {
    return "";
  }
}

export async function ensureSession(): Promise<Session> {
  const cfg = loadConfig();
  let session = loadSession();

  const stale =
    !session ||
    (jwtExp(session?.token ?? "") !== null &&
      tokenRemainingRatio(session!.token) <= cfg.auth.refreshThreshold);

  if (!stale && session) {
    const userId = session.userId || userIdFromToken(session.token);
    if (!session.cloudUrl && userId) {
      const cloud = await getCloudUrl(cfg, userId, session.token);
      session = { ...session, userId, cloudUrl: cloud.cloudUrl, cloudRegion: cloud.cloudRegion };
      saveSession(session);
    }
    return session;
  }

  const login = await haLogin(cfg, cfg.account.username, cfg.account.password);
  const cloud = await getCloudUrl(cfg, login.userId, login.token);
  session = {
    username: cfg.account.username,
    loginAccount: login.loginAccount,
    token: login.token,
    refreshToken: login.refreshToken,
    userId: login.userId,
    cloudUrl: cloud.cloudUrl,
    cloudRegion: cloud.cloudRegion,
  };
  saveSession(session);
  return session;
}
