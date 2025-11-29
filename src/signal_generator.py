#!/usr/bin/env python3
from pathlib import Path
import pandas as pd
import logging
import json
import hashlib
import tempfile
from datetime import datetime
import argparse
import os
from typing import List, Tuple

# Rutas por defecto
BASE_DIR = Path.cwd()
DATA_INDICATORS_DIR = BASE_DIR / "data_indicators"
DATA_SIGNALS_DIR = BASE_DIR / "data_signals"
META_DIR = DATA_SIGNALS_DIR / "meta"

BOARD_FILE = DATA_SIGNALS_DIR / "board_general.csv"
BOARD_META_FILE = META_DIR / "board_general.meta.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("signal_generator")

REQUIRED_COLS = {
    "date",
    "ticker",
    "ema50",
    "T_hma16",
    "T_ema12_26",
    "T_ema10_50_100",
    "vma20_cat",
    "candle_signal",
    "candle_pattern",
}


def ensure_output_dir(data_signals_dir: Path = DATA_SIGNALS_DIR, meta_dir: Path = META_DIR):
    data_signals_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)


def infer_mercado(ticker: str) -> str:
    t = str(ticker).upper() if pd.notna(ticker) else ""
    if t.endswith(".BA") or t.endswith("_BA") or t.endswith("-BA"):
        return "Local"
    return "ADR"


def label_first_second_occurrence(series: pd.Series) -> pd.Series:
    result = []
    compra_count = 0
    venta_count = 0
    last_signal_type = None

    for val in series:
        if pd.isna(val) or str(val).strip() == "":
            result.append("")
            last_signal_type = None
            compra_count = venta_count = 0
            continue

        val_str = str(val).strip().lower()

        if val_str.startswith("compra tempr") or val_str.startswith("compra conf"):
            result.append(str(val).strip())
            last_signal_type = "Compra"
            compra_count = max(compra_count, 1)
            venta_count = 0
            continue

        if val_str.startswith("venta tempr") or val_str.startswith("venta conf"):
            result.append(str(val).strip())
            last_signal_type = "Venta"
            venta_count = max(venta_count, 1)
            compra_count = 0
            continue

        if "compra" in val_str:
            if last_signal_type != "Compra":
                compra_count = 0
            compra_count += 1
            result.append("Compra Temprana" if compra_count == 1 else "Compra Confirmada")
            last_signal_type = "Compra"
            venta_count = 0
            continue

        if "venta" in val_str:
            if last_signal_type != "Venta":
                venta_count = 0
            venta_count += 1
            result.append("Venta Temprana" if venta_count == 1 else "Venta Confirmada")
            last_signal_type = "Venta"
            compra_count = 0
            continue

        result.append(str(val).strip())
        last_signal_type = None
        compra_count = venta_count = 0

    return pd.Series(result, index=series.index)


def _list_candidate_files(indicators_dir: Path) -> List[Path]:
    """
    Busca recursivamente *_indicators.csv. Si no encuentra, busca todos los .csv
    en la carpeta y subcarpetas y los filtrará por columnas requeridas.
    """
    if not indicators_dir.exists():
        logger.warning("La carpeta %s no existe", indicators_dir)
        return []

    # Buscar recursivamente *_indicators.csv
    primary = list(sorted(indicators_dir.rglob("*_indicators.csv")))
    if primary:
        logger.info("Encontrados %d archivos con patrón '*_indicators.csv' (recursivo)", len(primary))
        return primary

    # Fallback: todos los CSV recursivos
    allcsv = list(sorted(indicators_dir.rglob("*.csv")))
    logger.info("No se encontraron '*_indicators.csv'. Se encontraron %d archivos .csv (recursivo)", len(allcsv))
    return allcsv


def _csv_has_required_columns(path: Path) -> bool:
    try:
        df_head = pd.read_csv(path, nrows=0)
        cols = set(df_head.columns.astype(str))
        return REQUIRED_COLS.issubset(cols)
    except Exception:
        return False


def process_ticker_board(ind_file: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(ind_file, header=0, dtype=str)
    except Exception as e:
        logger.warning("No se puede leer %s: %s", ind_file.name, str(e))
        return pd.DataFrame()

    if "date" in df.columns:
        df = df[df["date"].astype(str).str.lower() != "date"]
    else:
        logger.warning("%s no contiene columna 'date'. Se omite.", ind_file.name)
        return pd.DataFrame()

    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.strip().str.upper() \
            .str.replace(r"\.BA$", "_BA", regex=True) \
            .str.replace(r"-BA$", "_BA", regex=True)
    else:
        inferred = ind_file.stem.replace("_indicators", "").upper()
        df["ticker"] = inferred

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        logger.warning("%s falta columnas requeridas: %s. Se omite.", ind_file.name, missing)
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date").reset_index(drop=True)

    df["ema50"] = pd.to_numeric(df["ema50"], errors="coerce")
    df = df[~df["ema50"].isna()].copy()
    if df.empty:
        return pd.DataFrame()

    df["mercado"] = df["ticker"].astype(str).apply(infer_mercado)

    df["hma16_ui"] = label_first_second_occurrence(df["T_hma16"].fillna("").astype(str))
    df["ema_12_26_ui"] = label_first_second_occurrence(df["T_ema12_26"].fillna("").astype(str))
    df["ema_10_50_100_ui"] = label_first_second_occurrence(df["T_ema10_50_100"].fillna("").astype(str))

    df["vma20_ui"] = df["vma20_cat"].fillna("").astype(str)
    df["candle_signal"] = df["candle_signal"].fillna("").astype(str)
    df["candle_pattern"] = df["candle_pattern"].fillna("").astype(str)

    out_cols = {
        "date": "date",
        "ticker": "ticker",
        "mercado": "mercado",
        "ema_12_26_ui": "ema_12_26",
        "ema_10_50_100_ui": "ema_10_50_100",
        "hma16_ui": "hma16",
        "vma20_ui": "vma20",
        "candle_signal": "candle_signal",
        "candle_pattern": "candle_pattern",
    }

    df_out = df[list(out_cols.keys())].rename(columns=out_cols)
    return df_out


def build_board_general(indicators_dir: Path) -> Tuple[pd.DataFrame, List[str], List[str]]:
    candidates = _list_candidate_files(indicators_dir)
    if not candidates:
        logger.warning("No se encontraron archivos para procesar en %s", indicators_dir)
        return pd.DataFrame(), [], []

    # Filtrar candidatos por columnas requeridas cuando sea necesario
    candidate_filtered = []
    for p in candidates:
        if p.name.lower().endswith("_indicators.csv"):
            candidate_filtered.append(p)
            continue
        if _csv_has_required_columns(p):
            candidate_filtered.append(p)
        else:
            logger.debug("Archivo %s no tiene columnas requeridas, se ignora", p.name)

    if not candidate_filtered:
        logger.warning("No se encontraron archivos CSV con las columnas requeridas en %s", indicators_dir)
        return pd.DataFrame(), [], []

    logger.info("Archivos a procesar: %s", [p.name for p in candidate_filtered])

    all_rows = []
    included = []
    omitted = []

    for ind_file in candidate_filtered:
        ticker_name = ind_file.stem.replace("_indicators", "")
        logger.info("Procesando %s", ticker_name)
        try:
            df_ticker = process_ticker_board(ind_file)
        except Exception as e:
            logger.warning("Error procesando %s: %s. Se omite.", ind_file.name, str(e))
            omitted.append(ticker_name)
            continue

        if df_ticker.empty:
            logger.info("  %s: sin filas válidas. Se omite.", ticker_name)
            omitted.append(ticker_name)
            continue

        all_rows.append(df_ticker)
        included.append(ticker_name)
        logger.info("  ✓ %s: %d filas agregadas", ticker_name, len(df_ticker))

    if not all_rows:
        logger.warning("No se generó información para ningún ticker")
        return pd.DataFrame(), included, omitted

    board = pd.concat(all_rows, ignore_index=True)
    board = board.sort_values(["date", "ticker"]).reset_index(drop=True)
    return board, included, omitted


def _atomic_write_text(path: Path, text: str, encoding="utf-8"):
    """
    Escribe de forma atómica creando el archivo temporal en la misma carpeta
    que el destino. Evita errores al mover entre distintas unidades.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # crear temp file en la misma carpeta que el destino
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding=encoding, prefix=path.name, suffix=".tmp") as tf:
        tf.write(text)
        tmp_path = Path(tf.name)
    try:
        tmp_path.replace(path)
    except Exception:
        # intentar limpiar si algo falla
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise


def _compute_md5_text(text: str) -> str:
    md5 = hashlib.md5()
    md5.update(text.encode("utf-8"))
    return md5.hexdigest()


def parse_args():
    parser = argparse.ArgumentParser(description="Generar Hoja 1 (board_general.csv) desde data_indicators")
    parser.add_argument("--data-indicators", type=str, default=os.getenv("DATA_INDICATORS_DIR"),
                        help="Ruta a data_indicators. Si no se pasa usa ./data_indicators")
    parser.add_argument("--data-signals", type=str, default=os.getenv("DATA_SIGNALS_DIR"),
                        help="Ruta a data_signals. Si no se pasa usa ./data_signals")
    return parser.parse_args()


def main():
    args = parse_args()

    # declarar global al inicio de la función antes de reasignar
    global DATA_INDICATORS_DIR, DATA_SIGNALS_DIR, META_DIR, BOARD_FILE, BOARD_META_FILE

    indicators_dir = Path(args.data_indicators) if args.data_indicators else DATA_INDICATORS_DIR
    signals_dir = Path(args.data_signals) if args.data_signals else DATA_SIGNALS_DIR

    DATA_INDICATORS_DIR = indicators_dir
    DATA_SIGNALS_DIR = signals_dir
    META_DIR = DATA_SIGNALS_DIR / "meta"
    BOARD_FILE = DATA_SIGNALS_DIR / "board_general.csv"
    BOARD_META_FILE = META_DIR / "board_general.meta.json"

    ensure_output_dir(DATA_SIGNALS_DIR, META_DIR)

    logger.info("MÓDULO 4 – Generación de Hoja 1 (board_general.csv)")
    logger.info("Entrada:  %s", DATA_INDICATORS_DIR)
    logger.info("Salida:   %s", BOARD_FILE)

    if DATA_INDICATORS_DIR.exists():
        files = sorted([str(p.relative_to(DATA_INDICATORS_DIR)) for p in DATA_INDICATORS_DIR.rglob("*") if p.is_file()])
        logger.info("Contenido recursivo de %s: %s", DATA_INDICATORS_DIR, files)
    else:
        logger.warning("Carpeta de indicadores no existe: %s", DATA_INDICATORS_DIR)

    board, included, omitted = build_board_general(DATA_INDICATORS_DIR)

    if board.empty:
        logger.warning("No se generó board_general.csv por falta de datos")
        logger.info("Tickers incluidos: %s", included)
        logger.info("Tickers omitidos: %s", omitted)
        return

    csv_text = board.to_csv(index=False)
    _atomic_write_text(BOARD_FILE, csv_text)
    logger.info("✓ board_general.csv generado con %d filas. Ubicación: %s", len(board), BOARD_FILE)

    meta = {
        "rows_out": len(board),
        "tickers_incluidos": included,
        "tickers_omitidos": omitted,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "md5": _compute_md5_text(csv_text),
    }
    _atomic_write_text(BOARD_META_FILE, json.dumps(meta, ensure_ascii=False, indent=2))
    logger.info("✓ metadata escrita en %s", BOARD_META_FILE)


if __name__ == "__main__":
    main()