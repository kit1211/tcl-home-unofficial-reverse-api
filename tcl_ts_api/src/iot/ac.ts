import { loadConfig } from "../config.ts";
import type { Session } from "../auth/session.ts";
import { getDeviceShadow, updateDeviceShadow } from "./client.ts";

export type AcStatus = {
  deviceId: string;
  power: boolean | null;
  targetTemperature: number | null;
  currentTemperature: number | null;
  workMode: number | null;
  raw: Record<string, unknown>;
};

function num(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

function pickState(shadow: Awaited<ReturnType<typeof getDeviceShadow>>): Record<string, unknown> {
  return { ...(shadow.state?.reported ?? {}), ...(shadow.state?.desired ?? {}) };
}

export async function getAcStatus(session: Session): Promise<AcStatus> {
  const cfg = loadConfig();
  const shadow = await getDeviceShadow(session, cfg.iot.deviceId);
  const state = pickState(shadow);
  const powerSwitch = state.powerSwitch;
  return {
    deviceId: cfg.iot.deviceId,
    power: powerSwitch === 1 ? true : powerSwitch === 0 ? false : null,
    targetTemperature: num(state.targetTemperature),
    currentTemperature: num(state.currentTemperature),
    workMode: num(state.workMode),
    raw: state,
  };
}

export async function setAcPower(session: Session, on: boolean) {
  const cfg = loadConfig();
  return updateDeviceShadow(session, cfg.iot.deviceId, { powerSwitch: on ? 1 : 0 });
}

export async function adjustAcTemperature(session: Session, delta: number) {
  const cfg = loadConfig();
  const status = await getAcStatus(session);
  const current = status.targetTemperature ?? 24;
  const next = Math.min(
    cfg.iot.tempMax,
    Math.max(cfg.iot.tempMin, current + delta * cfg.iot.tempStep),
  );
  const payload = await updateDeviceShadow(session, cfg.iot.deviceId, {
    targetTemperature: next,
    powerSwitch: 1,
  });
  return { previous: current, target: next, payload };
}

export async function setAcTemperature(session: Session, value: number) {
  const cfg = loadConfig();
  const status = await getAcStatus(session);
  const next = Math.min(cfg.iot.tempMax, Math.max(cfg.iot.tempMin, value));
  const payload = await updateDeviceShadow(session, cfg.iot.deviceId, {
    targetTemperature: next,
    powerSwitch: 1,
  });
  return { previous: status.targetTemperature, target: next, payload };
}
