"""
index_dollar_comparison.py
Genera 2 graficos comparativos: indice MEP equiponderado vs tenencia de dolares MEP.
Standalone, no integrado al pipeline. Correr on-demand para regenerar PNGs de la tesis.
"""

import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.config.logging_conf import get_logger
from src.config.study_config import TICKERS_ACCIONES, STUDY_START_DATE, STUDY_END_DATE

logger = get_logger("index_dollar_comparison")

NORMALIZED_DIR = project_root / "data_normalized" / "csv"
CHARTS_DIR = project_root / "data_public" / "charts"


def load_mep_index():
    """Carga las 12 series _MEP, filtra al periodo de estudio, normaliza cada
    una a 100 en su primer dia disponible, y retorna el indice equiponderado."""
    start_ts = pd.Timestamp(STUDY_START_DATE)
    end_ts = pd.Timestamp(STUDY_END_DATE)
    series = {}
    for ba_ticker in TICKERS_ACCIONES:
        mep_ticker = ba_ticker.replace("_BA", "_MEP")
        path = NORMALIZED_DIR / f"{mep_ticker}_normalized.csv"
        if not path.exists():
            logger.warning(f"Falta {mep_ticker}_normalized.csv")
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        df = df[(df["date"] >= start_ts) & (df["date"] <= end_ts)]
        df = df.dropna(subset=["close"])
        if df.empty:
            logger.warning(f"{mep_ticker}: sin datos en el periodo")
            continue
        first_close = float(df["close"].iloc[0])
        if first_close <= 0:
            logger.warning(f"{mep_ticker}: first_close invalido ({first_close})")
            continue
        normalized = (df.set_index("date")["close"] / first_close) * 100
        series[mep_ticker] = normalized

    if not series:
        raise RuntimeError("No se cargo ninguna serie MEP - abortando.")

    df_combined = pd.DataFrame(series).sort_index()
    index_eq = df_combined.mean(axis=1)
    logger.info(
        f"Indice equiponderado: {len(series)} tickers, {len(index_eq)} dias, "
        f"primer dia={index_eq.index.min().date()}, ultimo dia={index_eq.index.max().date()}"
    )
    return index_eq


def plot_chart_a(index_series):
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(
        index_series.index, index_series.values,
        color="steelblue", linewidth=2,
        label="Indice MEP equiponderado (12 acciones)",
    )
    ax.axhline(
        100, color="gray", linestyle="--", linewidth=1.5,
        label="Tenencia de dolares MEP (base 100)",
    )
    ax.set_title("Rendimiento del indice de acciones argentinas en dolares MEP vs tenencia de dolares")
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Valor relativo (base 100)")
    ax.text(
        0.02, 0.97, f"Periodo: {STUDY_START_DATE} -> {STUDY_END_DATE}",
        transform=ax.transAxes, fontsize=9, verticalalignment="top", alpha=0.7,
    )
    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    out = CHARTS_DIR / "index_vs_dollar_A.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    logger.info(f"Grafico A guardado: {out}")


def plot_chart_b(index_series):
    dollar_relative = 10000 / index_series
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(
        dollar_relative.index, dollar_relative.values,
        color="darkorange", linewidth=2,
        label="Poder de compra de USD MEP (en terminos del indice)",
    )
    ax.axhline(
        100, color="gray", linestyle="--", linewidth=1.5,
        label="Tenencia del indice de acciones (base 100)",
    )
    ax.set_title("Poder de compra de dolares MEP en terminos del indice de acciones")
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Valor relativo (base 100)")
    ax.text(
        0.02, 0.05, f"Periodo: {STUDY_START_DATE} -> {STUDY_END_DATE}",
        transform=ax.transAxes, fontsize=9, verticalalignment="bottom", alpha=0.7,
    )
    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    out = CHARTS_DIR / "index_vs_dollar_B.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    logger.info(f"Grafico B guardado: {out}")


def main():
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando generacion de graficos indice MEP vs dolar")
    index_eq = load_mep_index()
    plot_chart_a(index_eq)
    plot_chart_b(index_eq)
    logger.info("Listo")


if __name__ == "__main__":
    main()
