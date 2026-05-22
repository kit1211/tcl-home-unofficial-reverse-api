แกะแอพ TCL Home แล้วทำเป็น API

> อยากสั่งเปิดแอร์จากสคริป / Home Assistant แต่ TCL ไม่ให้ API มา เลยต้องแกะแอพเอง

---

## ทำไมต้องแกะ?

มีแอร์ TCL ที่คุมผ่านแอพ **TCL Home** ได้ดี แต่พออยากให้ระบบอื่นเรียกใช้ เช่น สั่งเปิดแอร์จาก Siri แต่ official ดันทำไม่ได้ซะงั้น

TCL ไม่เปิด public API, ไม่มี integration กับ Home Assistant, ไม่มี webhook อะไรเลย  
ทางเดียวคือ **เลียนแบบสิ่งที่แอพมือถือทำ** แล้วห่อเป็น HTTP API ธรรมดา

---

## แกะแล้วเจออะไรบ้าง (spoiler: ไม่ได้ง่ายอย่างที่หวัง)

flow จริงไม่ใช่ "login แล้วยิง endpoint เปิดแอร์" แต่เป็นหลายชั้นซ้อนกัน:

1. **Login บัญชี TCL (HA auth)** — รหัสผ่านส่งเป็น MD5, มี header แปลกๆ (`th_platform`, `th_version`, `th_appbulid` …) ปลอมว่าเป็น Android
2. **ขอ cloud URL** — endpoint แยก ใช้ SSO token หา region / cloud ของ user
3. **loadBalance** — ได้ Cognito identity + MQTT endpoint + token ชุดใหม่, พร้อม header `Sign = md5(timestamp + nonce + accessToken)` ที่ต้องคำนวณทุกครั้ง
4. **AWS Cognito** — แลก identity เป็น AWS credentials ชั่วคราว
5. **AWS IoT Device Shadow** — อ่าน/เขียนสถานะแอร์ผ่าน shadow topic ไม่ใช่ REST ตรงๆ

ปัญหาที่เจอระหว่างทาง:

| อาการ | สาเหตุ |
|--------|--------|
| login 403 / rejected | header version ไม่ตรงกับที่ server คาด |
| loadBalance ล้ม | `Sign` หรือ `Nonce`/`Timestamp` ผิด |
| อ่าน shadow ไม่ได้ | Cognito creds หมดอายุ / endpoint region ผิด |
| สั่งเปิดแอร์แล้วไม่ติด | ต้อง publish ไป `$aws/things/{deviceId}/shadow/update` ไม่ใช่ API ทั่วไป |

สรุป: แอพ TCL Home คือ **mobile client ที่คุยกับ AWS IoT ผ่าน Cognito** ไม่ใช่ backend ธรรมดา

---

## แกะด้วยอะไร?

- **ดัก traffic (Burp)** — จับ request Login-logout จริงตอนเปิด-ปิดแอร์ในแอพ ดู URL, header, body
- **decompile APK (jadx)** — ไล่หา endpoint, ชื่อ field, logic sign / MD5 password
- **ลองยิงซ้ำทีละชั้น** — login → cloud URL → loadBalance → Cognito → shadow จนแต่ละ step ผ่าน
- **เก็บค่าที่พังง่ายไว้ที่เดียว** — version / User-Agent อยู่ใน `src/env.ts` เผื่อแอพอัปเดตแล้วต้องแก้

---

## จบด้วยอะไร?

โปรเจคนี้ห่อทุกอย่างไว้เป็น **Bun HTTP server** ที่ใช้งานง่าย:

```
login + session cache  →  loadBalance + Cognito  →  IoT Shadow  →  แอร์เปลี่ยนจริง
```

คุณแค่ยิง REST:

| Method | Path | ทำอะไร |
|--------|------|--------|
| `GET` | `/api/ac/status` | อ่านสถานะแอร์ |
| `POST` | `/api/ac/power` | `{ "on": true }` เปิด/ปิด |
| `POST` | `/api/ac/temperature` | `{ "value": 25 }` หรือ `{ "delta": -1 }` |
| `GET` | `/health` | ตรวจว่า server ยังอยู่ |

session เก็บใน `session.json` อัตโนมัติ — login ครั้งแรกแล้วใช้ต่อได้ ไม่ต้อง login ทุก request

---

## เอาไปใช้ต่อยังไง?

### 1. เตรียม config

```bash
cp config.example.json config.json
```

แก้ใน `config.json`:

- `account.username` / `password` — บัญชี TCL Home (เบอร์หรือ email)
- `iot.deviceId` — รหัสอุปกรณ์แอร์ (ดักจาก traffic หรือดูในแอพ)
- endpoint อื่นๆ ใช้ค่า default ได้ถ้า region เดียวกัน

### 2. รัน

**แบบ local (Bun):**

```bash
bun install
bun start
# → http://localhost:3100
```

**แบบ Docker:**

```bash
docker compose up -d --build
docker compose logs -f
```

### 3. ลองสั่งแอร์

```bash
curl http://localhost:3100/api/ac/status
curl -X POST http://localhost:3100/api/ac/power \
  -H 'Content-Type: application/json' -d '{"on":true}'
curl -X POST http://localhost:3100/api/ac/temperature \
  -H 'Content-Type: application/json' -d '{"delta":-1}'
```

จากนั้นเอาไปผูก Home Assistant (`rest` command), Node-RED, cron, หรืออะไรก็ได้ที่ยิง HTTP ได้

---

## โครงสร้างโปรเจค (ถ้าอยากแกะต่อ)

```
tcl_ts_api/
  config.json       ← credentials + deviceId (gitignore)
  session.json      ← token อัตโนมัติ (gitignore)
  src/
    env.ts          ← app version / headers (แก้ตรงนี้เมื่อ TCL อัปเดตแอพ)
    auth/           ← HA login + session cache
    iot/            ← loadBalance → Cognito → shadow
    server.ts       ← REST routes
```

---

## ข้อควรรู้

- โปรเจคนี้ **ไม่ใช่ของ official TCL** — ใช้ความเสี่ยงของตัวเอง, account อาจโดน rate-limit ถ้ายิงถี่เกิน
- ถ้า login พังหลังแอพอัปเดต → ลองแก้ `src/env.ts` ให้ version ตรงกับแอพล่าสุด
- `config.json` มีรหัสผ่าน — **อย่า commit**, อย่า expose port 3100 ออก internet ตรงๆ

---

*แกะมาเพราะอยากนอนห้องเย็นโดยไม่ต้องเปิดแอพ — แชร์ไว้ให้คนที่มีปัญหาเดียวกัน*
