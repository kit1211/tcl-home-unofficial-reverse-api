import { loadConfig } from "./config.ts";
import { ensureSession } from "./auth/index.ts";
import { adjustAcTemperature, getAcStatus, setAcPower, setAcTemperature } from "./iot/ac.ts";
import { servePublic } from "./static.ts";

function json(data: unknown, status = 200): Response {
  return Response.json(data, { status });
}

function err(message: string, status = 400): Response {
  return json({ ok: false, error: message }, status);
}

async function readBody(req: Request): Promise<Record<string, unknown>> {
  try {
    return (await req.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

export function createServer() {
  const cfg = loadConfig();

  return Bun.serve({
    hostname: cfg.server.host ?? "0.0.0.0",
    port: cfg.server.port,
    routes: {
      "/": () => servePublic("index.html") ?? err("UI not found", 404),
      "/styles.css": () => servePublic("styles.css") ?? err("not found", 404),
      "/app.js": () => servePublic("app.js") ?? err("not found", 404),

      "/api/devices": {
        GET: () =>
          json({
            ok: true,
            data: [
              {
                id: cfg.iot.deviceId,
                type: "air_conditioner",
                label: "TCL Air Conditioner",
                region: cfg.iot.region,
                tempMin: cfg.iot.tempMin,
                tempMax: cfg.iot.tempMax,
                tempStep: cfg.iot.tempStep,
              },
            ],
          }),
      },
      "/api/ac/status": {
        GET: async () => {
          try {
            const session = await ensureSession();
            const status = await getAcStatus(session);
            return json({ ok: true, data: status });
          } catch (e) {
            return err(e instanceof Error ? e.message : String(e), 500);
          }
        },
      },
      "/api/ac/power": {
        POST: async (req) => {
          try {
            const body = await readBody(req);
            if (typeof body.on !== "boolean") return err('ต้องส่ง { "on": true|false }');
            const session = await ensureSession();
            const payload = await setAcPower(session, body.on);
            return json({ ok: true, on: body.on, payload });
          } catch (e) {
            return err(e instanceof Error ? e.message : String(e), 500);
          }
        },
      },
      "/api/ac/temperature": {
        POST: async (req) => {
          try {
            const body = await readBody(req);
            const session = await ensureSession();

            if (typeof body.value === "number") {
              const result = await setAcTemperature(session, body.value);
              return json({ ok: true, ...result });
            }
            if (typeof body.delta === "number") {
              const result = await adjustAcTemperature(session, body.delta);
              return json({ ok: true, ...result });
            }
            return err('ต้องส่ง { "delta": 1|-1 } หรือ { "value": 25 }');
          } catch (e) {
            return err(e instanceof Error ? e.message : String(e), 500);
          }
        },
      },
      "/health": { GET: () => json({ ok: true }) },
    },
    fetch(req) {
      const url = new URL(req.url);
      const asset = servePublic(url.pathname.slice(1));
      if (asset) return asset;

      return Response.json(
        {
          ok: false,
          error: "not found",
          routes: [
            "GET /",
            "GET /api/devices",
            "GET /api/ac/status",
            "POST /api/ac/power",
            "POST /api/ac/temperature",
            "GET /health",
          ],
        },
        { status: 404 },
      );
    },
  });
}
