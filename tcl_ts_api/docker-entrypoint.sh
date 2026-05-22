#!/bin/sh
set -e

PERSIST_DIR=/usr/src/app/persist
SESSION_FILE="$PERSIST_DIR/session.json"

mkdir -p "$PERSIST_DIR"
[ -f "$SESSION_FILE" ] || echo '{}' > "$SESSION_FILE"
ln -sf "$SESSION_FILE" /usr/src/app/session.json
chown -R bun:bun "$PERSIST_DIR"

exec runuser -u bun -- bun run index.ts
