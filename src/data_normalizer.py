#!/usr/bin/env python3
"""
data_normalizer.py

Normaliza CSVs descargados en data_raw/csv y genera:
- data_normalized/csv/<TICKER>_normalized.csv
- data_normalized/meta/<TICKER>_normalized.meta.json

Política conservadora por defecto:
- Detecta gaps y los deja como NaN
- No imputa datos para cálculos ni backtest
- Opción --visual-fill para forward-fill solo para visualización (marcado en metadata)
- Usa días hábiles (--use-business-days) por defecto para detectar gaps reales de mercado
"""
from pathlib import Path
from datetime import datetime
import argparse
import json
import hashlib
import logging
import sys
import traceback

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]

# Rutas según estructura propuesta
DATA_RAW_CSV_DIR = BASE_DIR / "data_raw" / "csv"
DATA_NORMALIZED_CSV_DIR = BASE_DIR / "data_normalized" / "csv"
DATA_NORMALIZED_META_DIR = BASE_DIR / "data_normalized" / "meta"
LOG_DIR = BASE_DIR / "logs"

NORMAL_COLUMNS = ["date", "open", "high", "low", "close", "volume", "ticker"]

LOGGER = None


def ensure_dirs():
    DATA_RAW_CSV_DIR.mkdir(parents=True, exist_ok=True)
    DATA_NORMALIZED_CSV_DIR.mkdir(parents=True, exist_ok=True)
    DATA_NORMALIZED_META_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logger():
    global LOGGER
    if LOGGER:
        return LOGGER
    logger = logging.getLogger("data_normalizer")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(LOG_DIR / "data_normalizer.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    LOGGER = logger
    return LOGGER


def file_md5(path: Path, chunk_size: int = 8192) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _flatten_columns_if_needed(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _find_col(df: pd.DataFrame, candidates):
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand is None:
            continue
        key = cand.lower()
        if key in cols_lower:
            return cols_lower[key]
    return None


def normalize_single_file(csv_path: Path, dayfirst: bool = False, visual_fill: bool = False, use_business_days: bool = True):
    logger = setup_logger()
    try:
        df = pd.read_csv(csv_path, dtype=str)
    except Exception as e:
        logger.error("[%s] No se pudo leer: %s", csv_path.name, e)
        logger.debug(traceback.format_exc())
        return

    try:
        df = _flatten_columns_if_needed(df)

        # Detectar columnas posibles
        date_col = _find_col(df, ["date", "fecha", "Date"])
        open_col = _find_col(df, ["open", "Open", "open_price"])
        high_col = _find_col(df, ["high", "High"])
        low_col = _find_col(df, ["low", "Low"])
        close_col = _find_col(df, ["close", "Close", "adj close", "Adj Close"])
        volume_col = _find_col(df, ["volume", "Volume", "vol"])

        found = {
            "date": date_col,
            "open": open_col,
            "high": high_col,
            "low": low_col,
            "close": close_col,
            "volume": volume_col,
        }
        missing = [k for k, v in found.items() if v is None]
        if missing:
            logger.warning("[%s] Faltan columnas detectadas: %s. Archivo saltado.", csv_path.name, missing)
            return

        # Construir DataFrame estándar
        df2 = pd.DataFrame()
        df2["date"] = df[found["date"]]
        df2["open"] = df[found["open"]]
        df2["high"] = df[found["high"]]
        df2["low"] = df[found["low"]]
        df2["close"] = df[found["close"]]
        df2["volume"] = df[found["volume"]]

        initial_rows = len(df2)

        # Convertir tipos
        df2["date"] = pd.to_datetime(df2["date"], errors="coerce", dayfirst=dayfirst)
        for col in ["open", "high", "low", "close", "volume"]:
            df2[col] = pd.to_numeric(df2[col], errors="coerce")

        # Eliminar filas con datos críticos faltantes
        df2 = df2.dropna(subset=["date", "open", "high", "low", "close", "volume"])
        dropped_rows = initial_rows - len(df2)
        if df2.empty:
            logger.warning("[%s] No tiene filas válidas después de limpiar. Archivo saltado.", csv_path.name)
            return

        # Agregar ticker normalizado (reemplaza puntos por guion bajo)
        ticker_raw = csv_path.stem
        ticker = ticker_raw.replace(".", "_")
        df2["ticker"] = ticker

        # Ordenar por fecha ascendente
        df2 = df2.sort_values("date").reset_index(drop=True)

        # Detectar gaps usando calendario de mercado (business days) o calendario diario
        dates = pd.to_datetime(df2["date"]).dt.date
        if use_business_days:
            full_idx = pd.bdate_range(start=dates.min(), end=dates.max())
        else:
            full_idx = pd.date_range(start=dates.min(), end=dates.max(), freq="D")

        expected_dates = set(pd.to_datetime(full_idx).date)
        actual_dates = set(dates)
        missing_dates = sorted(expected_dates - actual_dates)
        gap_count = len(missing_dates)

        # Por defecto no imputar. Si --visual-fill se activa solo para visualización
        fill_method = "none"
        filled_for_visual_only = False
        if visual_fill and gap_count > 0:
            # Reindex sobre full_idx, forward-fill
            reindexed = pd.DataFrame(index=pd.to_datetime(full_idx).strftime("%Y-%m-%d"))
            df2 = df2.set_index(df2["date"].dt.strftime("%Y-%m-%d"))
            df2 = reindexed.join(df2, how="left")
            df2.reset_index(inplace=True)
            df2.rename(columns={"index": "date"}, inplace=True)
            df2["ticker"] = ticker
            df2[["open", "high", "low", "close", "volume"]] = df2[["open", "high", "low", "close", "volume"]].ffill()
            fill_method = "ffill"
            filled_for_visual_only = True

        # Normalizar formato de fecha
        df2["date"] = pd.to_datetime(df2["date"], errors="coerce").dt.strftime("%Y-%m-%d")

        # Guardar archivo normalizado (atomic write)
        out_name = f"{ticker}_normalized.csv"
        out_path = DATA_NORMALIZED_CSV_DIR / out_name
        tmp_path = out_path.with_suffix(".csv.tmp")
        try:
            df2[NORMAL_COLUMNS].to_csv(tmp_path, index=False)
            tmp_path.replace(out_path)
        except Exception as e:
            logger.error("[%s] No se pudo guardar %s: %s", ticker, out_path, e)
            logger.debug(traceback.format_exc())
            return

        # Metadata
        meta = {
            "ticker": ticker,
            "source_file": str(csv_path.as_posix()),
            "generated_at": datetime.now().astimezone().isoformat(),
            "initial_rows": initial_rows,
            "final_rows": len(df2),
            "dropped_rows_by_nan": dropped_rows,
            "gap_count": gap_count,
            "gap_dates": [d.isoformat() for d in missing_dates],
            "filled_for_visual_only": bool(filled_for_visual_only),
            "fill_method": fill_method,
            "md5": None,
        }
        try:
            meta["md5"] = file_md5(out_path)
        except Exception:
            meta["md5"] = None

        meta_path = DATA_NORMALIZED_META_DIR / f"{ticker}_normalized.meta.json"
        try:
            with open(meta_path, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("[%s] No se pudo guardar metadata %s: %s", ticker, meta_path, e)

        logger.info("[OK] %s -> %s (filas: %d, gaps: %d)", csv_path.name, out_path.name, len(df2), gap_count)

    except Exception as e:
        logger.error("[%s] Error procesando archivo: %s", csv_path.name, e)
        logger.debug(traceback.format_exc())


def parse_args():
    p = argparse.ArgumentParser(prog="data_normalizer", description="Normaliza CSVs de data_raw/csv")
    p.add_argument("--dayfirst", action="store_true", help="Interpretar fechas como DD/MM/YYYY")
    p.add_argument("--visual-fill", action="store_true", help="Forward-fill gaps solo para visualización")
    p.add_argument("--no-business-days", action="store_true", help="Usar calendario diario en vez de días hábiles")
    p.add_argument("--limit", type=int, default=0, help="Limitar número de archivos procesados (0 = todos)")
    return p.parse_args()


def main():
    ensure_dirs()
    setup_logger()
    args = parse_args()

    use_business_days = not args.no_business_days
    csv_files = sorted(DATA_RAW_CSV_DIR.glob("*.csv"))
    if not csv_files:
        print("No hay CSV en data_raw/csv. Ejecutá primero data_downloader.")
        return

    if args.limit and args.limit > 0:
        csv_files = csv_files[: args.limit]

    logger = setup_logger()
    logger.info("Normalizando %d archivos (use_business_days=%s visual_fill=%s)", len(csv_files), use_business_days, args.visual_fill)

    for csv_path in csv_files:
        logger.info("Normalizando %s...", csv_path.name)
        normalize_single_file(csv_path, dayfirst=args.dayfirst, visual_fill=args.visual_fill, use_business_days=use_business_days)

    logger.info("Normalización completa.")


if __name__ == "__main__":
    main()