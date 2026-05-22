import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export type AppConfig = {
  server: { port: number; host?: string };
  account: { username: string; password: string; countryCode: string };
  auth: {
    loginUrl: string;
    cloudUrlsEndpoint: string;
    haAppId: string;
    clientId: string;
    sessionFile: string;
    refreshThreshold: number;
  };
  iot: {
    host: string;
    appId: string;
    deviceId: string;
    countryCode: string;
    timezone: string;
    region: string;
    cognitoHost: string;
    tempMin: number;
    tempMax: number;
    tempStep: number;
  };
};

const ROOT = join(import.meta.dir, "..");
const CONFIG_PATH = join(ROOT, "config.json");

let cached: AppConfig | null = null;

export function loadConfig(): AppConfig {
  if (cached) return cached;
  if (!existsSync(CONFIG_PATH)) {
    throw new Error(`ไม่พบ config.json — copy จาก config.example.json (${CONFIG_PATH})`);
  }
  cached = JSON.parse(readFileSync(CONFIG_PATH, "utf8")) as AppConfig;
  return cached;
}

export function resolvePath(relative: string): string {
  return join(ROOT, relative);
}
