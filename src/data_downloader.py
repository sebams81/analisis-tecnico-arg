#!/usr/bin/env python3
"""
data_downloader.py

Descarga históricos desde yfinance y guarda:
- data_raw/csv/<TICKER>.csv
- data_raw/meta/<TICKER>.meta.json

Uso:
    python src/data_downloader.py [--hist-days N] [--tickers T1,T2] [--limit N] [--pause S] [--retries R]

Notas:
- Preserva el orden de PAIRS.
- Guarda metadata con md5, filas y primer/última fecha.
- No hace imputación de datos.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse
import time
import json
import hashlib
import logging
import sys
import traceback

import yfinance as yf
import pandas as pd

# Base del proyecto (dos niveles arriba de este archivo)
BASE_DIR = Path(__file__).resolve().parents[1]

# Rutas nuevas según estructura propuesta
DATA_RAW_CSV_DIR = BASE_DIR / "data_raw" / "csv"
DATA_RAW_META_DIR = BASE_DIR / "data_raw" / "meta"
LOG_DIR = BASE_DIR / "logs"

# Pares Local / ADR (orden preservado)
PAIRS = [
    ("PAMP.BA", "PAM"),
    ("GGAL.BA", "GGAL"),
    ("YPFD.BA", "YPF"),
    ("BMA.BA", "BMA"),
    ("CEPU.BA", "CEPU"),
    ("SUPV.BA", "SUPV"),
    ("BBAR.BA", "BBAR"),
    ("EDN.BA", "EDN"),
    ("TXAR.BA", "TX"),
    ("LOMA.BA", "LOMA"),
    ("TECO2.BA", "TEO"),
    ("TGSU2.BA", "TGS"),
]

# Lista de tickers preservando el orden local/ADR
TICKERS = [t for pair in PAIRS for t in pair]

# Columnas mínimas esperadas tras reset_index
REQUIRED_COLUMNS = {"Open", "High", "Low", "Close", "Volume"}

LOGGER = None


def ensure_dirs():
    DATA_RAW_CSV_DIR.mkdir(parents=True, exist_ok=True)
    DATA_RAW_META_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logger():
    global LOGGER
    if LOGGER:
        return LOGGER
    logger = logging.getLogger("data_downloader")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(LOG_DIR / "data_downloader.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    LOGGER = logger
    return logger


def file_md5(path: Path, chunk_size: int = 8192) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def save_raw_metadata(ticker: str, csv_path: Path, rows: int, first_date: str, last_date: str):
    meta = {
        "ticker": ticker,
        "csv": str(csv_path.as_posix()),
        "rows": rows,
        "first_date": first_date,
        "last_date": last_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        meta["md5"] = file_md5(csv_path)
    except Exception:
        meta["md5"] = None
    out_path = DATA_RAW_META_DIR / f"{csv_path.stem}.meta.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)


def _flatten_columns_if_needed(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c if isinstance(c, str) else str(c) for c in df.columns]
    return df


def download_history_for_ticker(ticker: str, hist_days: int, max_retries: int = 3, pause: float = 0.5) -> bool:
    logger = setup_logger()
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=hist_days)
    logger.info("[%s] Descargando desde %s hasta %s", ticker, start_date, end_date)

    attempt = 0
    last_exc = None
    while attempt < max_retries:
        attempt += 1
        try:
            data = yf.download(
                ticker,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                progress=False,
                auto_adjust=True,
                threads=False,
            )
            if data is None or data.empty:
                logger.warning("[%s] yfinance devolvió DataFrame vacío (intento %d/%d)", ticker, attempt, max_retries)
                last_exc = None
                time.sleep(pause)
                continue

            # Aplanar MultiIndex y normalizar nombres de columnas
            data = _flatten_columns_if_needed(data)

            # Asegurar índice como columna de fecha
            data = data.reset_index()

            cols = {str(c).strip() for c in data.columns}
            if not REQUIRED_COLUMNS.issubset(cols):
                logger.warning(
                    "[%s] Faltan columnas requeridas: esperado %s pero obtuvo %s. Archivo no guardado.",
                    ticker, sorted(REQUIRED_COLUMNS), sorted(cols)
                )
                return False

            # Guardar en archivo temporal y renombrar atómico
            safe_name = ticker.replace(".", "_")
            output_file = DATA_RAW_CSV_DIR / f"{safe_name}.csv"
            tmp_file = DATA_RAW_CSV_DIR / f"{safe_name}.csv.tmp"
            data.to_csv(tmp_file, index=False)
            tmp_file.replace(output_file)

            # Metadata: primero y último date si existen
            first_date = ""
            last_date = ""
            try:
                if "Date" in data.columns:
                    first_date = str(pd.to_datetime(data["Date"]).min().date())
                    last_date = str(pd.to_datetime(data["Date"]).max().date())
                elif data.index.name and "date" in data.index.name.lower():
                    idx = pd.to_datetime(data.index)
                    first_date = str(idx.min().date())
                    last_date = str(idx.max().date())
            except Exception:
                first_date = ""
                last_date = ""

            # Guardar metadata simple
            save_raw_metadata(ticker, output_file, len(data), first_date, last_date)

            logger.info("[%s] Datos guardados en: %s (filas: %d)", ticker, output_file, len(data))
            return True

        except Exception as e:
            last_exc = e
            logger.warning("[%s] Error en descarga intento %d/%d: %s", ticker, attempt, max_retries, str(e))
            logger.debug(traceback.format_exc())
            backoff = min(5, 0.5 * (2 ** (attempt - 1)))
            time.sleep(backoff + pause)

    logger.error("[%s] Falló la descarga después de %d intentos. Última excepción: %s", ticker, max_retries, last_exc)
    return False


def parse_args():
    p = argparse.ArgumentParser(prog="data_downloader", description="Descarga históricos desde yfinance")
    p.add_argument("--hist-days", type=int, default=365, help="Días de histórico a descargar")
    p.add_argument("--tickers", type=str, help="Lista de tickers separados por comas. Si se omite usa PAIRS")
    p.add_argument("--limit", type=int, default=0, help="Limitar número de tickers procesados (0 = todos)")
    p.add_argument("--pause", type=float, default=0.35, help="Segundos a esperar entre descargas")
    p.add_argument("--retries", type=int, default=3, help="Reintentos por ticker")
    return p.parse_args()


def main():
    ensure_dirs()
    logger = setup_logger()
    args = parse_args()

    hist_days = args.hist_days
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = TICKERS.copy()

    if args.limit and args.limit > 0:
        tickers = tickers[: args.limit]

    logger.info("Carpeta de raw CSV: %s", DATA_RAW_CSV_DIR)
    logger.info("Carpeta de raw meta: %s", DATA_RAW_META_DIR)
    logger.info("Tickers a procesar (%d): %s", len(tickers), ", ".join(tickers))
    logger.info("Hist_days: %d", hist_days)

    processed = 0
    for ticker in tickers:
        download_history_for_ticker(ticker, hist_days, max_retries=args.retries, pause=args.pause)
        processed += 1
        time.sleep(args.pause)

    logger.info("Descarga finalizada. Procesados: %d", processed)


if __name__ == "__main__":
    main()