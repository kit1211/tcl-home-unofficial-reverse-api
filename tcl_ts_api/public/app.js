const WORK_MODES = {
  0: "อัตโนมัติ",
  1: "ทำความเย็น",
  2: "ทำความร้อน",
  3: "พัดลม",
  4: "ถ่ายเท",
};

const POLL_MS = 12_000;

/** @type {Map<string, { min: number, max: number, step: number }>} */
const deviceMeta = new Map();

/** @type {ReturnType<typeof setInterval> | null} */
let pollTimer = null;

/** @type {boolean} */
let busy = false;

const $ = (sel, root = document) => root.querySelector(sel);

function setConn(state, text) {
  const badge = $("#connBadge");
  badge.dataset.state = state;
  badge.textContent = text;
}

function setLastUpdated() {
  $("#lastUpdated").textContent = `อัปเดต ${new Date().toLocaleTimeString("th-TH")}`;
}

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await res.json();
  if (!res.ok || body.ok === false) {
    throw new Error(body.error ?? `HTTP ${res.status}`);
  }
  return body;
}

function workModeLabel(mode) {
  if (mode == null) return "—";
  return WORK_MODES[mode] ?? `โหมด ${mode}`;
}

function renderDeviceCard(device, status) {
  const tpl = $("#deviceCardTpl");
  const node = tpl.content.cloneNode(true);
  const card = $(".device-card", node);
  const id = device.id;

  card.dataset.deviceId = id;
  $(".device-label", card).textContent = device.label;
  $(".device-id", card).textContent = id;

  const powerInput = $(".power-input", card);
  const slider = $(".temp-slider", card);
  slider.min = String(device.tempMin);
  slider.max = String(device.tempMax);
  slider.step = String(device.tempStep);

  deviceMeta.set(id, {
    min: device.tempMin,
    max: device.tempMax,
    step: device.tempStep,
  });

  applyStatus(card, status);

  powerInput.addEventListener("change", () => onPowerToggle(card, powerInput.checked));
  $(".temp-down", card).addEventListener("click", () => adjustTemp(card, -1));
  $(".temp-up", card).addEventListener("click", () => adjustTemp(card, 1));

  let sliderTimer;
  slider.addEventListener("input", () => {
    $(".temp-target", card).textContent = slider.value;
    clearTimeout(sliderTimer);
    sliderTimer = setTimeout(() => setTemp(card, Number(slider.value)), 400);
  });

  return card;
}

function applyStatus(card, status) {
  const on = status?.power === true;
  card.classList.toggle("is-on", on);

  const powerInput = $(".power-input", card);
  powerInput.checked = on;
  $(".power-text", card).textContent = on ? "เปิด" : "ปิด";

  const room = status?.currentTemperature;
  const target = status?.targetTemperature;

  $(".temp-room", card).textContent = room != null ? String(room) : "—";
  $(".temp-target", card).textContent = target != null ? String(target) : "—";

  const slider = $(".temp-slider", card);
  if (target != null) slider.value = String(target);

  $(".meta-mode", card).textContent = workModeLabel(status?.workMode);
  const stateChip = $(".meta-state", card);
  stateChip.textContent = on ? "กำลังทำงาน" : "ปิดอยู่";
  stateChip.classList.toggle("is-on", on);

  $(".device-error", card).hidden = true;
}

function setCardBusy(card, isBusy) {
  card.classList.toggle("is-busy", isBusy);
}

function showCardError(card, message) {
  const el = $(".device-error", card);
  el.textContent = message;
  el.hidden = false;
}

async function withBusy(card, fn) {
  if (busy) return;
  busy = true;
  setCardBusy(card, true);
  setConn("busy", "กำลังส่งคำสั่ง…");
  try {
    await fn();
    await refreshStatus(card);
    setConn("ok", "เชื่อมต่อแล้ว");
  } catch (e) {
    showCardError(card, e instanceof Error ? e.message : String(e));
    setConn("error", "ผิดพลาด");
  } finally {
    setCardBusy(card, false);
    busy = false;
  }
}

async function onPowerToggle(card, on) {
  await withBusy(card, async () => {
    await api("/api/ac/power", {
      method: "POST",
      body: JSON.stringify({ on }),
    });
  });
}

async function adjustTemp(card, delta) {
  await withBusy(card, async () => {
    await api("/api/ac/temperature", {
      method: "POST",
      body: JSON.stringify({ delta }),
    });
  });
}

async function setTemp(card, value) {
  await withBusy(card, async () => {
    await api("/api/ac/temperature", {
      method: "POST",
      body: JSON.stringify({ value }),
    });
  });
}

async function refreshStatus(card) {
  const { data } = await api("/api/ac/status");
  applyStatus(card, data);
  setLastUpdated();
}

async function loadDevices() {
  const grid = $("#devicesGrid");
  setConn("busy", "กำลังโหลด…");

  try {
    const [{ data: devices }, { data: status }] = await Promise.all([
      api("/api/devices"),
      api("/api/ac/status"),
    ]);

    grid.innerHTML = "";
    for (const device of devices) {
      grid.appendChild(renderDeviceCard(device, status));
    }

    setConn("ok", "เชื่อมต่อแล้ว");
    setLastUpdated();
  } catch (e) {
    grid.innerHTML = `<p class="loading-msg" style="color: var(--danger)">${e instanceof Error ? e.message : String(e)}</p>`;
    setConn("error", "เชื่อมต่อไม่ได้");
  }
}

function setupTabs() {
  const tabs = document.querySelectorAll(".tab");
  const panels = {
    control: $("#panel-control"),
    docs: $("#panel-docs"),
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.dataset.tab;
      tabs.forEach((t) => {
        t.classList.toggle("active", t === tab);
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      for (const [key, panel] of Object.entries(panels)) {
        const active = key === name;
        panel.classList.toggle("active", active);
        panel.hidden = !active;
      }
    });
  });
}

function setupTheme() {
  const btn = $("#themeToggle");
  btn.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("theme", next);
  });
}

function setupPoll() {
  pollTimer = setInterval(async () => {
    if (busy) return;
    const card = $(".device-card");
    if (!card) return;
    try {
      await refreshStatus(card);
      setConn("ok", "เชื่อมต่อแล้ว");
    } catch {
      setConn("error", "อัปเดตไม่สำเร็จ");
    }
  }, POLL_MS);
}

$("#refreshBtn").addEventListener("click", async () => {
  const card = $(".device-card");
  if (!card) {
    await loadDevices();
    return;
  }
  setConn("busy", "กำลังโหลด…");
  try {
    await refreshStatus(card);
    setConn("ok", "เชื่อมต่อแล้ว");
  } catch (e) {
    setConn("error", "ผิดพลาด");
    showCardError(card, e instanceof Error ? e.message : String(e));
  }
});

setupTabs();
setupTheme();
setupPoll();
loadDevices();
