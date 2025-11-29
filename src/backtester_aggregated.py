#!/usr/bin/env python3
import glob
from pathlib import Path
from collections import defaultdict
import pandas as pd
import numpy as np

def norm_sig(v):
    if pd.isna(v):
        return 0
    if isinstance(v, (int, float, np.integer, np.floating)):
        if v > 0: return 1
        if v < 0: return -1
        return 0
    s = str(v).strip().lower()
    if s in ("1","buy","compra","long","+","true","1.0"): return 1
    if s in ("-1","sell","venta","short","-","false","-1.0"): return -1
    return 0

def run_backtest(df, sig_col, max_hold=30, vma_median=None):
    trades = []
    in_pos = False
    entry_idx = None
    hold = 0
    entry_price = None
    entry_date = None
    entry_vma = None
    n = len(df)
    for i in range(n-1):
        sig = norm_sig(df.iloc[i].get(sig_col, 0))
        if not in_pos and sig == 1:
            entry_idx = i + 1
            if entry_idx >= n: continue
            row = df.iloc[entry_idx]
            if pd.isna(row.get("open")) or pd.isna(row.get("date")): continue
            entry_price = row["open"]
            entry_date = row["date"]
            entry_vma = row.get("VMA20", np.nan)
            in_pos = True
            hold = 0
            continue
        if in_pos:
            hold += 1
            exit_sig = norm_sig(df.iloc[i+1].get(sig_col, 0)) if (i+1) < n else 0
            if exit_sig == -1 or hold >= max_hold:
                exit_idx = i + 1
                if exit_idx >= n: break
                rowx = df.iloc[exit_idx]
                if pd.isna(rowx.get("open")) or pd.isna(rowx.get("date")):
                    break
                exit_price = rowx["open"]
                exit_date = rowx["date"]
                ret = (exit_price / entry_price) - 1 if entry_price and exit_price else None
                vma_confirm = None
                if vma_median is not None and not pd.isna(entry_vma):
                    vma_confirm = bool(entry_vma > vma_median)
                trades.append({
                    "entry_date": str(entry_date)[:10],
                    "entry_price": float(entry_price),
                    "exit_date": str(exit_date)[:10],
                    "exit_price": float(exit_price),
                    "return": ret,
                    "holding_days": int(hold),
                    "entry_vma20": float(entry_vma) if not pd.isna(entry_vma) else None,
                    "vma20_confirm": vma_confirm
                })
                in_pos = False
                entry_idx = None
                entry_price = None
                entry_date = None
                entry_vma = None
                hold = 0
    # close open pos at last close
    if in_pos and entry_price is not None:
        last = df.iloc[-1]
        exit_price = last.get("close")
        exit_date = last.get("date")
        if not pd.isna(exit_price) and not pd.isna(exit_date):
            ret = (exit_price / entry_price) - 1 if entry_price and exit_price else None
            vma_confirm = None
            if vma_median is not None and not pd.isna(entry_vma):
                vma_confirm = bool(entry_vma > vma_median)
            trades.append({
                "entry_date": str(entry_date)[:10],
                "entry_price": float(entry_price),
                "exit_date": str(exit_date)[:10],
                "exit_price": float(exit_price),
                "return": ret,
                "holding_days": int(hold),
                "entry_vma20": float(entry_vma) if not pd.isna(entry_vma) else None,
                "vma20_confirm": vma_confirm
            })
    return trades

def summarize_trades(trades):
    rets = [t["return"] for t in trades if t["return"] is not None]
    if not rets:
        return {"n_trades": 0, "win_rate": None, "avg_return": None,
                "median_return": None, "cumulative_return": None, "max_drawdown": None}
    arr = np.array(rets)
    wins = (arr > 0).sum()
    cum = np.prod(1 + arr) - 1
    eq = np.cumprod(1 + arr)
    peak = np.maximum.accumulate(eq)
    dd = ((eq - peak) / peak).min() if len(peak) > 0 else 0
    return {
        "n_trades": int(len(arr)),
        "win_rate": float(wins) / len(arr),
        "avg_return": float(arr.mean()),
        "median_return": float(np.median(arr)),
        "cumulative_return": float(cum),
        "max_drawdown": float(dd)
    }

def analyze_candles(df, sig_col):
    counts = defaultdict(int)
    total = 0
    for i in range(len(df)):
        if norm_sig(df.iloc[i].get(sig_col, 0)) != 0:
            total += 1
            pat = str(df.iloc[i].get("candle_pattern", "")).strip()
            if pat:
                counts[pat] += 1
    return dict(counts), total

def pair_adr_local(tick_dfs):
    pairs = []
    for t in list(tick_dfs.keys()):
        if t.endswith("_BA"):
            local = t[:-3]
            if local in tick_dfs:
                pairs.append((local, t))
    return pairs

def safe_read_csv(path):
    try:
        return pd.read_csv(path, parse_dates=["date"])
    except Exception:
        try:
            return pd.read_csv(path, parse_dates=["date"], encoding="cp1252")
        except Exception:
            return pd.read_csv(path, parse_dates=["date"], encoding="latin1")

def ensure_cols(df, cols):
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    return df

def main():
    base = Path(".")
    d1 = base / "data_indicators" / "csv"
    d2 = base / "data_indicators"
    indicators_dir = d1 if d1.exists() and any(d1.glob("*.csv")) else d2
    out = base / "data_public" / "backtests"
    out.mkdir(parents=True, exist_ok=True)

    files = sorted(indicators_dir.glob("*.csv"))
    tickers = {}
    warnings = []

    for f in files:
        name = f.stem
        ticker = name[:-len("_indicators")] if name.endswith("_indicators") else name
        try:
            df = safe_read_csv(f)
            df = df.sort_values("date").reset_index(drop=True)
            df = ensure_cols(df, ["open","close","T_hma16","T_ema12_26","T_ema10_50_100","VMA20","candle_pattern"])
            tickers[ticker] = df
        except Exception as e:
            warnings.append({"file": str(f), "issue": str(e)})

    summary_rows = []
    candle_rows = []
    trades_files = []

    for ticker, df in tickers.items():
        median_vma = df["VMA20"].dropna().median() if "VMA20" in df.columns else None
        # combined EMA signal
        def comb_row(r):
            s1 = norm_sig(r.get("T_ema12_26", 0))
            s2 = norm_sig(r.get("T_ema10_50_100", 0))
            s = s1 + s2
            return 1 if s > 0 else (-1 if s < 0 else 0)
        df["T_emas_combined"] = df.apply(comb_row, axis=1)

        for method, col in [("HMA16", "T_hma16"), ("EMAs", "T_emas_combined"), ("VMA20", "VMA20")]:
            try:
                trades = run_backtest(df, col, vma_median=median_vma)
                # ensure CSV exists even if empty
                trades_df = pd.DataFrame(trades)
                if trades_df.empty:
                    trades_df = pd.DataFrame(columns=["entry_date","entry_price","exit_date","exit_price","return","holding_days","entry_vma20","vma20_confirm"])
                csv_file = out / f"{ticker}_{method}_trades.csv"
                trades_df.to_csv(csv_file, index=False, encoding="utf-8-sig")
                trades_files.append({"ticker": ticker, "method": method, "file": str(csv_file)})
                stats = summarize_trades(trades)
                row = {"ticker": ticker, "method": method, **stats}
                # VMA20 confirmation substats
                if not trades_df.empty:
                    dfc = trades_df[trades_df["vma20_confirm"] == True]
                    dfn = trades_df[trades_df["vma20_confirm"] == False]
                    row["n_confirmed"] = len(dfc)
                    row["n_not_confirmed"] = len(dfn)
                    row["cumulative_confirmed"] = float(np.prod(1 + dfc["return"].dropna()) - 1) if len(dfc) > 0 else None
                    row["cumulative_not_confirmed"] = float(np.prod(1 + dfn["return"].dropna()) - 1) if len(dfn) > 0 else None
                else:
                    row["n_confirmed"] = 0
                    row["n_not_confirmed"] = 0
                    row["cumulative_confirmed"] = None
                    row["cumulative_not_confirmed"] = None
                summary_rows.append(row)
            except Exception as e:
                warnings.append({"ticker": ticker, "method": method, "issue": str(e)})

        # candle analysis for HMA16 and EMAs
        for method, col in [("HMA16", "T_hma16"), ("EMAs", "T_emas_combined")]:
            try:
                matches, total = analyze_candles(df, col)
                for pat, cnt in matches.items():
                    candle_rows.append({"ticker": ticker, "method": method, "candle_pattern": pat, "pattern_matches": int(cnt), "total_signals": int(total), "match_rate": float(cnt) / total if total>0 else 0.0})
            except Exception as e:
                warnings.append({"ticker": ticker, "method": method, "issue": f"candle:{e}"})

    # ADR vs local
    adr_rows = []
    pairs = pair_adr_local(tickers)
    for local, adr in pairs:
        try:
            dl = tickers[local]
            da = tickers[adr]
            merged = pd.merge(dl[["date","T_hma16"]], da[["date","T_hma16"]], on="date", how="inner", suffixes=("_local","_adr"))
            merged["sig_local"] = merged["T_hma16_local"].apply(norm_sig)
            merged["sig_adr"] = merged["T_hma16_adr"].apply(norm_sig)
            corr = merged["sig_local"].corr(merged["sig_adr"]) if len(merged)>1 else None
            merged["lag"] = merged["sig_local"] - merged["sig_adr"]
            avg_lag = float(merged["lag"].mean()) if len(merged)>0 else None
            adr_rows.append({"local_ticker": local, "adr_ticker": adr, "correlation": corr, "avg_lag": avg_lag})
        except Exception as e:
            warnings.append({"pair": f"{local}/{adr}", "issue": str(e)})

    # build dataframes and save
    df_summary = pd.DataFrame(summary_rows)
    if df_summary.empty:
        df_summary = pd.DataFrame(columns=["ticker","method","n_trades","win_rate","avg_return","median_return","cumulative_return","max_drawdown","n_confirmed","n_not_confirmed","cumulative_confirmed","cumulative_not_confirmed"])
    df_candles = pd.DataFrame(candle_rows)
    if df_candles.empty:
        df_candles = pd.DataFrame(columns=["ticker","method","candle_pattern","pattern_matches","total_signals","match_rate"])
    df_adr = pd.DataFrame(adr_rows)
    if df_adr.empty:
        df_adr = pd.DataFrame(columns=["local_ticker","adr_ticker","correlation","avg_lag"])
    df_warnings = pd.DataFrame(warnings) if warnings else pd.DataFrame(columns=["info"])

    df_summary.to_csv(out / "summary_all_tickers.csv", index=False, encoding="utf-8-sig")
    df_candles.to_csv(out / "candle_analysis.csv", index=False, encoding="utf-8-sig")
    df_adr.to_csv(out / "adr_vs_local.csv", index=False, encoding="utf-8-sig")
    df_warnings.to_csv(out / "backtest_warnings.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(trades_files).to_csv(out / "trades_files_list.csv", index=False, encoding="utf-8-sig")

    # Excel
    try:
        excel_path = out / "backtests_summary.xlsx"
        with pd.ExcelWriter(excel_path, engine="openpyxl") as w:
            df_summary.to_excel(w, sheet_name="summary_all_tickers", index=False)
            df_candles.to_excel(w, sheet_name="candle_analysis", index=False)
            df_adr.to_excel(w, sheet_name="adr_vs_local", index=False)
            df_warnings.to_excel(w, sheet_name="warnings", index=False)
            pd.DataFrame(trades_files).to_excel(w, sheet_name="trades_files", index=False)
    except Exception:
        # keep CSVs, write warning
        df_warnings = pd.DataFrame(warnings)
        df_warnings.to_csv(out / "backtest_warnings.csv", index=False, encoding="utf-8-sig")

    print("[OK] Archivos en data_public/backtests/")
    print(" -> backtests_summary.xlsx  (si openpyxl disponible)")
    print(" -> summary_all_tickers.csv, candle_analysis.csv, adr_vs_local.csv, backtest_warnings.csv")
    print(" -> trades por ticker: *_HMA16_trades.csv, *_EMAs_trades.csv, *_VMA20_trades.csv")

if __name__ == "__main__":
    main()