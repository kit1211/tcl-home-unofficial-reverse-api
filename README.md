# tcl-home-unofficial-reverse-api

Unofficial TCL Home API: reverse-engineered auth + AWS IoT shadow control for TCL ACs.

## Components

| Path | Description |
|------|-------------|
| [`tcl_ts_api/`](tcl_ts_api/) | **Bun REST API + web UI** — status, power, temperature |
| `tcl_auth/` | Python HA-style login, session, refresh |
| `tcl_iot/` | Python IoT client (loadBalance → Cognito → shadow) |
| `tcl_ac_cli.py` | CLI: on / off / test |
| `tcl_auth_cli.py` | CLI: login, status, import, coexist test |
| `tcl_burp/` | Burp history time filter helpers |

## Quick start (API)

```bash
cd tcl_ts_api
cp config.example.json config.json   # set account + deviceId
bun install
bun start
```

See [tcl_ts_api/README.md](tcl_ts_api/README.md) for full docs and Docker setup.

## Python CLI

```bash
pip install -r requirements.txt
cp .env.example .env
PYTHONPATH=. python3 tcl_auth_cli.py login
PYTHONPATH=. python3 tcl_ac_cli.py test --seconds 10
```

## Disclaimer

Not affiliated with TCL. Use at your own risk — credentials and tokens stay local (`config.json`, `session.json`, `.env` are gitignored).
