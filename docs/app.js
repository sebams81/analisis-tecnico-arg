const META = { studyCutoffDate: null, studyEndDate: null, warmupEndDate: null };
let SUMMARY = null;
let LOCAL_VS_MEP = null;
let DAILY_PANEL = null;
let DAILY_PANEL_DATES = null;
let SELECTED_TICKERS = null;
let CURRENT_DATE = null;
let FUNDAMENTALS = null;

async function init() {
  setupTabs();
  try {
    const [meta, summary, lvm] = await Promise.all([
      fetch("./data/_meta.json").then((r) => {
        if (!r.ok) throw new Error("No se pudo cargar _meta.json");
        return r.json();
      }),
      fetch("./data/summary.json").then((r) => {
        if (!r.ok) throw new Error("No se pudo cargar summary.json");
        return r.json();
      }),
      fetch("./data/local_vs_mep.json").then((r) => {
        if (!r.ok) throw new Error("No se pudo cargar local_vs_mep.json");
        return r.json();
      }),
    ]);
    META.studyCutoffDate = meta.study_cutoff_date;
    META.studyEndDate = meta.study_end_date;
    META.warmupEndDate = meta.warmup_end_date;
    SUMMARY = summary;
    LOCAL_VS_MEP = lvm;

    SUMMARY.sort((a, b) => {
      const baseA = a.ticker.split("_")[0];
      const baseB = b.ticker.split("_")[0];
      if (baseA !== baseB) return baseA.localeCompare(baseB);
      return a.mercado.localeCompare(b.mercado);
    });

    SELECTED_TICKERS = new Set(SUMMARY.map((t) => t.ticker));
    CURRENT_DATE = snapshotDate();

    populateFooter(meta);
    setupTickerFilter();
    setupDatePicker();
    renderSnapshotInfo();
    renderTable();
    document.getElementById("loadingTab1").hidden = true;
    document.getElementById("signalsTable").hidden = false;
  } catch (e) {
    const err = document.getElementById("errorTab1");
    err.textContent = `Error al cargar datos: ${e.message}`;
    err.hidden = false;
    document.getElementById("loadingTab1").hidden = true;
  }
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document
        .querySelectorAll(".tab-content")
        .forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.tab).classList.add("active");

      if (btn.dataset.tab === "tab3" && FUNDAMENTALS === null) {
        loadFundamentals();
      }
    });
  });
}

function snapshotDate() {
  // Snapshot = max(last_date) entre los 24 tickers (en la práctica todos comparten el mismo día).
  const dates = SUMMARY.map((t) => t.last_date).filter(Boolean).sort();
  return dates[dates.length - 1] || "—";
}

function renderSnapshotInfo() {
  document.getElementById("snapshotDate").textContent = CURRENT_DATE || snapshotDate();
}

function setupTickerFilter() {
  const list = document.getElementById("tickerCheckboxes");
  list.innerHTML = SUMMARY.map(
    (t) =>
      `<label><input type="checkbox" value="${t.ticker}" checked> ${t.ticker}</label>`
  ).join("");

  document.getElementById("tickerFilterToggle").addEventListener("click", (e) => {
    e.stopPropagation();
    const panel = document.getElementById("tickerFilterPanel");
    panel.hidden = !panel.hidden;
  });
  document.addEventListener("click", (e) => {
    const panel = document.getElementById("tickerFilterPanel");
    if (
      !panel.hidden &&
      !panel.contains(e.target) &&
      e.target.id !== "tickerFilterToggle"
    ) {
      panel.hidden = true;
    }
  });

  document.querySelectorAll(".filter-actions button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const checked = btn.dataset.action === "all";
      list
        .querySelectorAll('input[type="checkbox"]')
        .forEach((cb) => (cb.checked = checked));
      onTickerSelectionChange();
    });
  });
  list.addEventListener("change", onTickerSelectionChange);
}

function onTickerSelectionChange() {
  SELECTED_TICKERS = new Set(
    [...document.querySelectorAll("#tickerCheckboxes input:checked")].map((cb) => cb.value)
  );
  document.getElementById("tickerCount").textContent = `${SELECTED_TICKERS.size}/24`;
  renderTable();
}

function setupDatePicker() {
  const input = document.getElementById("dateInput");
  input.min = META.warmupEndDate;
  input.max = snapshotDate();
  input.value = snapshotDate();
  input.addEventListener("change", onDateChange);
}

async function onDateChange() {
  const input = document.getElementById("dateInput");
  const requested = input.value;
  const lastDate = snapshotDate();

  if (requested === lastDate) {
    CURRENT_DATE = requested;
    renderSnapshotInfo();
    renderTable();
    return;
  }

  if (!DAILY_PANEL) {
    showToast("Cargando histórico…");
    try {
      DAILY_PANEL = await fetch("./data/daily_panel.json").then((r) => {
        if (!r.ok) throw new Error("No se pudo cargar daily_panel.json");
        return r.json();
      });
      DAILY_PANEL_DATES = Object.keys(DAILY_PANEL).sort();
    } catch (e) {
      showToast(`Error al cargar histórico: ${e.message}`);
      return;
    }
  }

  let target = null;
  for (let i = DAILY_PANEL_DATES.length - 1; i >= 0; i--) {
    if (DAILY_PANEL_DATES[i] <= requested) {
      target = DAILY_PANEL_DATES[i];
      break;
    }
  }
  if (!target) {
    showToast("No hay datos disponibles antes de esa fecha");
    return;
  }
  if (target !== requested) {
    showToast(`Rueda hábil más cercana: ${formatDateDDMMYYYY(target)}`);
    input.value = target;
  }
  CURRENT_DATE = target;
  renderSnapshotInfo();
  renderTable();
}

function showToast(msg) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    toast.hidden = true;
  }, 3000);
}

function renderTable() {
  const lastDate = snapshotDate();
  const source =
    CURRENT_DATE === lastDate || !DAILY_PANEL
      ? SUMMARY
      : DAILY_PANEL[CURRENT_DATE] || [];

  const filtered = source.filter((t) => SELECTED_TICKERS.has(t.ticker));
  const tbody = document.querySelector("#signalsTable tbody");
  tbody.innerHTML = filtered
    .map(
      (t, i) => `
    <tr>
      <td>${i + 1}</td>
      <td><strong>${t.ticker}</strong></td>
      <td>${pillMercado(t.mercado)}</td>
      <td>${pillSignal(t.signals.HMA16)}</td>
      <td>${pillSignal(t.signals.EMA_12_26)}</td>
      <td>${pillSignal(t.signals.SMA_10_50_100)}</td>
      <td>${pillVma(t.vma20_cat)}</td>
      <td>${candleLabel(t.candle)}</td>
    </tr>
  `
    )
    .join("");
}

const SIGNAL_GREENS = ["Compra Temprana", "Compra Confirmada", "Señal Alcista"];
const SIGNAL_REDS = ["Venta Temprana", "Venta Confirmada", "Señal Bajista"];

function pillSignal(s) {
  if (!s) return '<span class="pill pill-neutral">—</span>';
  if (SIGNAL_GREENS.includes(s)) return `<span class="pill pill-buy">${s}</span>`;
  if (SIGNAL_REDS.includes(s)) return `<span class="pill pill-sell">${s}</span>`;
  return `<span class="pill pill-neutral">${s}</span>`;
}

const VMA_CLASS = {
  "Muy Alto": "vma-mh",
  "Alto": "vma-h",
  "Neutro": "vma-n",
  "Bajo": "vma-l",
  "Muy Bajo": "vma-ml",
};

function pillVma(cat) {
  if (!cat) return '<span class="pill pill-neutral">—</span>';
  const cls = VMA_CLASS[cat] || "vma-n";
  return `<span class="pill ${cls}">${cat}</span>`;
}

function pillMercado(m) {
  return `<span class="pill pill-mercado-${m.toLowerCase()}">${m}</span>`;
}

const CANDLE_LABELS = {
  Marubozu_Alc: "Marubozu Alcista",
  Marubozu_Baj: "Marubozu Bajista",
  Engulfing_Alc: "Engulfing Alcista",
  Engulfing_Baj: "Engulfing Bajista",
  Doji: "Doji",
};

function candleLabel(c) {
  if (!c) return "—";
  return CANDLE_LABELS[c] || c;
}

function formatDateDDMMYYYY(iso) {
  const datePart = iso.split("T")[0];
  const [y, m, d] = datePart.split("-");
  return `${d}/${m}/${y}`;
}

function populateFooter(meta) {
  const dateDDMMYYYY = formatDateDDMMYYYY(meta.pipeline_run_date);
  const cost = (meta.cost_per_trade * 100).toString().replace(".", ",");
  document.getElementById("appFooter").innerHTML =
    `Última actualización: ${dateDDMMYYYY} · Costo por trade asumido: ${cost}%`;
}

async function loadFundamentals() {
  const loading = document.getElementById("loadingTab3");
  const err = document.getElementById("errorTab3");
  const table = document.getElementById("fundamentalsTable");
  loading.hidden = false;
  err.hidden = true;
  try {
    FUNDAMENTALS = await fetch("./data/fundamentals.json").then((r) => {
      if (!r.ok) throw new Error("No se pudo cargar fundamentals.json");
      return r.json();
    });
    FUNDAMENTALS.sort((a, b) => b.fecha.localeCompare(a.fecha));
    renderFundamentals();
    loading.hidden = true;
    table.hidden = false;
  } catch (e) {
    loading.hidden = true;
    err.textContent = `Error al cargar datos: ${e.message}`;
    err.hidden = false;
    FUNDAMENTALS = null;
  }
}

const MONTHS_ES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function monthYearLabel(iso) {
  const [y, m] = iso.split("-");
  return `${MONTHS_ES[parseInt(m, 10) - 1]} ${y}`;
}

function renderFundamentals() {
  const tbody = document.querySelector("#fundamentalsTable tbody");
  let lastMonthKey = null;
  const rows = [];
  for (const ev of FUNDAMENTALS) {
    const monthKey = ev.fecha.slice(0, 7);
    if (monthKey !== lastMonthKey) {
      rows.push(`
        <tr class="month-separator">
          <td colspan="4">${monthYearLabel(ev.fecha)}</td>
        </tr>
      `);
      lastMonthKey = monthKey;
    }
    rows.push(`
      <tr>
        <td>${formatDateDDMMYYYY(ev.fecha)}</td>
        <td>${tickerChips(ev.tickers_afectados)}</td>
        <td class="evento">${escapeHtml(ev.evento)}</td>
        <td>${impactPill(ev.impacto)}</td>
      </tr>
    `);
  }
  tbody.innerHTML = rows.join("");
}

function tickerChips(arr) {
  if (!arr || arr.length === 0) return "—";
  if (arr.length <= 3) {
    return arr.map((t) => `<span class="chip">${t}</span>`).join("");
  }
  const head = arr.slice(0, 3).map((t) => `<span class="chip">${t}</span>`).join("");
  return `${head}<span class="chip-more">+${arr.length - 3} más</span>`;
}

const IMPACT_MAP = {
  Verde:    { cls: "pill-buy",     label: "Positivo" },
  Amarillo: { cls: "pill-neutral", label: "Neutro" },
  Rojo:     { cls: "pill-sell",    label: "Negativo" },
};

function impactPill(impacto) {
  const m = IMPACT_MAP[impacto];
  if (!m) return `<span class="pill pill-neutral">—</span>`;
  return `<span class="pill ${m.cls}">${m.label}</span>`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

init();
