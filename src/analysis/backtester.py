# ============================================================================
# backtester.py
# ============================================================================
"""
backtester.py
Ejecuta backtests sobre señales de trading y genera reportes agregados.

Responsabilidades:
- Ejecutar backtests sobre señales HMA16, EMAs combinadas y VMA20.
- Calcular métricas de performance por ticker y método.
- Comparar señales entre ADRs y locales.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.config.logging_conf import get_logger
from src.config.study_config import STUDY_START_DATE, STUDY_CUTOFF_DATE, STUDY_END_DATE, COST_PER_TRADE

logger = get_logger("backtester")

INDICATORS_DIR = project_root / "data_indicators" / "csv"
SIGNALS_DIR = project_root / "data_signals" / "csv"
BACKTESTS_DIR = project_root / "data_public" / "backtests"

BACKTESTS_DIR.mkdir(parents=True, exist_ok=True)

# Inicio OOS = día siguiente al cutoff IS (string ISO)
_OOS_START_DATE = (datetime.strptime(STUDY_CUTOFF_DATE, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")


def norm_sig(v):
    """Normaliza señales a -1, 0, 1."""
    if pd.isna(v):
        return 0
    if isinstance(v, (int, float, np.integer, np.floating)):
        if v > 0:
            return 1
        if v < 0:
            return -1
        return 0
    s = str(v).strip().lower()
    if s in ("1", "buy", "compra", "compra temprana", "compra confirmada", "long", "+", "true", "1.0", "alcista", "señal alcista"):
        return 1
    if s in ("-1", "sell", "venta", "venta temprana", "venta confirmada", "short", "-", "false", "-1.0", "bajista", "señal bajista"):
        return -1
    return 0


def _classify_candle(pattern):
    """True = aligned (Marubozu_Alc/Engulfing_Alc), False = not_aligned (Marubozu_Baj/Engulfing_Baj),
    None = neutral (Doji o vacio)."""
    p = str(pattern).strip()
    if p in ("Marubozu_Alc", "Engulfing_Alc"):
        return True
    if p in ("Marubozu_Baj", "Engulfing_Baj"):
        return False
    return None


def run_backtest(df_indicators, df_signals, sig_col, max_hold=30, vma_median=None):
    """Ejecuta backtest sobre una señal."""
    trades = []
    in_pos = False
    entry_idx = None
    hold = 0
    entry_price = None
    entry_date = None
    entry_vma = None
    entry_candle_pattern = None
    n = len(df_signals)

    for i in range(n - 1):
        sig = norm_sig(df_signals.iloc[i].get(sig_col, 0))
        if not in_pos and sig == 1:
            entry_idx = i + 1
            if entry_idx >= n:
                continue
            row_sig = df_signals.iloc[entry_idx]
            row_ind = df_indicators.iloc[entry_idx]
            if pd.isna(row_ind.get("open")) or pd.isna(row_sig.get("date")):
                continue
            entry_price = row_ind["open"]
            entry_date = row_sig["date"]
            entry_vma = row_ind.get("vma20_ratio", np.nan)
            entry_candle_pattern = str(row_sig.get("candle_pattern", "")).strip() or None
            in_pos = True
            hold = 0
            continue

        if in_pos:
            hold += 1
            exit_sig = (
                norm_sig(df_signals.iloc[i].get(sig_col, 0)) if i < n else 0
            )
            if exit_sig == -1 or hold >= max_hold:
                exit_idx = i + 1
                if exit_idx >= n:
                    break
                rowx_sig = df_signals.iloc[exit_idx]
                rowx_ind = df_indicators.iloc[exit_idx]
                if pd.isna(rowx_ind.get("open")) or pd.isna(rowx_sig.get("date")):
                    break
                exit_price = rowx_ind["open"]
                exit_date = rowx_sig["date"]
                ret = (
                    (exit_price / entry_price) - 1 - COST_PER_TRADE if entry_price and exit_price else None
                )
                vma_confirm = None
                if vma_median is not None and not pd.isna(entry_vma):
                    vmm = vma_median.iloc[entry_idx]
                    if not pd.isna(vmm):
                        vma_confirm = bool(entry_vma > vmm)
                trades.append(
                    {
                        "entry_date": str(entry_date)[:10],
                        "entry_price": float(entry_price),
                        "exit_date": str(exit_date)[:10],
                        "exit_price": float(exit_price),
                        "return": ret,
                        "holding_days": int(hold),
                        "entry_vma20": (
                            float(entry_vma) if not pd.isna(entry_vma) else None
                        ),
                        "vma20_confirm": vma_confirm,
                        "entry_candle_pattern": entry_candle_pattern,
                        "candle_aligned": _classify_candle(entry_candle_pattern),
                    }
                )
                in_pos = False
                entry_idx = None
                entry_price = None
                entry_date = None
                entry_vma = None
                entry_candle_pattern = None
                hold = 0

    if in_pos and entry_price is not None:
        last_sig = df_signals.iloc[-1]
        last_ind = df_indicators.iloc[-1]
        exit_price = last_ind.get("open")
        exit_date = last_sig.get("date")
        if not pd.isna(exit_price) and not pd.isna(exit_date):
            ret = (
                (exit_price / entry_price) - 1 - COST_PER_TRADE if entry_price and exit_price else None
            )
            vma_confirm = None
            if vma_median is not None and not pd.isna(entry_vma):
                vmm = vma_median.iloc[entry_idx]
                if not pd.isna(vmm):
                    vma_confirm = bool(entry_vma > vmm)
            trades.append(
                {
                    "entry_date": str(entry_date)[:10],
                    "entry_price": float(entry_price),
                    "exit_date": str(exit_date)[:10],
                    "exit_price": float(exit_price),
                    "return": ret,
                    "holding_days": int(hold),
                    "entry_vma20": float(entry_vma) if not pd.isna(entry_vma) else None,
                    "vma20_confirm": vma_confirm,
                    "entry_candle_pattern": entry_candle_pattern,
                    "candle_aligned": _classify_candle(entry_candle_pattern),
                }
            )

    return trades


def run_buy_and_hold(df_indicators, start_date, end_date):
    """B&H: 1 trade desde start_date hasta end_date (ambos inclusivos).
    Aplica COST_PER_TRADE. Retorna trade dict o None si <2 dias disponibles."""
    df = df_indicators[
        (df_indicators["date"] >= start_date) &
        (df_indicators["date"] <= end_date)
    ].dropna(subset=["open", "close"])
    if len(df) < 2:
        return None
    entry_row = df.iloc[0]
    exit_row = df.iloc[-1]
    ret = (exit_row["close"] / entry_row["open"]) - 1 - COST_PER_TRADE
    return {
        "entry_date": str(entry_row["date"])[:10],
        "entry_price": float(entry_row["open"]),
        "exit_date": str(exit_row["date"])[:10],
        "exit_price": float(exit_row["close"]),
        "return": float(ret),
        "holding_days": int(len(df)),
        "entry_vma20": None,
        "vma20_confirm": None,
        "entry_candle_pattern": None,
        "candle_aligned": None,
    }


def summarize_trades(trades):
    """Calcula métricas de performance separadas por TOTAL / IS / OOS."""

    def _compute(subset):
        rets = [t["return"] for t in subset if t["return"] is not None]
        if not rets:
            return {
                "n_trades": 0,
                "win_rate": None,
                "cumulative_return": None,
                "max_drawdown": None,
            }
        arr = np.array(rets)
        wins = (arr > 0).sum()
        cum = np.prod(1 + arr) - 1
        eq = np.cumprod(1 + arr)
        peak = np.maximum.accumulate(eq)
        dd = ((eq - peak) / peak).min() if len(peak) > 0 else 0
        return {
            "n_trades": int(len(arr)),
            "win_rate": float(wins) / len(arr),
            "cumulative_return": float(cum),
            "max_drawdown": float(dd),
        }

    is_trades = [t for t in trades if t.get("is_in_sample") is True]
    oos_trades = [t for t in trades if t.get("is_in_sample") is False]

    result = {}
    for suffix, subset in [("total", trades), ("is", is_trades), ("oos", oos_trades)]:
        for k, v in _compute(subset).items():
            result[f"{k}_{suffix}"] = v
    return result


def pair_adr_local(tick_dfs):
    """Identifica pares ADR vs local."""
    pairs = []
    for t in list(tick_dfs.keys()):
        if t.endswith("_BA"):
            mep = t[:-3] + "_MEP"
            if mep in tick_dfs:
                pairs.append((t, mep))
    return pairs


def safe_read_csv(path):
    """Lee CSV con múltiples encodings."""
    try:
        return pd.read_csv(path, parse_dates=["date"])
    except Exception:
        try:
            return pd.read_csv(path, parse_dates=["date"], encoding="cp1252")
        except Exception:
            return pd.read_csv(path, parse_dates=["date"], encoding="latin1")


def ensure_cols(df, cols):
    """Asegura que existan columnas requeridas."""
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    return df


def main():
    """Flujo principal de backtesting."""
    start_time = datetime.now()
    logger.info("Iniciando backtester")

    signals_files = sorted(SIGNALS_DIR.glob("*_signals.csv"))
    # Excluir bonos (insumos del MEP, no instrumentos backtesteables)
    signals_files = [f for f in signals_files if not f.stem.startswith("AL30")]
    if not signals_files:
        logger.warning(f"No se encontraron archivos en {SIGNALS_DIR}")
        return

    logger.info(f"Archivos signals encontrados: {len(signals_files)}")

    tickers_signals = {}
    tickers_indicators = {}

    for f in signals_files:
        ticker = f.stem.replace("_signals", "")
        try:
            df_sig = safe_read_csv(f)
            df_sig = df_sig.sort_values("date").reset_index(drop=True)
            df_sig = ensure_cols(
                df_sig,
                [
                    "date",
                    "ticker",
                    "T_hma16",
                    "T_ema12_26",
                    "T_sma10_50_100",
                    "candle_pattern",
                ],
            )
            tickers_signals[ticker] = df_sig

            ind_file = INDICATORS_DIR / f"{ticker}_indicators.csv"
            if ind_file.exists():
                df_ind = safe_read_csv(ind_file)
                df_ind = df_ind.sort_values("date").reset_index(drop=True)
                df_ind = ensure_cols(
                    df_ind, ["date", "open", "close", "vma20_ratio"]
                )
                tickers_indicators[ticker] = df_ind
            else:
                logger.warning(f"[{ticker}] No se encontró archivo de indicadores")

            logger.info(f"[{ticker}] Cargado {len(df_sig)} filas")
        except Exception as e:
            logger.error(f"[{ticker}] Error cargando: {e}")

    summary_rows = []

    for ticker in tickers_signals.keys():
        if ticker not in tickers_indicators:
            logger.warning(f"[{ticker}] Sin indicadores, saltando")
            continue

        df_sig = tickers_signals[ticker]
        df_ind = tickers_indicators[ticker]

        median_vma = (
            df_ind["vma20_ratio"].expanding().median().shift(1)
            if "vma20_ratio" in df_ind.columns
            else None
        )

        for method, col in [
            ("HMA16", "T_hma16"),
            ("EMA_12_26", "T_ema12_26"),
            ("SMA_10_50_100", "T_sma10_50_100"),
        ]:
            try:
                trades = run_backtest(df_ind, df_sig, col, vma_median=median_vma)
                trades = [
                    {**t, "is_in_sample": t["entry_date"] <= STUDY_CUTOFF_DATE}
                    for t in trades
                    if STUDY_START_DATE <= t["entry_date"] <= STUDY_END_DATE
                ]
                trades_df = pd.DataFrame(trades)
                if trades_df.empty:
                    trades_df = pd.DataFrame(
                        columns=[
                            "entry_date",
                            "entry_price",
                            "exit_date",
                            "exit_price",
                            "return",
                            "holding_days",
                            "entry_vma20",
                            "vma20_confirm",
                            "entry_candle_pattern",
                            "candle_aligned",
                            "is_in_sample",
                        ]
                    )
                csv_file = BACKTESTS_DIR / f"{ticker}_{method}_trades.csv"
                trades_df.to_csv(csv_file, index=False, encoding="utf-8-sig")

                stats = summarize_trades(trades)
                row = {"ticker": ticker, "method": method, **stats}

                if not trades_df.empty:
                    dfc = trades_df[trades_df["vma20_confirm"] == True]
                    dfn = trades_df[trades_df["vma20_confirm"] == False]
                    row["n_confirmed"] = len(dfc)
                    row["n_not_confirmed"] = len(dfn)
                    row["cumulative_confirmed"] = (
                        float(np.prod(1 + dfc["return"].dropna()) - 1)
                        if len(dfc) > 0
                        else None
                    )
                    row["cumulative_not_confirmed"] = (
                        float(np.prod(1 + dfn["return"].dropna()) - 1)
                        if len(dfn) > 0
                        else None
                    )
                else:
                    row["n_confirmed"] = 0
                    row["n_not_confirmed"] = 0
                    row["cumulative_confirmed"] = None
                    row["cumulative_not_confirmed"] = None

                summary_rows.append(row)
                logger.info(f"[{ticker}] {method} OK {len(trades)} trades")

            except Exception as e:
                logger.error(f"[{ticker}] Error en {method}: {e}")

        # ============ Buy & Hold como 4to método ============
        try:
            bh_total = run_buy_and_hold(df_ind, STUDY_START_DATE, STUDY_END_DATE)
            bh_is = run_buy_and_hold(df_ind, STUDY_START_DATE, STUDY_CUTOFF_DATE)
            bh_oos = run_buy_and_hold(df_ind, _OOS_START_DATE, STUDY_END_DATE)

            bh_trades_rows = []
            if bh_total is not None:
                bh_trades_rows.append({**bh_total, "is_in_sample": None})
            if bh_is is not None:
                bh_trades_rows.append({**bh_is, "is_in_sample": True})
            if bh_oos is not None:
                bh_trades_rows.append({**bh_oos, "is_in_sample": False})
            bh_csv = BACKTESTS_DIR / f"{ticker}_B&H_trades.csv"
            pd.DataFrame(bh_trades_rows).to_csv(bh_csv, index=False, encoding="utf-8-sig")

            def _bh_metrics(t):
                if t is None:
                    return 0, None, None, None
                r = t["return"]
                return 1, (1.0 if r > 0 else 0.0), float(r), float(min(0.0, r))

            n_t, wr_t, cr_t, dd_t = _bh_metrics(bh_total)
            n_i, wr_i, cr_i, dd_i = _bh_metrics(bh_is)
            n_o, wr_o, cr_o, dd_o = _bh_metrics(bh_oos)

            bh_row = {
                "ticker": ticker, "method": "B&H",
                "n_trades_total": n_t, "win_rate_total": wr_t,
                "cumulative_return_total": cr_t, "max_drawdown_total": dd_t,
                "n_trades_is": n_i, "win_rate_is": wr_i,
                "cumulative_return_is": cr_i, "max_drawdown_is": dd_i,
                "n_trades_oos": n_o, "win_rate_oos": wr_o,
                "cumulative_return_oos": cr_o, "max_drawdown_oos": dd_o,
                "n_confirmed": 0, "n_not_confirmed": 0,
                "cumulative_confirmed": None, "cumulative_not_confirmed": None,
            }
            summary_rows.append(bh_row)
            logger.info(f"[{ticker}] B&H OK")
        except Exception as e:
            logger.error(f"[{ticker}] Error en B&H: {e}")

    adr_rows = []
    pairs = pair_adr_local(tickers_signals)
    logger.info(f"Pares ADR/local encontrados: {len(pairs)}")

    for local, adr in pairs:
        try:
            dl = tickers_signals[local]
            da = tickers_signals[adr]
            merged = pd.merge(
                dl[["date", "T_hma16"]],
                da[["date", "T_hma16"]],
                on="date",
                how="inner",
                suffixes=("_local", "_adr"),
            )
            merged["sig_local"] = merged["T_hma16_local"].apply(norm_sig)
            merged["sig_adr"] = merged["T_hma16_adr"].apply(norm_sig)
            corr = (
                merged["sig_local"].corr(merged["sig_adr"]) if len(merged) > 1 else None
            )
            merged["lag"] = merged["sig_local"] - merged["sig_adr"]
            avg_lag = float(merged["lag"].mean()) if len(merged) > 0 else None
            adr_rows.append(
                {
                    "local_ticker": local,
                    "adr_ticker": adr,
                    "correlation": corr,
                    "avg_lag": avg_lag,
                }
            )
            logger.info(f"Par {local}/{adr} analizado")
        except Exception as e:
            logger.error(f"Error en par {local}/{adr}: {e}")

    # ============ Agregador de validadores (VMA + candle) ============
    validators_rows = []
    for row in summary_rows:
        method = row["method"]
        if method == "B&H":
            continue
        ticker = row["ticker"]
        trades_csv = BACKTESTS_DIR / f"{ticker}_{method}_trades.csv"
        if not trades_csv.exists():
            continue
        td = pd.read_csv(trades_csv)
        if td.empty:
            continue

        # --- VMA validator (2 categorias) ---
        vma_yes = td[td["vma20_confirm"] == True]
        vma_no = td[td["vma20_confirm"] == False]
        n_vma_y, n_vma_n = len(vma_yes), len(vma_no)
        wr_vma_y = float((vma_yes["return"] > 0).mean()) if n_vma_y > 0 else None
        wr_vma_n = float((vma_no["return"] > 0).mean()) if n_vma_n > 0 else None
        cr_vma_y = float(np.prod(1 + vma_yes["return"].dropna()) - 1) if n_vma_y > 0 else None
        cr_vma_n = float(np.prod(1 + vma_no["return"].dropna()) - 1) if n_vma_n > 0 else None

        # --- Candle validator (3 categorias incluyendo neutral baseline) ---
        cand_y = td[td["candle_aligned"] == True]
        cand_n = td[td["candle_aligned"] == False]
        cand_neu = td[td["candle_aligned"].isna()]
        n_cand_y, n_cand_n, n_cand_neu = len(cand_y), len(cand_n), len(cand_neu)
        wr_cand_y = float((cand_y["return"] > 0).mean()) if n_cand_y > 0 else None
        wr_cand_n = float((cand_n["return"] > 0).mean()) if n_cand_n > 0 else None
        wr_cand_neu = float((cand_neu["return"] > 0).mean()) if n_cand_neu > 0 else None
        cr_cand_y = float(np.prod(1 + cand_y["return"].dropna()) - 1) if n_cand_y > 0 else None
        cr_cand_n = float(np.prod(1 + cand_n["return"].dropna()) - 1) if n_cand_n > 0 else None
        cr_cand_neu = float(np.prod(1 + cand_neu["return"].dropna()) - 1) if n_cand_neu > 0 else None

        validators_rows.append({
            "ticker": ticker, "method": method,
            "n_vma_confirmed": n_vma_y, "n_vma_not_confirmed": n_vma_n,
            "win_rate_vma_confirmed": wr_vma_y, "win_rate_vma_not_confirmed": wr_vma_n,
            "cumulative_vma_confirmed": cr_vma_y, "cumulative_vma_not_confirmed": cr_vma_n,
            "n_candle_aligned": n_cand_y, "n_candle_not_aligned": n_cand_n, "n_candle_neutral": n_cand_neu,
            "win_rate_candle_aligned": wr_cand_y, "win_rate_candle_not_aligned": wr_cand_n, "win_rate_candle_neutral": wr_cand_neu,
            "cumulative_candle_aligned": cr_cand_y, "cumulative_candle_not_aligned": cr_cand_n, "cumulative_candle_neutral": cr_cand_neu,
        })

    df_validators = pd.DataFrame(validators_rows)
    validators_file = BACKTESTS_DIR / "validators_effectiveness.csv"
    df_validators.to_csv(validators_file, index=False, encoding="utf-8-sig")

    df_summary = pd.DataFrame(summary_rows)

    df_adr = pd.DataFrame(adr_rows)
    if df_adr.empty:
        df_adr = pd.DataFrame(
            columns=["local_ticker", "adr_ticker", "correlation", "avg_lag"]
        )

    summary_file = BACKTESTS_DIR / "summary_all_tickers.csv"
    adr_file = BACKTESTS_DIR / "adr_vs_local.csv"

    df_summary.to_csv(summary_file, index=False, encoding="utf-8-sig")
    df_adr.to_csv(adr_file, index=False, encoding="utf-8-sig")

    end_time = datetime.now()

    sep = "=" * 60
    logger.info(sep)
    logger.info(f"  Tickers procesados: {len(tickers_signals)}")
    logger.info(f"  Duración: {(end_time - start_time).total_seconds():.2f} segundos")
    logger.info(sep)


if __name__ == "__main__":
    main()