#!/usr/bin/env python3
import glob, pandas as pd, numpy as np
from pathlib import Path

def norm_sig(v):
    if pd.isna(v): return 0
    try:
        if isinstance(v, (int, float, np.integer, np.floating)):
            return 1 if v>0 else (-1 if v<0 else 0)
        s=str(v).strip().lower()
        if s in ("1","buy","compra","long","+","true"): return 1
        if s in ("-1","sell","venta","short","-","false"): return -1
    except: pass
    return 0

p = Path("data_indicators")
files = sorted(glob.glob(str(p/"*.csv")))
print("Archivos indicadores:", len(files))
for f in files:
    name = Path(f).stem
    try:
        df = pd.read_csv(f, parse_dates=["date"])
    except Exception as e:
        print(name, "read_error", e)
        continue
    # aseguramos columnas
    for c in ("T_hma16","T_ema12_26","T_ema10_50_100","VMA20","open","close"):
        if c not in df.columns:
            print(name, "MISSING", c)
    # combined ema
    def comb(r):
        return (norm_sig(r.get("T_ema12_26",0)) + norm_sig(r.get("T_ema10_50_100",0)))
    df["T_emas_combined"] = df.apply(lambda r: (1 if comb(r)>0 else (-1 if comb(r)<0 else 0)), axis=1)
    cnt_h = (df["T_hma16"].apply(norm_sig) == 1).sum() if "T_hma16" in df.columns else 0
    cnt_e = (df["T_emas_combined"].apply(norm_sig) == 1).sum()
    cnt_v = (df["VMA20"].notna() & (df["VMA20"]>0)).sum() if "VMA20" in df.columns else 0
    print(f"{name}: HMA_buy={cnt_h} EMA_buy={cnt_e} VMA_nonnull={cnt_v} rows={len(df)}")
    # show up to 2 example rows with any buy signal
    examples = df[((df.get("T_hma16",0).apply if hasattr(df.get("T_hma16",0),'apply') else lambda x: x)(pd.Series(df.get("T_hma16",0))).apply(norm_sig)==1) | (df["T_emas_combined"].apply(norm_sig)==1)]
    if not examples.empty:
        print("  Ejemplo:", examples.head(1)[["date","open","close","T_hma16","T_ema12_26","T_ema10_50_100","VMA20"]].to_dict(orient="records")[0])