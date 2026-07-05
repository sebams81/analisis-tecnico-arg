"""Memoria por granularidad via tracemalloc: pico NETO de allocaciones Python
durante el computo de UNA serie. Independiente de n_tickers (la etapa procesa
y libera una serie por vez). No mide tiempo. Aislado de produccion (funciones
puras importadas, datos sinteticos en memoria)."""
import tracemalloc, sys, csv
from pathlib import Path
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]        # raiz del repo
sys.path.insert(0, str(REPO_ROOT))
from src.analysis.indicator_engine import calculate_hma, calculate_vma20_ratio

SB = Path(__file__).resolve().parent.parent            # validation/benchmark

def synth(n, seed=1000):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    op = close * (1 + rng.normal(0, 0.003, n))
    vol = rng.integers(int(1e5), int(1e7), n).astype(float)
    return pd.DataFrame({"open": op, "high": high, "low": low, "close": close, "volume": vol})

def compute(df):
    df = df.copy()
    df["hma16"] = calculate_hma(df["close"], span=16)
    for s in (10, 50, 100):
        df[f"sma{s}"] = df["close"].rolling(s).mean().round(2)
    for s in (12, 26):
        ema = df["close"].ewm(span=s, adjust=False).mean()
        ema.iloc[:max(0, s - 1)] = np.nan
        df[f"ema{s}"] = ema.round(2)
    df["vma20_ratio"] = calculate_vma20_ratio(df)
    return df

GRAN = [("diario", 1400), ("intradia_60m", 9000), ("intradia_1m", 550000)]
rows = []
for name, n in GRAN:
    d = synth(n)
    tracemalloc.start()
    _ = compute(d)                     # una serie: pico neto de allocaciones
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    del _, d
    mb = round(peak / 1e6, 1)
    rows.append((name, n, mb))
    print(f"{name:>14} rows={n:>7} pico_neto_MB={mb}")

out = SB / "memory_benchmark.csv"
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["granularidad", "filas_por_serie", "pico_neto_MB"])
    for r in rows:
        w.writerow(r)
print(f"CSV: {out}")
