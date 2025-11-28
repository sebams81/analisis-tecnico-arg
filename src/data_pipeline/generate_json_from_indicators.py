#!/usr/bin/env python3
"""
generate_json_from_indicators.py
Lee CSV *_indicators.csv y genera un JSON por ticker en data_public/json/.
Comportamiento:
 - entrada: carpeta con CSV (por defecto data_indicators/)
 - salida: data_public/json/{TICKER}.json
 - criterio de serie: elimina filas iniciales hasta la primera fila con EMA50 no nula
 - idempotencia: usa manifest (manifest.json) para evitar regenerar si no hay cambios
Requisitos: pandas
"""

import pandas as pd
import json
import hashlib
from pathlib import Path
from datetime import datetime

INPUT_DIR = Path("data_indicators")
OUTPUT_DIR = Path("data_public/json")
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"

PALETTE_DEFAULT = [
    "#FF0000","#00CC66","#FFCC00","#0055FF","#AA00FF","#8B4513",
    "#00AAAA","#FF66CC","#336600","#663399","#FF8800","#006600"
]
HMA_COLORS = {"up": "#00AA00", "down": "#CC0000"}
EMA_DEFAULTS = {"EMA12": "#FFFF00", "EMA26": "#0000FF", "EMA10": "#FF7700", "EMA50": "#7A00FF", "EMA100": "#8B4513"}

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def file_hash(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def load_manifest():
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}

def save_manifest(manifest):
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

def compute_hma_trend(series_values):
    # recibe pd.Series con valores HMA16 ordenados por fecha
    prev = None
    trends = []
    for v in series_values:
        if pd.isna(v):
            trends.append(None)
        else:
            if prev is None:
                trends.append(None)
            else:
                trends.append("up" if v > prev else "down")
            prev = v
    return trends

def process_csv(path: Path):
    try:
        df = pd.read_csv(path, parse_dates=["date"])
    except Exception as e:
        print(f"ERROR leyendo {path}: {e}")
        return None

    ticker = path.stem  # assuming file is TICKER_indicators or just TICKER
    # normalize column names to lower-case keys for JSON
    # criterio: eliminar filas iniciales hasta que EMA50 sea no nula
    if "EMA50" not in df.columns and "ema50" not in [c.lower() for c in df.columns]:
        print(f"WARNING {path.name} no contiene EMA50, se salta")
        return None

    # aseguramos nombres estándar
    cols = {c: c for c in df.columns}
    # use case-insensitive lookup
    def col(name):
        for c in df.columns:
            if c.lower() == name.lower():
                return c
        return None

    ema50_col = col("EMA50")
    hma_col = col("HMA16")
    # drop leading rows until ema50 not null
    first_valid_idx = df[ema50_col].first_valid_index()
    if first_valid_idx is None:
        print(f"WARNING {path.name} EMA50 nunca válida, se salta")
        return None
    df = df.loc[first_valid_idx:].reset_index(drop=True)

    # compute HMA trend
    if hma_col:
        trends = compute_hma_trend(df[hma_col].tolist())
    else:
        trends = [None] * len(df)

    series = []
    for i, row in df.iterrows():
        item = {
            "date": pd.Timestamp(row[col("date")]).strftime("%Y-%m-%d"),
            "open": None if pd.isna(row.get(col("open"), None)) else float(row.get(col("open"))),
            "high": None if pd.isna(row.get(col("high"), None)) else float(row.get(col("high"))),
            "low": None if pd.isna(row.get(col("low"), None)) else float(row.get(col("low"))),
            "close": None if pd.isna(row.get(col("close"), None)) else float(row.get(col("close"))),
            "volume": None if pd.isna(row.get(col("volume"), None)) else float(row.get(col("volume"))),
            "HMA16": None if hma_col is None or pd.isna(row.get(hma_col)) else float(row.get(hma_col)),
            "HMA16_trend": trends[i],
        }
        # add EMAs if present
        for e in ["EMA10","EMA12","EMA26","EMA50","EMA100"]:
            c = col(e)
            if c:
                val = row.get(c)
                item[e] = None if pd.isna(val) else float(val)
        # add VMA20 and candle signals if present
        vma = col("VMA20")
        if vma:
            v = row.get(vma)
            item["VMA20"] = None if pd.isna(v) else float(v)
        cs = col("candle_signal")
        if cs:
            item["candle_signal"] = None if pd.isna(row.get(cs)) else str(row.get(cs))
        cp = col("candle_pattern")
        if cp:
            item["candle_pattern"] = None if pd.isna(row.get(cp)) else str(row.get(cp))

        series.append(item)

    json_obj = {
        "ticker": ticker,
        "market": None,
        "timezone": "America/Argentina/Buenos_Aires",
        "source": str(path),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "defaults": {
            "palette": PALETTE_DEFAULT,
            "hma_colors": HMA_COLORS,
            "ema_defaults": EMA_DEFAULTS
        },
        "series": series,
        "ui_helpers": {
            "available_views": ["candles", "line"],
            "ema_groups": {
                "pair_12_26": ["EMA12", "EMA26"],
                "triple_10_50_100": ["EMA10", "EMA50", "EMA100"]
            }
        }
    }
    return json_obj

def main():
    manifest = load_manifest()
    updated = False
    for csv_path in sorted(INPUT_DIR.glob("*_indicators.csv")):
        h = file_hash(csv_path)
        key = csv_path.name
        if manifest.get(key, {}).get("hash") == h:
            # no cambió
            continue
        print(f"Procesando {csv_path.name}")
        j = process_csv(csv_path)
        if j is None:
            continue
        out_file = OUTPUT_DIR / (csv_path.stem.split("_indicators")[0] + ".json")
        out_file.write_text(json.dumps(j, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest[key] = {"hash": h, "json": str(out_file), "updated_at": datetime.utcnow().isoformat()}
        updated = True

    if updated:
        save_manifest(manifest)
        print("Generación completada, manifest actualizado")
    else:
        print("No hubo cambios, nada que generar")

if __name__ == "__main__":
    main()