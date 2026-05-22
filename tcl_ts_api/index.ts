import { createServer } from "./src/server.ts";
import { loadConfig } from "./src/config.ts";

const cfg = loadConfig();
const server = createServer();

console.log(`tcl_ts_api listening on http://${cfg.server.host ?? "0.0.0.0"}:${cfg.server.port}`);

export { server };
