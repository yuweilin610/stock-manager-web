/**
 * Market Oracle - 最終完整對接版 (含狀態感知與開市時間計算)
 */

const TZ = "Europe/Dublin";
const MAX_STOCKS = 5;
// const API_URL =
//   "https://d5og0mk1hf.execute-api.eu-west-1.amazonaws.com/v1/subscribe";
const API_URL =
  "https://befk3btyengwqkovss4y3kacje0npcef.lambda-url.eu-west-1.on.aws/subscribe";

const els = {
  emailInput: document.getElementById("emailInput"),
  lookupBtn: document.getElementById("lookupBtn"),
  stockInput: document.getElementById("stockInput"),
  addBtn: document.getElementById("addBtn"),
  stockList: document.getElementById("stockList"),
  limitText: document.getElementById("limitText"),
  limitNote: document.getElementById("limitNote"),
  limitBar: document.getElementById("limitBar"),
  reportTime: document.getElementById("reportTime"),
  saveScheduleBtn: document.getElementById("saveScheduleBtn"),
  nextSendText: document.getElementById("nextSendText"),
  refreshNextBtn: document.getElementById("refreshNextBtn"),
  unsubscribeBtn: document.getElementById("unsubscribeBtn"),
  toastHost: document.getElementById("toastHost"),
};

let currentEmail = "";
let currentStatus = null; // 🚀 新增：追蹤目前帳號狀態
let state = {
  stocks: [],
  reportTime: "21:00",
};

// ==========================================
// 1. API 串接邏輯
// ==========================================

async function lookup() {
  const email = normalizeEmail(els.emailInput.value);
  if (!email || !email.includes("@")) {
    toast("warn", "Invalid Email", "Please enter a valid email address.");
    return;
  }

  els.lookupBtn.disabled = true;
  els.lookupBtn.textContent = "Loading...";

  try {
    const response = await fetch(
      `${API_URL}?email=${encodeURIComponent(email)}`,
    );
    const data = await response.json();

    if (data.is_existing) {
      currentEmail = email;
      currentStatus = data.status; // 🚀 紀錄狀態
      state.stocks = (data.stocks || []).map((item) =>
        typeof item === "object" && item.S ? item.S : String(item),
      );
      state.reportTime = data.schedule === "MORNING" ? "14:30" : "21:00";
      els.reportTime.value = state.reportTime;

      renderStocks();
      refreshNextSendText(); // 🚀 內部會自動使用 currentStatus

      if (data.status === "pending") {
        toast(
          "warn",
          "Verification Required",
          "Email pending. Check inbox or Save to resend.",
        );
      } else {
        toast("good", "Sync Complete", `Settings loaded for ${email}`);
      }
    } else {
      currentEmail = email;
      currentStatus = "inactive"; // 新用戶預設不活躍
      state.stocks = [];
      renderStocks();
      refreshNextSendText();
      toast(
        "warn",
        "New Profile",
        "Enter a ticker to start your cloud watchlist.",
      );
    }
  } catch (err) {
    toast("bad", "API Error", "Check your internet or CORS settings.");
  } finally {
    els.lookupBtn.disabled = false;
    els.lookupBtn.textContent = "Load";
  }
}

async function syncToCloud(
  silent = false,
  customAction = null,
  customMsg = null,
) {
  if (!currentEmail) return;

  const scheduleLabel =
    els.reportTime.value === "14:30" ? "MORNING" : "AFTERNOON";
  const payload = {
    email: currentEmail,
    stocks: state.stocks,
    schedule: scheduleLabel,
    trigger_now: false,
  };

  if (customAction) payload.action = customAction;

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const resData = await response.json();

    // 同步成功後更新狀態，確保 Next Delivery 顯示正確
    if (resData.status) currentStatus = resData.status;

    if (response.status === 403 && resData.message === "quota_limit_reached") {
      toast("bad", "Quota Reached", "Database is full (Max 10 users).");
      return;
    }

    if (resData.status === "inactive") {
      toast(
        "good",
        "Unsubscribed",
        "You have been removed from the mailing list.",
      );
      return resData;
    }

    if (resData.status === "pending") {
      toast("warn", "Verification Sent", "Please check your inbox to verify.");
    } else if (!silent) {
      toast(
        "good",
        customMsg || "Cloud Synced",
        resData.message || "Watchlist updated.",
      );
    }

    refreshNextSendText(); // 🚀 同步後重整時間文字
    return resData;
  } catch (err) {
    toast("bad", "Sync Failed", "Could not connect to AWS.");
  }
}

// ==========================================
// 2. UI 渲染
// ==========================================

function renderStocks() {
  els.stockList.innerHTML = "";
  if (!currentEmail) {
    els.stockList.innerHTML = `<div class="hint"><strong>Load user first</strong></div>`;
    updateLimitUI();
    return;
  }
  if (state.stocks.length === 0) {
    els.stockList.innerHTML = `<div class="hint"><strong>Watchlist empty</strong></div>`;
    updateLimitUI();
    return;
  }

  state.stocks.forEach((ticker) => {
    const row = document.createElement("div");
    row.className = "stock-item";
    row.innerHTML = `
      <div class="stock-left"><div class="ticker mono">${escapeHtml(ticker)}</div></div>
      <button class="btn danger small" type="button">Remove</button>
    `;
    row.querySelector("button").addEventListener("click", () => {
      row.classList.add("removing");
      setTimeout(async () => {
        state.stocks = state.stocks.filter((t) => t !== ticker);
        await syncToCloud(false, null, "Stock Removed");
        renderStocks();
      }, 140);
    });
    els.stockList.appendChild(row);
  });
  updateLimitUI();
}

function updateLimitUI() {
  const n = state.stocks.length;
  els.limitText.textContent = `${n} / ${MAX_STOCKS}`;
  els.limitNote.textContent = currentEmail
    ? `Account: ${currentEmail}`
    : "Not loaded";
  els.limitBar.style.width = `${(n / MAX_STOCKS) * 100}%`;
}

// ==========================================
// 3. 輔助功能與事件
// ==========================================

function toast(type, title, detail) {
  const t = document.createElement("div");
  t.className = `toast ${type || ""}`.trim();
  t.innerHTML = `
    <div class="msg">
      <span class="badge"></span>
      <div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(detail || "")}</p></div>
    </div>
    <button type="button">×</button>
  `;
  t.querySelector("button").addEventListener("click", () => t.remove());
  els.toastHost.appendChild(t);
  setTimeout(() => {
    if (t.isConnected) t.remove();
  }, 6000);
}

// 🚀 改良：計算下一個「工作日」的寄信時間
function nextOccurrenceInDublin(hhmm) {
  const [hh, mm] = hhmm.split(":").map(Number);
  const now = new Date(new Date().toLocaleString("en-US", { timeZone: TZ }));
  let d = new Date(now);
  d.setHours(hh, mm, 0, 0);

  // 如果今天的時間已經過了，就先加一天
  if (d <= now) d.setDate(d.getDate() + 1);

  // 🚀 關鍵：如果是週六(6)或週日(0)，則推移到下週一
  while (d.getDay() === 0 || d.getDay() === 6) {
    d.setDate(d.getDate() + 1);
  }
  return d;
}

// 🚀 修改：整合狀態顯示與自動計算
function refreshNextSendText() {
  if (!currentEmail) {
    els.nextSendText.textContent = "Load user first";
    return;
  }

  // 1. 根據狀態顯示不同文字
  if (currentStatus === "pending") {
    els.nextSendText.textContent = "Waiting for verification...";
    return;
  }

  if (currentStatus === "inactive" || state.stocks.length === 0) {
    els.nextSendText.textContent =
      "Subscription inactive (Add stocks to start)";
    return;
  }

  // 2. 只有 Active 才計算並顯示具體日期
  const d = nextOccurrenceInDublin(state.reportTime);
  const opt = {
    timeZone: TZ,
    hour12: false,
    weekday: "short",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  };
  els.nextSendText.textContent = `${new Intl.DateTimeFormat("en-GB", opt).format(d)} (Ireland)`;
}

async function addStockFromInput() {
  if (!currentEmail) {
    toast("warn", "Load User", "Please load an email first.");
    return;
  }
  const ticker = normalizeStockInput(els.stockInput.value);
  if (!ticker) return;
  if (state.stocks.length >= MAX_STOCKS) {
    toast("warn", "Limit Reached", "Max 5 stocks allowed.");
    return;
  }
  if (state.stocks.includes(ticker)) {
    toast("warn", "Duplicate", "Ticker already in list.");
    return;
  }

  state.stocks.unshift(ticker);
  els.stockInput.value = "";
  renderStocks();
  await syncToCloud(false, null, "Stock Added");
}

async function saveSchedule() {
  if (!currentEmail) {
    toast("warn", "No User", "Load an email first.");
    return;
  }
  if (state.stocks.length === 0) {
    toast(
      "warn",
      "Empty Watchlist",
      "Please add at least one stock ticker first.",
    );
    return;
  }

  state.reportTime = els.reportTime.value;
  const scheduleLabel = state.reportTime === "14:30" ? "MORNING" : "AFTERNOON";

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: currentEmail,
        stocks: state.stocks,
        schedule: scheduleLabel,
        trigger_now: false,
      }),
    });
    const data = await res.json();
    if (res.status === 200) {
      if (data.status) currentStatus = data.status; // 更新狀態
      toast("good", "Schedule Updated", "Your delivery time has been saved.");
    } else {
      toast("bad", "Update Failed", data.message || "Could not save.");
    }
  } catch (e) {
    toast("bad", "Error", "Connection failed.");
  }
  refreshNextSendText();
}

async function handleUnsubscribe() {
  if (!currentEmail) {
    toast("warn", "No User", "Please load a user first.");
    return;
  }
  if (!confirm("Are you sure? This will stop all reports.")) return;

  els.unsubscribeBtn.disabled = true;
  const res = await syncToCloud(false, "unsubscribe");
  if (res) {
    currentEmail = "";
    currentStatus = null;
    els.emailInput.value = "";
    state.stocks = [];
    renderStocks();
    refreshNextSendText();
  }
  els.unsubscribeBtn.disabled = false;
}

function escapeHtml(s) {
  return String(s).replace(
    /[&<>"']/g,
    (m) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        m
      ],
  );
}
function normalizeEmail(s) {
  return String(s || "")
    .trim()
    .toLowerCase();
}
function normalizeStockInput(s) {
  return String(s || "")
    .trim()
    .split(" ")[0]
    .toUpperCase();
}

els.lookupBtn.addEventListener("click", lookup);
els.addBtn.addEventListener("click", addStockFromInput);
els.saveScheduleBtn.addEventListener("click", saveSchedule);
els.unsubscribeBtn.addEventListener("click", handleUnsubscribe);
els.refreshNextBtn.addEventListener("click", () => {
  // 🚀 Refresh 時重新檢查當前 Email 狀態
  if (currentEmail) lookup();
  else toast("warn", "No User", "Load a user first.");
});
els.emailInput.addEventListener(
  "keydown",
  (e) => e.key === "Enter" && lookup(),
);
els.stockInput.addEventListener(
  "keydown",
  (e) => e.key === "Enter" && addStockFromInput(),
);

renderStocks();
refreshNextSendText();
