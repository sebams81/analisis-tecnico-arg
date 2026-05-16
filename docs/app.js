const META = { studyCutoffDate: null, studyEndDate: null };
let SUMMARY = null;
let LOCAL_VS_MEP = null;

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
    SUMMARY = summary;
    LOCAL_VS_MEP = lvm;

    SUMMARY.sort((a, b) => {
      const baseA = a.ticker.split("_")[0];
      const baseB = b.ticker.split("_")[0];
      if (baseA !== baseB) return baseA.localeCompare(baseB);
      return a.mercado.localeCompare(b.mercado);
    });

    populateFooter(meta);
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
    });
  });
}

function snapshotDate() {
  // Snapshot = max(last_date) entre los 24 tickers (en la práctica todos comparten el mismo día).
  const dates = SUMMARY.map((t) => t.last_date).filter(Boolean).sort();
  return dates[dates.length - 1] || "—";
}

function renderSnapshotInfo() {
  document.getElementById("snapshotDate").textContent = snapshotDate();
}

function renderTable() {
  const tbody = document.querySelector("#signalsTable tbody");
  tbody.innerHTML = SUMMARY.map(
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
  ).join("");
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

init();
