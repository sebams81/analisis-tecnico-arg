"""
Validación de tesis (NO es parte del pipeline de producción de 7 módulos).

Objetivo: validar el dólar MEP sintético (precio_local_ARS / (AL30/AL30D)) contra
el ADR real cotizando en NYSE/NASDAQ en USD. Para cada acción:
  - mapea su ADR y el ratio de conversión (ADR = N acciones ordinarias locales),
  - baja el cierre diario en USD del ADR (PPI -> yfinance -> Stooq, registra fuente),
  - alinea por fechas comunes (inner join, sin rellenar) el sintético MEP con ADR/ratio,
  - calcula correlación, desfasaje medio y desviación porcentual media,
  - genera figuras de superposición.

El precio implícito por acción local en USD = precio_ADR_USD / ratio, que es lo que
el MEP sintético debería replicar.

Uso:
    python validation/adr_validation.py            # los 13
    python validation/adr_validation.py YPFD_BA    # solo uno/varios
"""

import sys
import io
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config.study_config import STUDY_START_DATE, STUDY_END_DATE  # noqa: E402

MEP_DIR = BASE_DIR / "data_normalized" / "csv"
ADR_RAW_DIR = BASE_DIR / "data_raw" / "adr"
FIG_DIR = BASE_DIR / "data_public" / "charts" / "adr_validation"
MANIFEST = ADR_RAW_DIR / "_sources.csv"

# Mapeo ADR (NYSE/NASDAQ) y ratio de conversión: 1 ADR = N acciones ordinarias locales.
ADR_MAP = {
    "PAMP_BA":  ("PAM",   25),
    "GGAL_BA":  ("GGAL",  10),
    "YPFD_BA":  ("YPF",    1),
    "BMA_BA":   ("BMA",   10),
    "CEPU_BA":  ("CEPU",  10),
    "SUPV_BA":  ("SUPV",   5),
    "BBAR_BA":  ("BBAR",   3),
    "EDN_BA":   ("EDN",   20),
    "CRES_BA":  ("CRESY", 10),
    "LOMA_BA":  ("LOMA",   5),
    "TECO2_BA": ("TEO",    5),
    "TGSU2_BA": ("TGS",    5),
    "IRSA_BA":  ("IRS",   10),
}


# --------------------------------------------------------------------------- #
# Descarga del ADR (cierre USD) con cadena de fallback y registro de fuente
# --------------------------------------------------------------------------- #
def _validate_usd(df):
    """Heurística: el ADR en USD vive en rango ~[0.5, 500]. Descarta pesos."""
    if df is None or df.empty:
        return False
    med = df["close"].median()
    return 0.3 < med < 800


def _from_ppi(adr_ticker, start, end):
    """PPI no expone ADRs de NYSE en USD (solo local/CEDEAR). Se intenta igual."""
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
        from src.ingestion.data_downloader import get_client
        ppi = get_client()
        for itype in ("ACCIONES", "CEDEARS", "ADR"):
            for settle in ("EXT-CONTADO", "A-24HS", "A-CI"):
                try:
                    raw = ppi.marketdata.search(adr_ticker, itype, settle, start, end)
                except Exception:
                    continue
                if raw:
                    df = pd.DataFrame(raw)
                    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.strftime("%Y-%m-%d")
                    df = df.rename(columns={"price": "close"})[["date", "close"]]
                    df = df.groupby("date", as_index=False)["close"].last()
                    if _validate_usd(df):
                        return df, f"PPI:{itype}/{settle}"
        return None, None
    except Exception:
        return None, None


def _from_yfinance(adr_ticker, start, end):
    try:
        import yfinance as yf
        df = yf.download(adr_ticker, start=start, end=end, auto_adjust=False, progress=False)
        if df is None or df.empty:
            return None, None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df = df.reset_index()[["Date", "Close"]].rename(columns={"Date": "date", "Close": "close"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df.dropna(subset=["close"])
        if _validate_usd(df):
            return df, "yfinance"
        return None, None
    except Exception:
        return None, None


def _from_stooq(adr_ticker, start, end):
    try:
        url = f"https://stooq.com/q/d/l/?s={adr_ticker.lower()}.us&i=d"
        r = requests.get(url, timeout=20)
        if r.status_code != 200 or "Date" not in r.text[:50]:
            return None, None
        df = pd.read_csv(io.StringIO(r.text))[["Date", "Close"]].rename(
            columns={"Date": "date", "Close": "close"})
        df = df[(df["date"] >= start) & (df["date"] <= end)].dropna(subset=["close"])
        if _validate_usd(df):
            return df, "stooq"
        return None, None
    except Exception:
        return None, None


def download_adr(adr_ticker, start, end, force=False):
    """Devuelve (df[date,close], fuente). Cachea el crudo en data_raw/adr/<ADR>.csv."""
    ADR_RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache = ADR_RAW_DIR / f"{adr_ticker}.csv"
    if cache.exists() and not force:
        df = pd.read_csv(cache)
        src = df["source"].iloc[0] if "source" in df.columns else "cache"
        return df[["date", "close"]], src

    sd = datetime.strptime(start, "%Y-%m-%d")
    ed = datetime.strptime(end, "%Y-%m-%d")
    # PPI queda FUERA de la cadena: se confirmó que no expone ADRs de NYSE en USD.
    # Peor aún, para símbolos que coinciden con un ticker local de BYMA (CEPU, SUPV,
    # EDN, LOMA) devuelve la acción local EN PESOS, un falso positivo. _from_ppi se
    # conserva documentado pero no se usa como fuente.
    _ = (_from_ppi, sd, ed)
    for fn, args in [(_from_yfinance, (adr_ticker, start, end)),
                     (_from_stooq, (adr_ticker, start, end))]:
        df, src = fn(*args)
        if df is not None and not df.empty:
            out = df.sort_values("date").copy()
            out["source"] = src
            out.to_csv(cache, index=False)
            return out[["date", "close"]], src
    raise RuntimeError(f"No se pudo bajar {adr_ticker} de ninguna fuente")


# --------------------------------------------------------------------------- #
# Métricas y figuras
# --------------------------------------------------------------------------- #
def load_synthetic_mep(local_label):
    mep = local_label.replace("_BA", "_MEP")
    df = pd.read_csv(MEP_DIR / f"{mep}_normalized.csv")[["date", "close"]]
    df = df[(df["date"] >= STUDY_START_DATE) & (df["date"] <= STUDY_END_DATE)]
    return df.rename(columns={"close": "synth"})


def load_local(local_label):
    df = pd.read_csv(MEP_DIR / f"{local_label}_normalized.csv")[["date", "close"]]
    df = df[(df["date"] >= STUDY_START_DATE) & (df["date"] <= STUDY_END_DATE)]
    return df.rename(columns={"close": "local"})


def best_lag(a, b, max_lag=5):
    """Desfasaje (ruedas) que maximiza la correlación de retornos diarios; signo:
    >0 = el sintético sigue al ADR con retraso."""
    ra = pd.Series(a).pct_change()
    rb = pd.Series(b).pct_change()
    best_k, best_c = 0, -2
    for k in range(-max_lag, max_lag + 1):
        c = ra.shift(k).corr(rb)
        if pd.notna(c) and c > best_c:
            best_c, best_k = c, k
    return best_k, best_c


def analyze(local_label, force=False):
    adr_ticker, ratio = ADR_MAP[local_label]
    adr, src = download_adr(adr_ticker, STUDY_START_DATE, STUDY_END_DATE, force=force)
    adr = adr.rename(columns={"close": "adr"})
    adr["implied"] = adr["adr"] / ratio

    synth = load_synthetic_mep(local_label)
    m = pd.merge(synth, adr, on="date", how="inner").sort_values("date").reset_index(drop=True)

    corr = m["synth"].corr(m["implied"])
    lag, _ = best_lag(m["synth"].values, m["implied"].values)
    pct_dev = ((m["synth"] - m["implied"]).abs() / m["implied"]).mean() * 100
    # ratio empírico: cuántas acciones locales replica 1 ADR según los precios.
    # Debe coincidir con el ratio asumido; si difiere, el ratio del mapeo está mal.
    emp_ratio = (m["adr"] / m["synth"]).median()

    return {
        "local": local_label, "adr": adr_ticker, "ratio": ratio, "source": src,
        "n_common": len(m), "correlation": corr, "avg_lag": lag,
        "mean_pct_dev": pct_dev, "emp_ratio": emp_ratio, "merged": m,
    }


def make_figures(res):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    local_label = res["local"]
    m = res["merged"].copy()
    m["d"] = pd.to_datetime(m["date"])
    tag = local_label.replace("_BA", "")

    # Figura A: sintético MEP vs ADR/ratio en dólares reales
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.plot(m["d"], m["implied"], label=f"ADR {res['adr']}/{res['ratio']} (USD real)", lw=1.3, color="#c0392b")
    ax.plot(m["d"], m["synth"], label="MEP sintético (USD)", lw=1.3, color="#2c3e50")
    ax.set_title(f"{tag} — MEP sintético vs ADR real en USD\n"
                 f"corr={res['correlation']:.3f} · desf={res['avg_lag']} ruedas · "
                 f"desv.media={res['mean_pct_dev']:.1f}% · fuente={res['source']}")
    ax.set_ylabel("USD por acción local"); ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout()
    pa = FIG_DIR / f"{tag}_usd.png"
    fig.savefig(pa, dpi=180); plt.close(fig)

    # Figura B: las dos anteriores + local, todo indexado a base 100
    loc = load_local(local_label)
    mb = pd.merge(m[["date", "synth", "implied"]], loc, on="date", how="inner").sort_values("date")
    mb["d"] = pd.to_datetime(mb["date"])
    for c in ["synth", "implied", "local"]:
        mb[c + "_i"] = mb[c] / mb[c].iloc[0] * 100
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.plot(mb["d"], mb["implied_i"], label=f"ADR {res['adr']}/{res['ratio']} (USD)", lw=1.3, color="#c0392b")
    ax.plot(mb["d"], mb["synth_i"], label="MEP sintético (USD)", lw=1.3, color="#2c3e50")
    ax.plot(mb["d"], mb["local_i"], label="Local (ARS)", lw=1.1, color="#7f8c8d", ls="--")
    ax.set_title(f"{tag} — Base 100 ({mb['date'].iloc[0]}): MEP sintético, ADR/ratio y local")
    ax.set_ylabel("Índice base 100"); ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout()
    pb = FIG_DIR / f"{tag}_base100.png"
    fig.savefig(pb, dpi=180); plt.close(fig)
    return pa, pb


def main(targets=None, make_figs_for=None, force=False):
    targets = targets or list(ADR_MAP.keys())
    rows = []
    for t in targets:
        res = analyze(t, force=force)
        rows.append(res)
        figs = ""
        if make_figs_for is None or t in make_figs_for:
            pa, pb = make_figures(res)
            figs = f" | figs: {pa.name}, {pb.name}"
        print(f"{t:9} ADR={res['adr']:5} ratio={res['ratio']:>3} | n={res['n_common']:4} "
              f"corr={res['correlation']:.3f} lag={res['avg_lag']:+d} "
              f"desv={res['mean_pct_dev']:5.1f}% | fuente={res['source']}{figs}")
    # manifest de fuentes/ratios
    mani = pd.DataFrame([{k: r[k] for k in ("local", "adr", "ratio", "emp_ratio", "source",
                          "n_common", "correlation", "avg_lag", "mean_pct_dev")} for r in rows])
    if len(rows) == len(ADR_MAP):
        print(f"\nMedia de correlación sobre los {len(rows)}: {mani['correlation'].mean():.4f}")
    ADR_RAW_DIR.mkdir(parents=True, exist_ok=True)
    mani.to_csv(MANIFEST, index=False)
    return rows


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    main(targets=args or None)
