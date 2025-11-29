#!/usr/bin/env python3
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

DATA_INDICATORS_DIR = Path("data_indicators")
OUTPUT_JSON_DIR = Path("data_public/json")
FUNDAMENTALS_JSON = Path("data_fundamentals/fundamentals.json")
MANIFEST_PATH = OUTPUT_JSON_DIR / "manifest.json"


def file_hash(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_ticker(t):
    t = str(t).strip().upper()
    if t == "" or t.lower() == "nan":
        return ""
    t = t.replace(".", "_")
    if t.endswith("-BA"):
        t = t[:-3] + "_BA"
    return t


def load_fundamentals_json(json_path: Path):
    if not json_path.exists():
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}

    # si ya es diccionario {'TICKER': [events...]} normalizar claves
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            nk = normalize_ticker(k)
            if not nk:
                continue
            out[nk] = []
            if not isinstance(v, list):
                continue
            for entry in v:
                out[nk].append({
                    "date": entry.get("date", ""),
                    "event": entry.get("event", entry.get("Evento", "")),
                    "impact": entry.get("impact", entry.get("Impacto", "")),
                    "source": entry.get("source", entry.get("Fuente", "")),
                    "original_ticker": entry.get("ticker", k)
                })
        return out

    # si es lista intentar mapear por campo ticker
    mapping = {}
    if isinstance(data, list):
        for e in data:
            t_raw = e.get("ticker") or e.get("Ticker") or ""
            key = normalize_ticker(t_raw)
            if not key:
                continue
            mapping.setdefault(key, []).append({
                "date": e.get("date", ""),
                "event": e.get("event", e.get("Evento", "")),
                "impact": e.get("impact", e.get("Impacto", "")),
                "source": e.get("source", e.get("Fuente", "")),
                "original_ticker": t_raw
            })
    for t in mapping:
        try:
            mapping[t].sort(key=lambda ev: ev.get("date") or "")
        except Exception:
            pass
    return mapping


def find_events_for_ticker(requested_ticker, mapping):
    t = normalize_ticker(requested_ticker)
    variants = [t]
    if t.endswith("_BA"):
        variants += [t.replace("_BA", ""), t.replace("_", ".")]
    else:
        variants += [t + "_BA", t.replace("_", ".")]
    for v in variants:
        if v in mapping and mapping[v]:
            return mapping[v], v
    return [], None


def _as_number_or_none(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        try:
            s = str(v).strip()
            return float(s) if s != "" else None
        except Exception:
            return None


def _as_str_or_none(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s != "" else None


def build_series_from_df(df: pd.DataFrame):
    series = []
    for _, r in df.iterrows():
        item = {}
        date_col = next((c for c in r.index if str(c).lower() in ("date", "fecha")), None)
        item["date"] = str(r[date_col]) if date_col else ""
        for colname in r.index:
            lname = str(colname).strip()
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
    fundamentals = load_fundamentals_json(FUNDAMENTALS_JSON)
    fundamentals_hash = file_hash(FUNDAMENTALS_JSON) if FUNDAMENTALS_JSON.exists() else None
    manifest = {}

    indicator_paths = sorted(DATA_INDICATORS_DIR.rglob("*_indicators.csv"))
    if not indicator_paths:
        indicator_paths = sorted(DATA_INDICATORS_DIR.rglob("*.csv"))

    for csv_path in indicator_paths:
        try:
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
                    "ema_colors": {"EMA10": "#f59e0b", "EMA50": "#0ea5e9", "EMA100": "#8b5cf6"},
                },
            }

            events, matched_as = find_events_for_ticker(ticker, fundamentals)
            json_obj["fundamentals"] = events
            json_obj["fundamentals_found_as"] = matched_as

            out_path = OUTPUT_JSON_DIR / f"{ticker}.json"
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(json_obj, fh, ensure_ascii=False, indent=2)

            manifest[csv_path.name] = {
                "hash": file_hash(csv_path),
                "json": str(out_path.as_posix()),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            print(f"[OK] {csv_path.name} -> {out_path.name}")
        except Exception as e:
            print(f"[ERROR] procesando {csv_path}: {e}")

    if fundamentals_hash:
        manifest["fundamentals_json_hash"] = fundamentals_hash

    with open(MANIFEST_PATH, "w", encoding="utf-8") as mfh:
        json.dump(manifest, mfh, ensure_ascii=False, indent=2)

    print(f"Manifest escrito en {MANIFEST_PATH} con {len(manifest)} entradas.")


if __name__ == "__main__":
    main()