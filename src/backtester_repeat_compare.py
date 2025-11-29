#!/usr/bin/env python3
import glob
from pathlib import Path
import pandas as pd
import numpy as np

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

def consecutive_counts(series):
    # serie de ints {1,0,-1} -> cuenta consecutiva por signo (reinicia cuando cambian)
    counts = [0]*len(series)
    prev = 0
    cnt = 0
    for i, v in enumerate(series):
        if v != 0 and v == prev:
            cnt += 1
        elif v != 0 and v != prev:
            cnt = 1
        else:
            cnt = 0
        counts[i] = cnt
        prev = v
    return counts

def run_backtest_variant(df, sig_col, entry_repeat=1, max_hold=30):
    # entry_repeat=1 -> first occurrence, =2 -> second consecutive occurrence, etc.
    trades=[]
    sig = df[sig_col].apply(norm_sig).astype(int).tolist()
    counts = consecutive_counts(sig)
    in_pos=False
    entry_price=None
    entry_vma=None
    entry_date=None
    hold=0
    for i in range(len(df)-1):
        cur_sig = sig[i]
        cur_count = counts[i]
        # enter if not in pos and current signal is buy and its consecutive count >= entry_repeat
        if not in_pos and cur_sig == 1 and cur_count >= entry_repeat:
            idx = i+1
            if idx >= len(df): continue
            row = df.iloc[idx]
            if pd.isna(row.get("open")) or pd.isna(row.get("date")): continue
            entry_price = row["open"]
            entry_date = row["date"]
            entry_vma = row.get("VMA20", np.nan)
            in_pos=True
            hold=0
            continue
        if in_pos:
            hold += 1
            next_sig = sig[i+1] if i+1 < len(sig) else 0
            # exit on explicit sell signal or max hold
            if next_sig == -1 or hold >= max_hold:
                exit_idx = i+1
                if exit_idx >= len(df): break
                exit_row = df.iloc[exit_idx]
                if pd.isna(exit_row.get("open")) or pd.isna(exit_row.get("date")):
                    break
                exit_price = exit_row["open"]
                exit_date = exit_row["date"]
                ret = (exit_price / entry_price) - 1 if entry_price and exit_price else None
                trades.append({
                    "entry_date": str(entry_date)[:10],
                    "exit_date": str(exit_date)[:10],
                    "entry_price": float(entry_price),
                    "exit_price": float(exit_price),
                    "return": ret,
                    "holding_days": hold,
                    "entry_vma20": float(entry_vma) if not pd.isna(entry_vma) else None
                })
                in_pos=False
                entry_price=None
                entry_date=None
                entry_vma=None
                hold=0
    # close open pos at last close
    if in_pos and entry_price is not None:
        last = df.iloc[-1]
        exit_price = last.get("close")
        exit_date = last.get("date")
        if not pd.isna(exit_price) and not pd.isna(exit_date):
            ret = (exit_price / entry_price) - 1 if entry_price and exit_price else None
            trades.append({
                "entry_date": str(entry_date)[:10],
                "exit_date": str(exit_date)[:10],
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "return": ret,
                "holding_days": hold,
                "entry_vma20": float(entry_vma) if not pd.isna(entry_vma) else None
            })
    return trades

def summarize(trades):
    rets = [t["return"] for t in trades if t["return"] is not None]
    if not rets:
        return {"n":0}
    arr = np.array(rets)
    wins = (arr>0).sum()
    cum = np.prod(1+arr)-1
    return {"n": len(arr), "win_rate": float(wins)/len(arr), "avg_return": float(arr.mean()), "median_return": float(np.median(arr)), "cumulative_return": float(cum)}

def main():
    base = Path(".")
    ind_dir = base / "data_indicators"
    out = base / "data_public" / "backtests"
    out.mkdir(parents=True, exist_ok=True)

    files = sorted(glob.glob(str(ind_dir/"*.csv")))
    tickers = []
    for f in files:
        name = Path(f).stem
        ticker = name[:-len("_indicators")] if name.endswith("_indicators") else name
        df = pd.read_csv(f, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
        tickers.append((ticker, df))

    rows=[]
    for ticker, df in tickers:
        # ensure columns
        for c in ("T_hma16","T_ema12_26","T_ema10_50_100","VMA20","open","close"):
            if c not in df.columns:
                df[c]=pd.NA
        # build combined ema
        def comb(r):
            s1 = norm_sig(r.get("T_ema12_26",0))
            s2 = norm_sig(r.get("T_ema10_50_100",0))
            v = s1+s2
            return 1 if v>0 else (-1 if v<0 else 0)
        df["T_emas_combined"] = df.apply(comb, axis=1)

        # for each method run first and second-entry variants
        for method,col in [("HMA16","T_hma16"),("EMAs","T_emas_combined")]:
            trades_first = run_backtest_variant(df, col, entry_repeat=1)
            trades_second = run_backtest_variant(df, col, entry_repeat=2)
            s_first = summarize(trades_first)
            s_second = summarize(trades_second)
            rows.append({
                "ticker": ticker,
                "method": method,
                "variant": "first",
                **s_first
            })
            rows.append({
                "ticker": ticker,
                "method": method,
                "variant": "second",
                **s_second
            })
            # save trade CSVs
            pd.DataFrame(trades_first).to_csv(out/f"{ticker}_{method}_first_trades.csv", index=False, encoding="utf-8-sig")
            pd.DataFrame(trades_second).to_csv(out/f"{ticker}_{method}_second_trades.csv", index=False, encoding="utf-8-sig")

    pd.DataFrame(rows).to_csv(out/"summary_repeat_compare.csv", index=False, encoding="utf-8-sig")
    print("[OK] terminado. Archivo:", out/"summary_repeat_compare.csv")

if __name__=="__main__":
    main()