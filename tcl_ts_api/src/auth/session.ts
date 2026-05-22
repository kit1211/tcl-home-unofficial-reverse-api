import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { loadConfig, resolvePath } from "../config.ts";

export type Session = {
  username: string;
  loginAccount: string;
  token: string;
  refreshToken: string;
  userId: string;
  cloudUrl: string;
  cloudRegion: string;
};

function sessionPath(): string {
  return resolvePath(loadConfig().auth.sessionFile);
}

export function loadSession(): Session | null {
  const path = sessionPath();
  if (!existsSync(path)) return null;
  const raw = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
  const token = String(raw.token ?? "");
  if (!token) return null;
  return {
    username: String(raw.username ?? raw.login_account ?? ""),
    loginAccount: String(raw.login_account ?? raw.loginAccount ?? ""),
    token,
    refreshToken: String(raw.refresh_token ?? raw.refreshToken ?? ""),
    userId: String(raw.user_id ?? raw.userId ?? ""),
    cloudUrl: String(raw.cloud_url ?? raw.cloudUrl ?? ""),
    cloudRegion: String(raw.cloud_region ?? raw.cloudRegion ?? "ap-southeast-1"),
  };
}

export function saveSession(session: Session): void {
  const path = sessionPath();
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(
    path,
    JSON.stringify(
      {
        username: session.username,
        login_account: session.loginAccount,
        token: session.token,
        refresh_token: session.refreshToken,
        user_id: session.userId,
        cloud_url: session.cloudUrl,
        cloud_region: session.cloudRegion,
        auth_flow: "ha",
      },
      null,
      2,
    ),
  );
}
