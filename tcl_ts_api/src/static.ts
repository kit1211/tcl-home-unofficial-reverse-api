import { join } from "node:path";
import { existsSync } from "node:fs";

const PUBLIC_DIR = join(import.meta.dir, "../public");

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

export function servePublic(pathname: string): Response | null {
  const safe = pathname.replace(/^\/+/, "") || "index.html";
  if (safe.includes("..")) return null;

  const filePath = join(PUBLIC_DIR, safe);
  if (!existsSync(filePath)) return null;

  const ext = safe.includes(".") ? safe.slice(safe.lastIndexOf(".")) : ".html";
  const type = MIME[ext] ?? "application/octet-stream";
  return new Response(Bun.file(filePath), { headers: { "Content-Type": type } });
}
