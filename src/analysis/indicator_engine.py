# ============================================================================
# indicator_engine.py
# ============================================================================
"""
indicator_engine.py
Calcula indicadores técnicos sobre series normalizadas.

Responsabilidades:
- Calcular indicadores técnicos (HMA16, EMAs, VMA20).
- NO genera señales de trading (eso es responsabilidad de signal_generator.py).
"""

import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore", category=RuntimeWarning)

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.config.logging_conf import get_logger

logger = get_logger("indicator_engine")

NORMALIZED_DIR = project_root / "data_normalized" / "csv"
INDICATORS_DIR = project_root / "data_indicators" / "csv"

INDICATORS_DIR.mkdir(parents=True, exist_ok=True)


def wma(series: pd.Series, window: int) -> pd.Series:
    """Calcula la media móvil ponderada (WMA)."""
    weights = np.arange(1, window + 1)
    return series.rolling(window).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def calculate_hma(close_series: pd.Series, span: int = 16) -> pd.Series:
    """Calcula el Hull Moving Average (HMA)."""
    half_span = max(1, span // 2)
    sqrt_span = max(1, int(np.sqrt(span)))
    wma_half = wma(close_series, half_span)
    wma_full = wma(close_series, span)
    diff = 2 * wma_half - wma_full
    hma = wma(diff, sqrt_span)
    return hma.round(2)


def calculate_vma20_ratio(df: pd.DataFrame) -> pd.Series:
    """Calcula el ratio de volumen respecto a su media móvil de 20 períodos."""
    vol_ma20 = df["volume"].rolling(window=20).mean()
    vma20_ratio = df["volume"] / vol_ma20
    return vma20_ratio.round(2)


def process_ticker(ticker: str, input_file: Path) -> bool:
    """Procesa un ticker: calcula indicadores, guarda CSV y genera meta."""
    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        logger.error(f"[{ticker}] No se pudo leer input: {e}")
        return False

    required_cols = ["date", "open", "high", "low", "close", "volume", "ticker"]
    if not all(col in df.columns for col in required_cols):
        logger.warning(f"[{ticker}] Faltan columnas requeridas")
        return False

    try:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date").reset_index(drop=True)

        df["hma16"] = calculate_hma(df["close"], span=16)

        # SMAs para el método de triple alineación 10/50/100
        for span in (10, 50, 100):
            df[f"sma{span}"] = df["close"].rolling(window=span).mean().round(2)

        # EMAs para el método de cruce 12/26
        for span in (12, 26):
            ema = df["close"].ewm(span=span, adjust=False).mean()
            ema.iloc[: max(0, span - 1)] = np.nan
            df[f"ema{span}"] = ema.round(2)

        df["vma20_ratio"] = calculate_vma20_ratio(df)

        output_cols = [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "ticker",
            "hma16",
            "sma10",
            "sma50",
            "sma100",
            "ema12",
            "ema26",
            "vma20_ratio",
        ]
        df_output = df[[c for c in output_cols if c in df.columns]].copy()
        df_output["date"] = df_output["date"].dt.strftime("%Y-%m-%d")

        output_file = INDICATORS_DIR / f"{ticker}_indicators.csv"
        df_output.to_csv(output_file, index=False)

        logger.info(f"[{ticker}] OK guardado {len(df_output)} filas")
        return True

    except Exception as e:
        logger.error(f"[{ticker}] Error procesando ticker: {e}")
        return False


def main():
    """Flujo principal de cálculo de indicadores."""
    start_time = datetime.now()
    logger.info("Iniciando cálculo de indicadores")

    normalized_files = sorted(NORMALIZED_DIR.glob("*_normalized.csv"))
    if not normalized_files:
        logger.warning(f"No se encontraron archivos en {NORMALIZED_DIR}")
        return

    logger.info(f"Archivos normalized encontrados: {len(normalized_files)}")

    processed = []
    failed = []

    for file in normalized_files:
        ticker = file.stem.replace("_normalized", "")
        ok = process_ticker(ticker, file)
        if ok:
            processed.append(ticker)
        else:
            failed.append(ticker)

    end_time = datetime.now()

    sep = "=" * 60
    logger.info(sep)
    logger.info(f"  Procesados exitosamente: {len(processed)}")
    logger.info(f"  Fallidos: {len(failed)}")
    if failed:
        logger.info(f"  Lista fallidos: {', '.join(failed)}")
    logger.info(f"  Duración: {(end_time - start_time).total_seconds():.2f} segundos")
    logger.info(sep)


if __name__ == "__main__":
    main()