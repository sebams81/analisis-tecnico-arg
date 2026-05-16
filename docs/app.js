const META = { studyCutoffDate: null, studyEndDate: null, warmupEndDate: null };
let SUMMARY = null;
let LOCAL_VS_MEP = null;
let DAILY_PANEL = null;
let DAILY_PANEL_DATES = null;
let SELECTED_TICKERS = null;
let CURRENT_DATE = null;
let FUNDAMENTALS = null;
let SELECTED_FUND_TICKERS = null;
let SELECTED_MONTH = "";
let TICKER_DATA = {};
let CHART = null;
let CHART_TICKER = null;
let CHART_MODE = "candles";
let CHART_INDICATORS = { hma: false };
let CHART_CLASSIC_METHOD = "none";
let TAB2_INITIALIZED = false;

async function init() {
  setupTabs();
  setupInfoToggles();
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

      if (btn.dataset.tab === "tab2") {
        setupTab2IfNeeded();
      }
      if (btn.dataset.tab === "tab3" && FUNDAMENTALS === null) {
        loadFundamentals();
      }
    });
  });
}

function setupInfoToggles() {
  document.querySelectorAll(".info-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const panel = btn.nextElementSibling;
      panel.hidden = !panel.hidden;
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
      <td><strong>${cleanTicker(t.ticker)}</strong></td>
      <td>${t.mercado === "BA" ? "Local" : "MEP"}</td>
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

const SIGNAL_PILL_CLASS = {
  "Compra Confirmada": "buy-conf",
  "Compra Temprana":   "buy-temp",
  "Señal Alcista":     "bull-soft",
  "Venta Confirmada":  "sell-conf",
  "Venta Temprana":    "sell-temp",
  "Señal Bajista":     "bear-soft",
  "Neutra":            "neutral",
};

function pillSignal(signal) {
  if (!signal) return '<span class="pill neutral">—</span>';
  const cls = SIGNAL_PILL_CLASS[signal] || "neutral";
  return `<span class="pill ${cls}">${signal}</span>`;
}

const VMA_CLASS = {
  "Muy Alto": "vma-mh",
  "Alto": "vma-h",
  "Neutro": "vma-n",
  "Bajo": "vma-l",
  "Muy Bajo": "vma-ml",
};

function pillVma(cat) {
  if (!cat) return '<span class="pill neutral">—</span>';
  const cls = VMA_CLASS[cat] || "vma-n";
  return `<span class="pill ${cls}">${cat}</span>`;
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
  document.getElementById("appFooter").innerHTML =
    `Última actualización: ${dateDDMMYYYY}`;
}

async function ensureFundamentals() {
  if (FUNDAMENTALS !== null) return true;
  try {
    FUNDAMENTALS = await fetch("./data/fundamentals.json").then((r) => {
      if (!r.ok) throw new Error("No se pudo cargar fundamentals.json");
      return r.json();
    });
    FUNDAMENTALS.sort((a, b) => b.fecha.localeCompare(a.fecha));
    return true;
  } catch (e) {
    FUNDAMENTALS = null;
    return false;
  }
}

async function loadFundamentals() {
  const loading = document.getElementById("loadingTab3");
  const err = document.getElementById("errorTab3");
  const table = document.getElementById("fundamentalsTable");
  loading.hidden = false;
  err.hidden = true;
  const ok = await ensureFundamentals();
  if (!ok) {
    loading.hidden = true;
    err.textContent = "Error al cargar datos: fundamentals.json";
    err.hidden = false;
    return;
  }
  setupFundFilters();
  renderFundamentals();
  loading.hidden = true;
  table.hidden = false;
}

function cleanTicker(t) {
  return t.replace(/_(BA|MEP)$/, "");
}

function setupFundFilters() {
  const allTickers = [...new Set(
    FUNDAMENTALS.flatMap((ev) => ev.tickers_afectados.map(cleanTicker))
  )].sort();
  SELECTED_FUND_TICKERS = new Set(allTickers);

  const list = document.getElementById("fundTickerCheckboxes");
  list.innerHTML = allTickers
    .map((t) => `<label><input type="checkbox" value="${t}" checked> ${t}</label>`)
    .join("");
  document.getElementById("fundTickerCount").textContent = `${allTickers.length}/${allTickers.length}`;

  document.getElementById("fundTickerFilterToggle").addEventListener("click", (e) => {
    e.stopPropagation();
    const panel = document.getElementById("fundTickerFilterPanel");
    panel.hidden = !panel.hidden;
  });
  document.addEventListener("click", (e) => {
    const panel = document.getElementById("fundTickerFilterPanel");
    if (!panel.hidden && !panel.contains(e.target) && e.target.id !== "fundTickerFilterToggle") {
      panel.hidden = true;
    }
  });

  document.querySelectorAll("button[data-fund-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const checked = btn.dataset.fundAction === "all";
      list.querySelectorAll('input[type="checkbox"]').forEach((cb) => (cb.checked = checked));
      onFundTickerSelectionChange();
    });
  });
  list.addEventListener("change", onFundTickerSelectionChange);

  const months = [...new Set(FUNDAMENTALS.map((ev) => ev.fecha.slice(0, 7)))].sort().reverse();
  const select = document.getElementById("monthSelect");
  for (const m of months) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = monthYearLabel(m);
    select.appendChild(opt);
  }
  select.addEventListener("change", (e) => {
    SELECTED_MONTH = e.target.value;
    renderFundamentals();
  });
}

function onFundTickerSelectionChange() {
  SELECTED_FUND_TICKERS = new Set(
    [...document.querySelectorAll("#fundTickerCheckboxes input:checked")].map((cb) => cb.value)
  );
  const total = document.querySelectorAll("#fundTickerCheckboxes input").length;
  document.getElementById("fundTickerCount").textContent = `${SELECTED_FUND_TICKERS.size}/${total}`;
  renderFundamentals();
}

const MONTHS_ES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function monthYearLabel(iso) {
  const [y, m] = iso.split("-");
  return `${MONTHS_ES[parseInt(m, 10) - 1]} ${y}`;
}

const IMPACT_MAP = {
  Verde:    { cls: "impacto-verde",    icon: "↑" },
  Amarillo: { cls: "impacto-amarillo", icon: "→" },
  Rojo:     { cls: "impacto-rojo",     icon: "↓" },
};

function renderFundamentals() {
  const filtered = FUNDAMENTALS.filter((ev) => {
    const tickerMatch = ev.tickers_afectados.some((t) => SELECTED_FUND_TICKERS.has(cleanTicker(t)));
    const monthMatch = !SELECTED_MONTH || ev.fecha.startsWith(SELECTED_MONTH);
    return tickerMatch && monthMatch;
  });
  const tbody = document.querySelector("#fundamentalsTable tbody");
  tbody.innerHTML = filtered.map((ev) => {
    const m = IMPACT_MAP[ev.impacto] || { cls: "", icon: "" };
    const tickers = ev.tickers_afectados
      .map(cleanTicker)
      .map((t) => `<strong>${escapeHtml(t)}</strong>`)
      .join(", ");
    const prefix = m.icon ? `${m.icon} ` : "";
    return `
      <tr class="${m.cls}">
        <td>${formatDateDDMMYYYY(ev.fecha)}</td>
        <td>${tickers}</td>
        <td>${prefix}${escapeHtml(ev.evento)}</td>
      </tr>
    `;
  }).join("");
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ============== Tab 2 — Chart ==============

function setupTab2IfNeeded() {
  if (TAB2_INITIALIZED) return;
  TAB2_INITIALIZED = true;

  const select = document.getElementById("chartTicker");
  select.innerHTML = SUMMARY.map(
    (t) => `<option value="${t.ticker}">${t.ticker}</option>`
  ).join("");
  select.value = "BBAR_BA";

  select.addEventListener("change", () => loadAndRenderTicker(select.value));

  document.getElementById("chartModeCandles").addEventListener("click", () => setChartMode("candles"));
  document.getElementById("chartModeLine").addEventListener("click", () => setChartMode("line"));

  document.getElementById("ind-hma").addEventListener("change", (e) => {
    CHART_INDICATORS.hma = e.target.checked;
    renderChart();
  });
  document.querySelectorAll('input[name="classic"]').forEach((radio) => {
    radio.addEventListener("change", (e) => {
      CHART_CLASSIC_METHOD = e.target.value;
      renderChart();
    });
  });

  loadAndRenderTicker("BBAR_BA");
}

function setChartMode(mode) {
  CHART_MODE = mode;
  document.getElementById("chartModeCandles").classList.toggle("active", mode === "candles");
  document.getElementById("chartModeLine").classList.toggle("active", mode === "line");
  renderChart();
}

async function loadAndRenderTicker(ticker) {
  const loading = document.getElementById("loadingTab2");
  const err = document.getElementById("errorTab2");
  err.hidden = true;

  if (!TICKER_DATA[ticker]) {
    loading.hidden = false;
    try {
      TICKER_DATA[ticker] = await fetch(`./data/ticker_${ticker}.json`).then((r) => {
        if (!r.ok) throw new Error(`No se pudo cargar ticker_${ticker}.json`);
        return r.json();
      });
    } catch (e) {
      loading.hidden = true;
      err.textContent = `Error al cargar datos: ${e.message}`;
      err.hidden = false;
      return;
    }
    loading.hidden = true;
  }

  CHART_TICKER = ticker;
  renderChart();
  renderTickerState(ticker);

  await ensureFundamentals();
  renderTickerEvents(ticker);
}

function renderChart() {
  if (!CHART_TICKER || !TICKER_DATA[CHART_TICKER]) return;

  const container = document.getElementById("chartContainer");
  if (CHART) {
    CHART.remove();
    CHART = null;
  }

  CHART = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight,
    layout: {
      background: { color: "transparent" },
      textColor: "#e6e6e6",
      panes: { separatorColor: "#232a3d", enableResize: false },
    },
    grid: {
      vertLines: { color: "#232a3d" },
      horzLines: { color: "#232a3d" },
    },
    rightPriceScale: { borderColor: "#232a3d" },
    timeScale: { borderColor: "#232a3d", timeVisible: false },
    crosshair: { mode: 1 },
  });

  const ohlc = TICKER_DATA[CHART_TICKER].ohlc;

  // Serie de precio en pane 0 (default)
  let priceSeries;
  if (CHART_MODE === "candles") {
    priceSeries = CHART.addSeries(LightweightCharts.CandlestickSeries, {
      upColor: "#34d399", downColor: "#f87171",
      borderUpColor: "#34d399", borderDownColor: "#f87171",
      wickUpColor: "#34d399", wickDownColor: "#f87171",
    });
    priceSeries.setData(ohlc.map((d) => ({
      time: d.time, open: d.open, high: d.high, low: d.low, close: d.close,
    })));
  } else {
    priceSeries = CHART.addSeries(LightweightCharts.LineSeries, {
      color: "#fde047", lineWidth: 3,
    });
    priceSeries.setData(ohlc.map((d) => ({ time: d.time, value: d.close })));
  }

  // Indicadores en pane 0
  if (CHART_INDICATORS.hma) addHmaIndicator(ohlc);
  if (CHART_CLASSIC_METHOD === "ema") addEmaIndicator(ohlc);
  if (CHART_CLASSIC_METHOD === "sma") addSmaIndicator(ohlc);

  // Pane 1 (markers): serie transparente con valor 0 constante
  const markerSeries = CHART.addSeries(LightweightCharts.LineSeries, {
    color: "transparent",
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
    priceFormat: { type: "price", precision: 0, minMove: 1 },
  }, 1);
  markerSeries.setData(ohlc.map((d) => ({ time: d.time, value: 0 })));

  // Markers EMA + SMA combinados sobre la serie de pane 1
  const markers = [];
  if (CHART_CLASSIC_METHOD === "ema") markers.push(...signalMarkers(ohlc, "T_ema12_26"));
  if (CHART_CLASSIC_METHOD === "sma") markers.push(...signalMarkers(ohlc, "T_sma10_50_100"));
  if (markers.length > 0) {
    markers.sort((a, b) => a.time.localeCompare(b.time));
    LightweightCharts.createSeriesMarkers(markerSeries, markers);
  }

  // Pane heights: 84% / 16% del container
  const panes = CHART.panes();
  if (panes.length >= 2) {
    const h = container.clientHeight;
    panes[0].setHeight(Math.round(h * 0.84));
    panes[1].setHeight(Math.round(h * 0.16));
  }

  // Rango visible default: últimos 130 ruedas (~6 meses)
  const visibleBars = 130;
  CHART.timeScale().setVisibleLogicalRange({
    from: Math.max(0, ohlc.length - visibleBars),
    to: ohlc.length - 1,
  });

  renderLegend();

  if (!renderChart._resizeAttached) {
    window.addEventListener("resize", () => {
      if (CHART) {
        const c = document.getElementById("chartContainer");
        CHART.resize(c.clientWidth, c.clientHeight);
        const h = c.clientHeight;
        const ps = CHART.panes();
        if (ps.length >= 2) {
          ps[0].setHeight(Math.round(h * 0.84));
          ps[1].setHeight(Math.round(h * 0.16));
        }
      }
    });
    renderChart._resizeAttached = true;
  }
}

const HMA_GREEN_STATES = new Set(["Compra Confirmada", "Compra Temprana", "Señal Alcista"]);
const HMA_RED_STATES   = new Set(["Venta Confirmada",  "Venta Temprana",  "Señal Bajista"]);

function hmaStateFromSignal(sig) {
  if (HMA_GREEN_STATES.has(sig)) return "green";
  if (HMA_RED_STATES.has(sig))   return "red";
  return "gray";
}

function addHmaIndicator(ohlc) {
  const colors = { green: "#34d399", red: "#f87171", gray: "#a8b3c7" };
  const segments = [];
  let current = { state: null, data: [] };

  for (const day of ohlc) {
    if (day.hma16 == null) continue;
    const state = hmaStateFromSignal(day.T_hma16);
    if (state !== current.state) {
      if (current.state !== null) {
        // Joiner: el día de transición cierra el segmento anterior antes de empezar el nuevo
        current.data.push({ time: day.time, value: day.hma16 });
        segments.push(current);
      }
      current = { state, data: [{ time: day.time, value: day.hma16 }] };
    } else {
      current.data.push({ time: day.time, value: day.hma16 });
    }
  }
  if (current.data.length > 0) segments.push(current);

  for (const seg of segments) {
    const series = CHART.addSeries(LightweightCharts.LineSeries, {
      color: colors[seg.state],
      lineWidth: 2,
      lastValueVisible: false,
      priceLineVisible: false,
      autoscaleInfoProvider: () => null,
    });
    series.setData(seg.data);
  }
}

function addEmaIndicator(ohlc) {
  const ema12 = ohlc.filter((d) => d.ema12 != null).map((d) => ({ time: d.time, value: d.ema12 }));
  const ema26 = ohlc.filter((d) => d.ema26 != null).map((d) => ({ time: d.time, value: d.ema26 }));
  CHART.addSeries(LightweightCharts.LineSeries, {
    color: "#60a5fa", lineWidth: 1.5, lastValueVisible: false, priceLineVisible: false,
    autoscaleInfoProvider: () => null,
  }).setData(ema12);
  CHART.addSeries(LightweightCharts.LineSeries, {
    color: "#dc2626", lineWidth: 1.5, lastValueVisible: false, priceLineVisible: false,
    autoscaleInfoProvider: () => null,
  }).setData(ema26);
}

function addSmaIndicator(ohlc) {
  const sma10  = ohlc.filter((d) => d.sma10  != null).map((d) => ({ time: d.time, value: d.sma10 }));
  const sma50  = ohlc.filter((d) => d.sma50  != null).map((d) => ({ time: d.time, value: d.sma50 }));
  const sma100 = ohlc.filter((d) => d.sma100 != null).map((d) => ({ time: d.time, value: d.sma100 }));
  CHART.addSeries(LightweightCharts.LineSeries, {
    color: "#fbbf24", lineWidth: 1.5, lastValueVisible: false, priceLineVisible: false,
    autoscaleInfoProvider: () => null,
  }).setData(sma10);
  CHART.addSeries(LightweightCharts.LineSeries, {
    color: "#CC66FF", lineWidth: 1.5, lastValueVisible: false, priceLineVisible: false,
    autoscaleInfoProvider: () => null,
  }).setData(sma50);
  CHART.addSeries(LightweightCharts.LineSeries, {
    color: "#FF66FF", lineWidth: 1.5, lastValueVisible: false, priceLineVisible: false,
    autoscaleInfoProvider: () => null,
  }).setData(sma100);
}

function renderLegend() {
  const items = [];
  if (CHART_MODE === "candles") {
    items.push({ label: "Precio (velas)", color: "#34d399" });
  } else {
    items.push({ label: "Precio", color: "#fde047" });
  }
  if (CHART_INDICATORS.hma) {
    items.push({ label: "HMA 16", color: "#34d399" });
  }
  if (CHART_CLASSIC_METHOD === "ema") {
    items.push({ label: "EMA 12", color: "#60a5fa" });
    items.push({ label: "EMA 26", color: "#dc2626" });
  }
  if (CHART_CLASSIC_METHOD === "sma") {
    items.push({ label: "SMA 10",  color: "#fbbf24" });
    items.push({ label: "SMA 50",  color: "#CC66FF" });
    items.push({ label: "SMA 100", color: "#FF66FF" });
  }
  document.querySelector(".chart-legend").innerHTML = items.map((i) =>
    `<div class="legend-item"><span class="swatch" style="background:${i.color}"></span>${i.label}</div>`
  ).join("");
}

const BUY_SIGNALS  = new Set(["Compra Confirmada", "Compra Temprana"]);
const SELL_SIGNALS = new Set(["Venta Confirmada",  "Venta Temprana"]);

function signalMarkers(ohlc, signalField) {
  const markers = [];
  for (const day of ohlc) {
    const sig = day[signalField];
    if (BUY_SIGNALS.has(sig)) {
      markers.push({ time: day.time, position: "belowBar", color: "#34d399", shape: "arrowUp" });
    } else if (SELL_SIGNALS.has(sig)) {
      markers.push({ time: day.time, position: "aboveBar", color: "#f87171", shape: "arrowDown" });
    }
  }
  return markers;
}

function fmtPctSigned(v) {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(1)}%`;
}

function fmtPrice(p) {
  if (p == null) return "—";
  if (p < 100) return `$${p.toFixed(2)}`;
  return `$${Math.round(p).toLocaleString("es-AR")}`;
}

function variationPct(closes, lookback) {
  if (closes.length <= lookback) return null;
  const cur = closes[closes.length - 1];
  const past = closes[closes.length - 1 - lookback];
  if (cur == null || past == null || past === 0) return null;
  return (cur - past) / past;
}

function setVariation(selector, v) {
  const el = document.querySelector(selector);
  if (v == null) {
    el.textContent = "—";
    el.className = "";
  } else {
    el.textContent = fmtPctSigned(v);
    el.className = v >= 0 ? "pos" : "neg";
  }
}

function renderTickerState(ticker) {
  const data = TICKER_DATA[ticker];
  if (!data || !data.ohlc || data.ohlc.length === 0) return;
  const ohlc = data.ohlc;
  const last = ohlc[ohlc.length - 1];
  const closes = ohlc.map((d) => d.close);

  document.querySelector(".state-date").textContent = formatDateDDMMYYYY(last.time);
  document.querySelector(".price-value").textContent = fmtPrice(last.close);

  const dayVar = variationPct(closes, 1);
  const dayEl = document.querySelector(".price-change");
  if (dayVar == null) {
    dayEl.textContent = "—";
    dayEl.className = "price-change";
  } else {
    const arrow = dayVar >= 0 ? "↑" : "↓";
    dayEl.textContent = `${arrow} ${fmtPctSigned(dayVar)} día`;
    dayEl.className = `price-change ${dayVar >= 0 ? "pos" : "neg"}`;
  }

  setVariation(".var-week",  variationPct(closes, 5));
  setVariation(".var-month", variationPct(closes, 21));
  setVariation(".var-year",  variationPct(closes, 252));

  document.querySelector(".state-hma").innerHTML = pillSignal(last.T_hma16);
  document.querySelector(".state-ema").innerHTML = pillSignal(last.T_ema12_26);
  document.querySelector(".state-sma").innerHTML = pillSignal(last.T_sma10_50_100);
  document.querySelector(".state-vma").innerHTML = pillVma(last.vma20_cat);
  document.querySelector(".state-candle").textContent = last.candle || "—";
}

function renderTickerEvents(ticker) {
  const list = document.querySelector(".events-list");
  const empty = document.querySelector(".no-events");
  if (FUNDAMENTALS === null) {
    list.innerHTML = "";
    empty.hidden = false;
    return;
  }
  const base = cleanTicker(ticker);
  const matching = FUNDAMENTALS
    .filter((ev) => ev.tickers_afectados.some((t) => cleanTicker(t) === base))
    .slice(0, 5);

  if (matching.length === 0) {
    list.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  list.innerHTML = matching.map((ev) => {
    const m = IMPACT_MAP[ev.impacto] || { cls: "", icon: "" };
    return `<li class="${m.cls}"><span class="icon">${m.icon}</span> <strong>${formatDateDDMMYYYY(ev.fecha)}</strong> ${escapeHtml(ev.evento)}</li>`;
  }).join("");
}

init();
