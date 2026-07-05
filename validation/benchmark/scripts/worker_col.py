"""Worker aislado: mide una granularidad. Subproceso -> PeakWorkingSetSize propio.
Args: <repo_root> <rows> <measured_ns_json> <tmpdir>
Genera OHLCV sintetico, corre el computo identico a indicator_engine (funciones
puras importadas, IO a temp), mide seg/serie (mediana) y wall-clock agregado por n.
NO toca src/ ni datos de produccion."""
import sys, json, time, statistics, ctypes, shutil
from ctypes import wintypes
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]); R = int(sys.argv[2])
measured_ns = json.loads(sys.argv[3]); tmpdir = Path(sys.argv[4])
sys.path.insert(0, str(ROOT))
# funciones puras del engine REAL (import read-only; no corre main ni escribe prod)
from src.analysis.indicator_engine import calculate_hma, calculate_vma20_ratio

class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

def peak_rss_mb():
    c = PMC(); c.cb = ctypes.sizeof(c)
    ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), ctypes.sizeof(c))
    return c.PeakWorkingSetSize / 1e6

def synth(n, seed):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    op = close * (1 + rng.normal(0, 0.003, n))
    vol = rng.integers(int(1e5), int(1e7), n).astype(float)
    dates = pd.date_range("2015-01-01", periods=n, freq="min").strftime("%Y-%m-%d")
    return pd.DataFrame({"date": dates, "open": op, "high": high, "low": low,
                         "close": close, "volume": vol, "ticker": "SYN"})

OUT = tmpdir / "_out.csv"  # se sobreescribe siempre -> disco acotado, costo de escritura real
def process_one(fin):
    df = pd.read_csv(fin)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date").reset_index(drop=True)
    df["hma16"] = calculate_hma(df["close"], span=16)
    for span in (10, 50, 100):
        df[f"sma{span}"] = df["close"].rolling(span).mean().round(2)
    for span in (12, 26):
        ema = df["close"].ewm(span=span, adjust=False).mean()
        ema.iloc[:max(0, span - 1)] = np.nan
        df[f"ema{span}"] = ema.round(2)
    df["vma20_ratio"] = calculate_vma20_ratio(df)
    cols = ["date", "open", "high", "low", "close", "volume", "ticker",
            "hma16", "sma10", "sma50", "sma100", "ema12", "ema26", "vma20_ratio"]
    df[[c for c in cols if c in df.columns]].to_csv(OUT, index=False)

in_dir = tmpdir / "in"
if in_dir.exists(): shutil.rmtree(in_dir)
in_dir.mkdir(parents=True, exist_ok=True)
max_n = max(measured_ns)
files = []
for i in range(max_n):
    f = in_dir / f"SYN{i:04d}.csv"
    synth(R, 1000 + i).to_csv(f, index=False)
    files.append(f)

# seg/serie: mediana sobre unas pocas series (incluye read+compute+write)
ks = 3 if R >= 500000 else 5
ks = min(ks, max_n)
per = []
for i in range(ks):
    t0 = time.perf_counter(); process_one(files[i]); per.append(time.perf_counter() - t0)
per_series = statistics.median(per)

# wall-clock agregado end-to-end por cada n medido
agg = {}
for n in sorted(measured_ns):
    t0 = time.perf_counter()
    for i in range(n):
        process_one(files[i])
    agg[str(n)] = time.perf_counter() - t0

peak = peak_rss_mb()
shutil.rmtree(in_dir, ignore_errors=True)
OUT.unlink(missing_ok=True)
print(json.dumps({"rows": R, "per_series": per_series, "peak_rss_mb": peak, "agg": agg}))
