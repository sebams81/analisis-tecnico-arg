"""
Figuras de la seccion 6.4 (validacion visual MEP sintetico vs ADR real).
Validacion de tesis, NO parte del pipeline de produccion.

Por ticker genera 2 PNG (sin titulo embebido; el epigrafe los nombra):
  {fig}_usd.png      -> MEP sintetico y ADR/ratio, en dolares por accion local.
  {fig}_base100.png  -> MEP sintetico, ADR/ratio y local (pesos), base 100 en
                        la primera rueda comun.

Datos: MEP sintetico del pipeline (data_normalized/csv/*_MEP_normalized.csv) +
ADR crudo congelado (data_raw/adr/*.csv). Inner join por fecha, desfasaje cero,
sin rellenar. Ratios oficiales.
"""

import sys
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
from src.config.study_config import STUDY_START_DATE, STUDY_END_DATE  # noqa: E402

MEP_DIR = BASE_DIR / "data_normalized" / "csv"
ADR_DIR = BASE_DIR / "data_raw" / "adr"
OUT_DIR = BASE_DIR / "data_public" / "charts" / "adr_validation"

# (nombre_figura, label_local, ticker_ADR, ratio_oficial)
SPECS = [
    ("YPF",  "YPFD_BA", "YPF",   1),
    ("GGAL", "GGAL_BA", "GGAL",  10),
    ("CRES", "CRES_BA", "CRESY", 10),
]

C_MEP, C_ADR, C_LOCAL = "steelblue", "darkorange", "dimgray"


def _load_window(col, path):
    df = pd.read_csv(path, parse_dates=["date"])[["date", "close"]].dropna(subset=["close"])
    df = df[(df["date"] >= pd.Timestamp(STUDY_START_DATE)) & (df["date"] <= pd.Timestamp(STUDY_END_DATE))]
    return df.rename(columns={"close": col})


def _fmt_dates(ax):
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_minor_locator(mdates.MonthLocator((1, 4, 7, 10)))


def make_pair(figname, local_label, adr_ticker, ratio):
    mep_label = local_label.replace("_BA", "_MEP")
    synth = _load_window("synth", MEP_DIR / f"{mep_label}_normalized.csv")
    local = _load_window("local", MEP_DIR / f"{local_label}_normalized.csv")
    adr = _load_window("adr", ADR_DIR / f"{adr_ticker}.csv")
    adr["implied"] = adr["adr"] / ratio

    # --- usd: ventana comun MEP & ADR ---
    m = pd.merge(synth, adr[["date", "implied"]], on="date", how="inner").sort_values("date")
    # diagnostico de cobertura (no rellena, solo informa)
    gap = m["date"].diff().dt.days
    info = {
        "fig": figname, "n_usd": len(m),
        "ini": m["date"].min().date(), "fin": m["date"].max().date(),
        "max_gap_dias": int(gap.max()) if len(m) > 1 else 0,
    }

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(m["date"], m["implied"], color=C_ADR, linewidth=2, label="ADR/ratio")
    ax.plot(m["date"], m["synth"], color=C_MEP, linewidth=2, label="MEP sintético")
    ax.set_xlabel("Fecha"); ax.set_ylabel("Precio en dólares")
    ax.grid(alpha=0.3); ax.legend(loc="best"); _fmt_dates(ax)
    fig.tight_layout()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / f"{figname}_usd.png", dpi=200); plt.close(fig)

    # --- base100: ventana comun de las TRES ---
    b = pd.merge(m[["date", "synth", "implied"]], local, on="date", how="inner").sort_values("date").reset_index(drop=True)
    for c in ("synth", "implied", "local"):
        b[c + "_i"] = b[c] / b[c].iloc[0] * 100
    info["n_base100"] = len(b)
    info["base_date"] = b["date"].iloc[0].date()

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(b["date"], b["synth_i"], color=C_MEP, linewidth=2, label="MEP sintético")
    ax.plot(b["date"], b["implied_i"], color=C_ADR, linewidth=2, label="ADR/ratio")
    ax.plot(b["date"], b["local_i"], color=C_LOCAL, linewidth=1.6, label="Local (pesos)")
    ax.set_xlabel("Fecha"); ax.set_ylabel("Índice base 100")
    ax.grid(alpha=0.3); ax.legend(loc="best"); _fmt_dates(ax)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{figname}_base100.png", dpi=200); plt.close(fig)
    return info


def main():
    for figname, local, adr, ratio in SPECS:
        i = make_pair(figname, local, adr, ratio)
        print(f"{i['fig']:5} usd: n={i['n_usd']} ({i['ini']}->{i['fin']}, gap max {i['max_gap_dias']}d) | "
              f"base100: n={i['n_base100']} base={i['base_date']} | "
              f"PNG: {i['fig']}_usd.png, {i['fig']}_base100.png")


if __name__ == "__main__":
    main()
