# ============================================================================
# signal_generator.py
# ============================================================================
"""
signal_generator.py
Genera señales de trading basadas en indicadores técnicos.

Responsabilidades:
- Interpretar indicadores y generar señales de tendencia.
- Identificar patrones de velas japonesas.
- Clasificar volumen en categorías cualitativas.
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

logger = get_logger("signal_generator")

INDICATORS_DIR = project_root / "data_indicators" / "csv"
SIGNALS_DIR = project_root / "data_signals" / "csv"

SIGNALS_DIR.mkdir(parents=True, exist_ok=True)


_NAN = object()  # sentinel para input invalido; distinto de None (carry-forward de prev_state)


def _trend_state_machine(n, get_state, reset_opposite_in_continuation):
    """State machine compartida por las 3 funciones de tendencia.

    get_state(i, prev_state) retorna _NAN si input invalido, "up"/"down"/None si valido.
    reset_opposite_in_continuation: legacy del HMA original (dead code en la practica).
    """
    trend = ["Neutra"]
    prev_state = None
    up_turn_count = 0
    down_turn_count = 0

    for i in range(1, n):
        state = get_state(i, prev_state)

        if state is _NAN:
            trend.append("Neutra")
            prev_state = None
            up_turn_count = 0
            down_turn_count = 0
            continue

        if prev_state is None:
            if state == "up":
                trend.append("Compra Temprana")
                up_turn_count = 1
            elif state == "down":
                trend.append("Venta Temprana")
            else:
                trend.append("Neutra")
        else:
            if state == "up" and prev_state != "up":
                up_turn_count = 1
                down_turn_count = 0
                trend.append("Compra Temprana")
            elif state == "down" and prev_state != "down":
                down_turn_count = 1
                up_turn_count = 0
                trend.append("Venta Temprana")
            else:
                if state == "up":
                    if 0 < up_turn_count < 2:
                        up_turn_count += 1
                        trend.append("Compra Confirmada")
                    else:
                        trend.append("Señal Alcista")
                        if reset_opposite_in_continuation:
                            down_turn_count = 0
                elif state == "down":
                    if 0 < down_turn_count < 2:
                        down_turn_count += 1
                        trend.append("Venta Confirmada")
                    else:
                        trend.append("Señal Bajista")
                        if reset_opposite_in_continuation:
                            up_turn_count = 0
                else:
                    trend.append(trend[-1])

        prev_state = state

    return trend


def calculate_hma_trend(hma_series: pd.Series) -> list:
    """Genera señales de tendencia basadas en la pendiente del HMA."""
    def get_state(i, prev_state):
        cur = hma_series.iloc[i]
        prev = hma_series.iloc[i - 1]
        if pd.isna(cur) or pd.isna(prev):
            return _NAN
        if cur > prev:
            return "up"
        if cur < prev:
            return "down"
        return prev_state
    return _trend_state_machine(
        len(hma_series), get_state, reset_opposite_in_continuation=True
    )


def calculate_ema_crossover_trend_12_26(
    ema12_series: pd.Series, ema26_series: pd.Series
) -> list:
    """Genera señales de tendencia basadas en el cruce de EMA12 y EMA26."""
    def get_state(i, prev_state):
        ema12 = ema12_series.iloc[i]
        ema26 = ema26_series.iloc[i]
        if pd.isna(ema12) or pd.isna(ema26):
            return _NAN
        if ema12 > ema26:
            return "up"
        if ema12 < ema26:
            return "down"
        return prev_state
    return _trend_state_machine(
        len(ema12_series), get_state, reset_opposite_in_continuation=False
    )


def calculate_sma_crossover_trend_10_50_100(
    sma10_series: pd.Series, sma50_series: pd.Series, sma100_series: pd.Series
) -> list:
    """Genera señales basadas en alineación SMA10 > SMA50 > SMA100 (up)
    o SMA10 < SMA50 < SMA100 (down). Alineación parcial mantiene tendencia previa."""
    def get_state(i, prev_state):
        s10 = sma10_series.iloc[i]
        s50 = sma50_series.iloc[i]
        s100 = sma100_series.iloc[i]
        if pd.isna(s10) or pd.isna(s50) or pd.isna(s100):
            return _NAN
        if s10 > s50 > s100:
            return "up"
        if s10 < s50 < s100:
            return "down"
        return None
    return _trend_state_machine(
        len(sma10_series), get_state, reset_opposite_in_continuation=False
    )


def categorize_vma20(vma20_series: pd.Series) -> np.ndarray:
    """Categoriza el VMA20 en niveles cualitativos."""
    conditions = [
        vma20_series.isna(),
        vma20_series < 0.7,
        (vma20_series >= 0.7) & (vma20_series < 0.9),
        (vma20_series >= 0.9) & (vma20_series < 1.3),
        (vma20_series >= 1.3) & (vma20_series < 2.0),
        vma20_series >= 2.0,
    ]
    choices = ["", "Muy Bajo", "Bajo", "Neutro", "Alto", "Muy Alto"]
    return np.select(conditions, choices, default="")


def identify_candle_pattern(df: pd.DataFrame) -> list:
    """Identifica patrones de velas japonesas."""
    body = (df["close"] - df["open"]).values
    range_val = (df["high"] - df["low"]).values
    body_pct = np.where(range_val > 0, np.abs(body) / range_val, 0)
    upper_shadow = (df["high"] - df[["open", "close"]].max(axis=1)).values
    lower_shadow = (df[["open", "close"]].min(axis=1) - df["low"]).values
    open_vals = df["open"].values
    close_vals = df["close"].values

    patterns = []
    for i in range(len(df)):
        pattern = ""

        if i > 0:
            open_today = open_vals[i]
            close_today = close_vals[i]
            body_today = body[i]
            open_yesterday = open_vals[i - 1]
            close_yesterday = close_vals[i - 1]
            body_yesterday = body[i - 1]

            if (
                body_yesterday < 0
                and body_today > 0
                and close_today > open_yesterday
                and open_today < close_yesterday
            ):
                pattern = "Engulfing_Alc"
            elif (
                body_yesterday > 0
                and body_today < 0
                and open_today > close_yesterday
                and close_today < open_yesterday
            ):
                pattern = "Engulfing_Baj"

        if pattern == "":
            r = range_val[i]
            bp = body_pct[i]
            b = body[i]
            us = upper_shadow[i]
            ls = lower_shadow[i]

            if bp < 0.1 and r > 0:
                pattern = "Doji"
            elif bp > 0.8 and b > 0 and us < 0.1 * r and ls < 0.1 * r:
                pattern = "Marubozu_Alc"
            elif bp > 0.8 and b < 0 and us < 0.1 * r and ls < 0.1 * r:
                pattern = "Marubozu_Baj"

        patterns.append(pattern)

    return patterns


def process_ticker(ticker: str, input_file: Path) -> bool:
    """Procesa un ticker: genera señales, guarda CSV y genera meta."""
    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        logger.error(f"[{ticker}] No se pudo leer input: {e}")
        return False

    required_cols = [
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
    if not all(col in df.columns for col in required_cols):
        logger.warning(f"[{ticker}] Faltan columnas requeridas")
        return False

    try:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date").reset_index(drop=True)

        df["T_hma16"] = calculate_hma_trend(df["hma16"])

        if "ema12" in df.columns and "ema26" in df.columns:
            df["T_ema12_26"] = calculate_ema_crossover_trend_12_26(
                df["ema12"], df["ema26"]
            )

        if "sma10" in df.columns and "sma50" in df.columns and "sma100" in df.columns:
            df["T_sma10_50_100"] = calculate_sma_crossover_trend_10_50_100(
                df["sma10"], df["sma50"], df["sma100"]
            )

        df["vma20_cat"] = categorize_vma20(df["vma20_ratio"])
        df["candle_pattern"] = identify_candle_pattern(df)

        output_cols = [
            "date",
            "ticker",
            "T_hma16",
            "T_ema12_26",
            "T_sma10_50_100",
            "vma20_cat",
            "candle_pattern",
        ]
        df_output = df[[c for c in output_cols if c in df.columns]].copy()
        df_output["date"] = df_output["date"].dt.strftime("%Y-%m-%d")

        output_file = SIGNALS_DIR / f"{ticker}_signals.csv"
        df_output.to_csv(output_file, index=False)

        logger.info(f"[{ticker}] OK guardado {len(df_output)} filas")
        return True

    except Exception as e:
        logger.error(f"[{ticker}] Error procesando ticker: {e}")
        return False


def main():
    """Flujo principal de generación de señales."""
    start_time = datetime.now()
    logger.info("Iniciando generación de señales")

    indicators_files = sorted(INDICATORS_DIR.glob("*_indicators.csv"))
    if not indicators_files:
        logger.warning(f"No se encontraron archivos en {INDICATORS_DIR}")
        return

    logger.info(f"Archivos indicators encontrados: {len(indicators_files)}")

    processed = []
    failed = []

    for file in indicators_files:
        ticker = file.stem.replace("_indicators", "")
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