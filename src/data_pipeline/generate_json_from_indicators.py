#!/usr/bin/env python3
import os
import glob
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA_INDICATORS_DIR = Path("data_indicators")
OUTPUT_JSON_DIR = Path("data_public/json")
FUNDAMENTALS_CSV = Path("data_raw/events_fundamentales_ar.csv")
MANIFEST_PATH = OUTPUT_JSON_DIR / "manifest.json"

def file_hash(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def load_fundamentals(path):
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str).fillna("")
    cols_lower = {c.lower(): c for c in df.columns}
    def get_col(*opts):
        for o in opts:
            if o and o.lower() in cols_lower:
                return cols_lower[o.lower()]
        return None
    fecha_col = get_col("Fecha", "Date")
    tickers_col = get_col("Ticker(s)", "Tickers", "ticker")
    evento_col = get_col("Evento", "Event")
    impacto_col = get_col("Impacto", "Impact")
    fuente_col = get_col("Fuente", "Source")
    if not (fecha_col and tickers_col and evento_col):
        return {}
    mapping = {}
    for _, r in df.iterrows():
        fecha = str(r.get(fecha_col, "")).strip()
        tickers = str(r.get(tickers_col, "")).strip()
        evento = str(r.get(evento_col, "")).strip()
        impacto = str(r.get(impacto_col, "")).strip() if impacto_col else ""
        fuente = str(r.get(fuente_col, "")).strip() if fuente_col else ""
        if not tickers:
            continue
        for t in [x.strip() for x in tickers.split(",") if x.strip()]:
            entry = {"date": fecha, "event": evento, "impact": impacto, "source": fuente}
            mapping.setdefault(t, []).append(entry)
    for t in mapping:
        try:
            mapping[t].sort(key=lambda e: e["date"])
        except:
            pass
    return mapping

def _as_number_or_none(v):
    if v is None:
        return None
    try:
        return float(v)
    except:
        try:
            s = str(v).strip()
            return float(s) if s != "" else None
        except:
            return None

def _as_str_or_none(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s != "" else None

def build_series_from_df(df):
    series = []
    for _, r in df.iterrows():
        item = {}
        date_col = next((c for c in r.index if c.lower() in ("date", "fecha")), None)
        item["date"] = str(r[date_col]) if date_col else ""
        for colname in r.index:
            lname = colname.strip()
            lcase = lname.lower()
            val = r[colname]
            if lcase in ("open", "open_price"):
                item["open"] = _as_number_or_none(val)
            elif lcase == "high":
                item["high"] = _as_number_or_none(val)
            elif lcase == "low":
                item["low"] = _as_number_or_none(val)
            elif lcase in ("close", "close_price"):
                item["close"] = _as_number_or_none(val)
            elif lcase in ("volume", "vol"):
                item["volume"] = _as_number_or_none(val)
            elif lcase == "hma16":
                item["HMA16"] = _as_number_or_none(val)
            elif lcase in ("hma16_trend", "hma16 trend"):
                item["HMA16_trend"] = _as_str_or_none(val)
            elif lcase.startswith("ema"):
                item[lname.upper()] = _as_number_or_none(val)
            elif lcase == "vma20":
                item["VMA20"] = _as_number_or_none(val)
            elif lcase == "candle_signal":
                item["candle_signal"] = _as_str_or_none(val)
            elif lcase == "candle_pattern":
                item["candle_pattern"] = _as_str_or_none(val)
        series.append(item)
    return series

def main():
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    fundamentals = load_fundamentals(FUNDAMENTALS_CSV)
    fundamentals_hash = file_hash(FUNDAMENTALS_CSV) if FUNDAMENTALS_CSV.exists() else None
    manifest = {}
    indicator_files = sorted(glob.glob(str(DATA_INDICATORS_DIR / "*_indicators.csv")) + glob.glob(str(DATA_INDICATORS_DIR / "*.csv")))

    for file_path in indicator_files:
        try:
            csv_path = Path(file_path)
            df = pd.read_csv(csv_path, dtype=str).fillna("")
            name = csv_path.name
            if name.endswith("_indicators.csv"):
                ticker = name[: -len("_indicators.csv")]
            elif name.endswith(".csv"):
                ticker = name[:-4]
            else:
                ticker = name
            series = build_series_from_df(df)
            json_obj = {
                "ticker": ticker,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "series": series,
                "defaults": {
                    "hma_color_up": "#16a34a",
                    "hma_color_down": "#ef4444",
                    "ema_colors": {"EMA10": "#f59e0b", "EMA50": "#0ea5e9", "EMA100": "#8b5cf6"}
                }
            }
            json_obj["fundamentals"] = fundamentals.get(ticker, [])
            out_path = OUTPUT_JSON_DIR / f"{ticker}.json"
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(json_obj, fh, ensure_ascii=False, indent=2)
            manifest[csv_path.name] = {
                "hash": file_hash(csv_path),
                "json": str(out_path.as_posix()),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            print(f"[OK] {csv_path.name} -> {out_path.name}")
        except Exception as e:
            print(f"[ERROR] procesando {file_path}: {e}")

    if fundamentals_hash:
        manifest["fundamentals_csv_hash"] = fundamentals_hash

    with open(MANIFEST_PATH, "w", encoding="utf-8") as mfh:
        json.dump(manifest, mfh, ensure_ascii=False, indent=2)

    print(f"Manifest escrito en {MANIFEST_PATH} con {len(manifest)} entradas.")

if __name__ == "__main__":
    main()