import { createHash, randomUUID } from "node:crypto";

export function md5(text: string): string {
  return createHash("md5").update(text).digest("hex");
}

export function clientToken(): string {
  return `mobile_${Date.now()}`;
}

export function iotNonce(): string {
  return randomUUID().toUpperCase();
}

export function normalizeUsername(account: string, countryCode: string): string {
  if (account.startsWith("+") || account.includes("@") || !/^\d+$/.test(account)) {
    return account;
  }
  const digits = account.startsWith("0") ? account.slice(1) : account;
  return `+${countryCode}${digits}`;
}

export function jwtExp(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]!));
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

export function tokenRemainingRatio(token: string): number {
  const exp = jwtExp(token);
  if (!exp) return 1;
  const iatGuess = exp - 86400 * 30;
  const span = Math.max(exp - iatGuess, 1);
  return Math.max(0, Math.min(1, (exp * 1000 - Date.now()) / (span * 1000)));
}
