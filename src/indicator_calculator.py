#!/usr/bin/env python3
"""
indicator_calculator.py

Calcula indicadores técnicos por ticker a partir de archivos normalizados.

Convenciones de rutas:
- Entrada:  data_normalized/csv/<TICKER>_normalized.csv
- Salida:   data_indicators/csv/<TICKER>_indicators.csv
- Meta:     data_indicators/meta/<TICKER>_indicators.meta.json
"""

from pathlib import Path
from datetime import datetime
import argparse
import json
import hashlib
import logging
import sys
import traceback

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]

DATA_NORMALIZED_CSV_DIR = BASE_DIR / "data_normalized" / "csv"
DATA_INDICATORS_CSV_DIR = BASE_DIR / "data_indicators" / "csv"
DATA_INDICATORS_META_DIR = BASE_DIR / "data_indicators" / "meta"
LOG_DIR = BASE_DIR / "logs"

DEFAULT_HMA_SPAN = 16
EMA_SPANS = [10, 12, 26, 50, 100]
DEFAULT_MIN_HISTORY = 120
PHASE_CONFIRMATION = 2  # número de ruedas para considerar fase establecida

LOGGER = None


def setup_logger():
    """Configura logger que escribe a archivo y stdout."""
    global LOGGER
    if LOGGER:
        return LOGGER
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("indicator_calculator")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(LOG_DIR / "indicator_calculator.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    LOGGER = logger
    return LOGGER


def file_md5(path: Path, chunk_size: int = 8192) -> str:
    """MD5 de archivo para metadata."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dirs():
    """Crear directorios necesarios si no existen."""
    DATA_NORMALIZED_CSV_DIR.mkdir(parents=True, exist_ok=True)
    DATA_INDICATORS_CSV_DIR.mkdir(parents=True, exist_ok=True)
    DATA_INDICATORS_META_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------
# Promedios ponderados y HMA
# -----------------------------
def wma(series: pd.Series, window: int, min_periods: int = None) -> pd.Series:
    """
    Weighted Moving Average con pesos lineales en la ventana.
    Devuelve NaN donde no hay suficientes datos (min_periods).
    """
    if min_periods is None:
        min_periods = window

    def _w(x):
        if len(x) < min_periods:
            return np.nan
        w_local = np.arange(1, len(x) + 1)
        return np.dot(x, w_local) / w_local.sum()

    return series.rolling(window=window, min_periods=min_periods).apply(_w, raw=True)


def calculate_hma(close_series: pd.Series, span: int = DEFAULT_HMA_SPAN) -> pd.Series:
    """Calcula HMA siguiendo la definición estándar y redondea a 2 decimales."""
    half_span = max(1, span // 2)
    sqrt_span = max(1, int(np.sqrt(span)))
    wma_half = wma(close_series, half_span, min_periods=half_span)
    wma_full = wma(close_series, span, min_periods=span)
    diff = 2 * wma_half - wma_full
    hma = wma(diff, sqrt_span, min_periods=max(1, sqrt_span))
    return hma.round(2)


# -----------------------------
# Lógica de tendencia (general)
# -----------------------------
def _trend_from_slope_sequence(slope_seq, confirmation=PHASE_CONFIRMATION):
    """
    Convierte secuencia de pendientes ('up'/'down'/None) en etiquetas:
    'Indeterminado', 'Compra', 'Alcista', 'Venta', 'Bajista'.
    La transición a fase 'Alcista'/'Bajista' requiere 'confirmation' observaciones.
    """
    state = []
    prev = None
    consecutive = 0
    for s in slope_seq:
        if s is None:
            state.append("Indeterminado")
            prev = None
            consecutive = 0
            continue
        if prev is None:
            if s == 'up':
                consecutive = 1
                state.append("Compra")
                prev = 'up'
            elif s == 'down':
                consecutive = 1
                state.append("Bajista")
                prev = 'down'
            else:
                state.append("Indeterminado")
        else:
            if s == prev:
                consecutive += 1
                if consecutive >= confirmation:
                    state.append("Alcista" if s == 'up' else "Bajista")
                else:
                    state.append("Compra" if s == 'up' else "Venta")
            else:
                consecutive = 1
                prev = s
                state.append("Compra" if s == 'up' else "Venta" if s == 'down' else "Indeterminado")
    return state


def calculate_hma_trend(hma_series: pd.Series, confirmation: int = PHASE_CONFIRMATION) -> pd.Series:
    """Calcula tendencia sobre HMA respetando NaN como 'Indeterminado'."""
    slopes = []
    for i in range(len(hma_series)):
        if i == 0:
            slopes.append(None)
            continue
        cur = hma_series.iloc[i]
        prev = hma_series.iloc[i - 1]
        if pd.isna(cur) or pd.isna(prev):
            slopes.append(None)
            continue
        slopes.append('up' if cur > prev else 'down' if cur < prev else None)
    trend = _trend_from_slope_sequence(slopes, confirmation=confirmation)
    return pd.Series(trend, index=hma_series.index)


def _ema_crossover_trend(short_series: pd.Series, long_series: pd.Series, confirmation: int = PHASE_CONFIRMATION):
    """Tendencia genérica por cruce de dos EMAs."""
    slopes = []
    for i in range(len(short_series)):
        short = short_series.iloc[i]
        long = long_series.iloc[i]
        if pd.isna(short) or pd.isna(long):
            slopes.append(None)
            continue
        slopes.append('up' if short > long else 'down' if short < long else None)
    trend = _trend_from_slope_sequence(slopes, confirmation=confirmation)
    return pd.Series(trend, index=short_series.index)


def calculate_ema_crossover_trend_12_26(ema12_series: pd.Series, ema26_series: pd.Series, confirmation: int = PHASE_CONFIRMATION):
    return _ema_crossover_trend(ema12_series, ema26_series, confirmation=confirmation)


def calculate_ema_crossover_trend_10_50_100(ema10_series: pd.Series, ema50_series: pd.Series, confirmation: int = PHASE_CONFIRMATION):
    return _ema_crossover_trend(ema10_series, ema50_series, confirmation=confirmation)


# -----------------------------
# VMA20 y categorías
# -----------------------------
def calculate_vma20(df: pd.DataFrame) -> pd.Series:
    """VMA20 = volume / rolling_mean(volume, 20). Devuelve NaN si la media es 0 o inválida."""
    vol_ma20 = df['volume'].rolling(window=20, min_periods=1).mean()
    with np.errstate(divide='ignore', invalid='ignore'):
        vma20 = df['volume'] / vol_ma20
    vma20 = vma20.replace([np.inf, -np.inf], np.nan)
    return vma20.round(2)


def categorize_vma20(vma20_series: pd.Series) -> pd.Series:
    """Categoriza VMA20 según rangos; NaN -> ''."""
    conds = [
        vma20_series.isna(),
        vma20_series < 0.7,
        (vma20_series >= 0.7) & (vma20_series < 0.9),
        (vma20_series >= 0.9) & (vma20_series < 1.3),
        (vma20_series >= 1.3) & (vma20_series < 2.0),
        vma20_series >= 2.0
    ]
    choices = ['', 'Muy Bajo', 'Bajo', 'Medio', 'Alto', 'Muy Alto']
    return pd.Series(np.select(conds, choices, default=''), index=vma20_series.index)


# -----------------------------
# Patrones de velas y señales
# -----------------------------
def identify_candle_pattern(df: pd.DataFrame) -> pd.Series:
    """
    Identifica Doji, Marubozu y Engulfing.
    Devuelve cadena vacía si no hay patrón o falta dato.
    """
    for col in ['open', 'high', 'low', 'close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    n = len(df)
    patterns = [''] * n
    open_vals = df['open'].values
    close_vals = df['close'].values
    high_vals = df['high'].values
    low_vals = df['low'].values

    body = close_vals - open_vals
    rng = high_vals - low_vals

    # Evitar división por cero y warnings: usar np.divide con where
    body_pct = np.zeros_like(body, dtype=float)
    np.divide(np.abs(body), rng, out=body_pct, where=rng > 0)

    upper_shadow = high_vals - np.maximum(open_vals, close_vals)
    lower_shadow = np.minimum(open_vals, close_vals) - low_vals

    for i in range(n):
        try:
            if np.isnan(open_vals[i]) or np.isnan(close_vals[i]) or np.isnan(high_vals[i]) or np.isnan(low_vals[i]):
                patterns[i] = ''
                continue
            pattern = ''
            # Engulfing (necesita vela anterior)
            if i > 0:
                open_t = open_vals[i]; close_t = close_vals[i]; body_t = body[i]
                open_y = open_vals[i - 1]; close_y = close_vals[i - 1]; body_y = body[i - 1]
                if (body_y < 0 and body_t > 0 and close_t > open_y and open_t < close_y):
                    pattern = 'Engulfing_Alc'
                elif (body_y > 0 and body_t < 0 and open_t > close_y and close_t < open_y):
                    pattern = 'Engulfing_Baj'
            # Patrones de una vela
            if pattern == '':
                r = rng[i]; bp = body_pct[i]; b = body[i]; us = upper_shadow[i]; ls = lower_shadow[i]
                if r > 0 and bp < 0.1:
                    pattern = 'Doji'
                elif bp > 0.8 and b > 0 and us < 0.1 * r and ls < 0.1 * r:
                    pattern = 'Marubozu_Alc'
                elif bp > 0.8 and b < 0 and us < 0.1 * r and ls < 0.1 * r:
                    pattern = 'Marubozu_Baj'
            patterns[i] = pattern
        except Exception:
            patterns[i] = ''
            continue
    return pd.Series(patterns, index=df.index)


def calculate_candle_signal(candle_pattern_series: pd.Series) -> pd.Series:
    """
    Señal derivada de patrones con lookback de hasta 3 ruedas.
    Prioridad: patrón de hoy > contexto pasado > Neutra.
    """
    n = len(candle_pattern_series)
    signals = ['Neutra'] * n
    for i in range(n):
        pat = candle_pattern_series.iloc[i]
        if pd.isna(pat) or pat == '':
            found = False
            for lookback in range(1, 4):
                j = i - lookback
                if j < 0:
                    break
                pat_past = candle_pattern_series.iloc[j]
                if pat_past in ('Engulfing_Alc', 'Marubozu_Alc'):
                    signals[i] = f'Alcista {lookback} rueda{"s" if lookback > 1 else ""} atras'
                    found = True
                    break
                if pat_past in ('Engulfing_Baj', 'Marubozu_Baj'):
                    signals[i] = f'Bajista {lookback} rueda{"s" if lookback > 1 else ""} atras'
                    found = True
                    break
            if not found:
                signals[i] = 'Neutra'
        else:
            if pat in ('Engulfing_Alc', 'Marubozu_Alc'):
                signals[i] = 'Alcista'
            elif pat in ('Engulfing_Baj', 'Marubozu_Baj'):
                signals[i] = 'Bajista'
            elif pat == 'Doji':
                signals[i] = 'Indeterminacion'
            else:
                signals[i] = 'Neutra'
    return pd.Series(signals, index=candle_pattern_series.index)


# -----------------------------
# Procesamiento por ticker
# -----------------------------
def process_ticker(ticker: str,
                   input_dir: Path,
                   output_dir: Path,
                   meta_dir: Path,
                   hma_span: int = DEFAULT_HMA_SPAN,
                   ema_spans: list = EMA_SPANS,
                   min_history: int = DEFAULT_MIN_HISTORY,
                   confirmation: int = PHASE_CONFIRMATION):
    """
    Lee <ticker>_normalized.csv, calcula indicadores y guarda CSV + metadata.
    Se aplica limpieza conservadora y se registra filas descartadas.
    """
    logger = setup_logger()
    input_file = input_dir / f"{ticker}_normalized.csv"
    if not input_file.exists():
        logger.warning("Archivo no encontrado: %s", input_file)
        return

    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        logger.error("No se pudo leer %s: %s", input_file, e)
        return

    required_cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'ticker']
    if not all(col in df.columns for col in required_cols):
        logger.warning("Faltan columnas requeridas en %s", input_file)
        return

    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.sort_values('date').reset_index(drop=True)
    initial_rows = len(df)

    # Eliminamos filas sin fecha o sin close; esto es explícito y queda en metadata
    df_clean = df.dropna(subset=['date', 'close'])
    dropped_rows = initial_rows - len(df_clean)
    if df_clean.empty:
        logger.warning("%s no tiene filas válidas después de limpieza. Archivo saltado.", ticker)
        return

    enough_history = len(df_clean) >= min_history
    df_calc = df_clean.copy().reset_index(drop=True)

    # Indicadores principales
    df_calc['hma16'] = calculate_hma(df_calc['close'], span=hma_span)
    df_calc['T_hma16'] = calculate_hma_trend(df_calc['hma16'], confirmation=confirmation)

    for span in ema_spans:
        ema = df_calc['close'].ewm(span=span, adjust=False, min_periods=span).mean()
        df_calc[f'ema{span}'] = ema.round(2)

    if 'ema12' in df_calc.columns and 'ema26' in df_calc.columns:
        df_calc['T_ema12_26'] = calculate_ema_crossover_trend_12_26(df_calc['ema12'], df_calc['ema26'], confirmation=confirmation)
    else:
        df_calc['T_ema12_26'] = pd.Series(['Indeterminado'] * len(df_calc), index=df_calc.index)

    if 'ema10' in df_calc.columns and 'ema50' in df_calc.columns:
        df_calc['T_ema10_50_100'] = calculate_ema_crossover_trend_10_50_100(df_calc['ema10'], df_calc['ema50'], confirmation=confirmation)
    else:
        df_calc['T_ema10_50_100'] = pd.Series(['Indeterminado'] * len(df_calc), index=df_calc.index)

    df_calc['vma20'] = calculate_vma20(df_calc)
    df_calc['vma20_cat'] = categorize_vma20(df_calc['vma20'])

    df_calc['candle_pattern'] = identify_candle_pattern(df_calc)
    df_calc['candle_signal'] = calculate_candle_signal(df_calc['candle_pattern'])

    # Preparar columnas de salida en orden consistente
    output_cols = [
        'date', 'open', 'high', 'low', 'close', 'volume', 'ticker',
        'vma20', 'vma20_cat'
    ]
    for span in sorted(ema_spans):
        output_cols.append(f'ema{span}')
    output_cols += [
        'hma16',
        'T_ema12_26', 'T_ema10_50_100', 'T_hma16',
        'candle_pattern', 'candle_signal'
    ]
    for col in output_cols:
        if col not in df_calc.columns:
            df_calc[col] = np.nan if col not in ['ticker', 'candle_pattern', 'candle_signal', 'vma20_cat'] else ''

    df_calc['date'] = pd.to_datetime(df_calc['date'], errors='coerce').dt.strftime('%Y-%m-%d')

    # Escritura atómica del CSV y metadata
    out_file = output_dir / f"{ticker}_indicators.csv"
    tmp_file = out_file.with_suffix('.csv.tmp')
    try:
        df_calc[output_cols].to_csv(tmp_file, index=False)
        tmp_file.replace(out_file)
    except Exception as e:
        logger.error("Error guardando %s: %s", out_file, e)
        return

    meta = {
        "ticker": ticker,
        "source_file": str(input_file.as_posix()),
        "generated_at": datetime.now().astimezone().isoformat(),
        "params": {
            "hma_span": hma_span,
            "ema_spans": ema_spans,
            "min_history": min_history,
            "phase_confirmation": confirmation
        },
        "rows_in": initial_rows,
        "rows_clean": len(df_clean),
        "dropped_rows": dropped_rows,
        "included_in_analysis": bool(enough_history),
        "output_rows": len(df_calc),
        "md5": None
    }
    try:
        meta["md5"] = file_md5(out_file)
    except Exception:
        meta["md5"] = None

    meta_file = meta_dir / f"{ticker}_indicators.meta.json"
    try:
        with open(meta_file.with_suffix('.json.tmp'), 'w', encoding='utf-8') as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
        Path(meta_file.with_suffix('.json.tmp')).replace(meta_file)
    except Exception as e:
        logger.warning("No se pudo guardar metadata %s: %s", meta_file, e)

    logger.info("%s: filas_in=%d filas_out=%d dropped=%d included=%s", ticker, initial_rows, len(df_calc), dropped_rows, enough_history)


# -----------------------------
# CLI / Main
# -----------------------------
def parse_args():
    p = argparse.ArgumentParser(prog="indicator_calculator", description="Calcula indicadores técnicos por ticker")
    p.add_argument("--min-history", type=int, default=DEFAULT_MIN_HISTORY, help="Min filas para considerar ticker en análisis")
    p.add_argument("--limit", type=int, default=0, help="Limitar número de archivos procesados (0 = todos)")
    p.add_argument("--confirmation", type=int, default=PHASE_CONFIRMATION, help="Ruedas consecutivas para considerar fase establecida")
    p.add_argument("--hma-span", type=int, default=DEFAULT_HMA_SPAN, help="Span para HMA")
    p.add_argument("--tickers", type=str, help="Lista de tickers separados por comas para procesar (sin sufijo _normalized)")
    return p.parse_args()


def main():
    ensure_dirs()
    logger = setup_logger()
    args = parse_args()

    normalized_files = sorted(DATA_NORMALIZED_CSV_DIR.glob('*_normalized.csv'))
    if not normalized_files:
        logger.warning("No se encontraron archivos en %s", DATA_NORMALIZED_CSV_DIR)
        return

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = [f.stem.replace('_normalized', '') for f in normalized_files]

    if args.limit and args.limit > 0:
        tickers = tickers[:args.limit]

    logger.info("Procesando %d tickers en %s -> %s", len(tickers), DATA_NORMALIZED_CSV_DIR, DATA_INDICATORS_CSV_DIR)

    for ticker in tickers:
        try:
            logger.info("Procesando %s...", ticker)
            process_ticker(
                ticker=ticker,
                input_dir=DATA_NORMALIZED_CSV_DIR,
                output_dir=DATA_INDICATORS_CSV_DIR,
                meta_dir=DATA_INDICATORS_META_DIR,
                hma_span=args.hma_span,
                ema_spans=EMA_SPANS,
                min_history=args.min_history,
                confirmation=args.confirmation
            )
        except Exception as e:
            logger.error("Excepción procesando %s: %s", ticker, e)
            logger.debug(traceback.format_exc())

    logger.info("Módulo 3 completado")


if __name__ == "__main__":
    main()