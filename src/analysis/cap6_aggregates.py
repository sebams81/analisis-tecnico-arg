# ============================================================================
# cap6_aggregates.py
# ============================================================================
"""
cap6_aggregates.py
Agregaciones para el Capítulo 6, separadas por universo (LOCAL en peso / MEP en USD).

Re-agrega `summary_all_tickers.csv` (no re-corre el backtest) y reconstruye una
curva de equity DIARIA por ticker×método para medir drawdown y time-in-market de
forma comparable con el drawdown diario de Buy & Hold (no trade-a-trade).

Por método × corte (Total/IS/OOS) y por universo escribe un CSV con:
  - retorno acumulado y CAGR anualizado (media y mediana entre tickers),
  - max drawdown diario (media y mediana) y time-in-market (media),
  - nº de tickers que le ganan a B&H (filas de estrategia).
La fila B&H incluye su propio max drawdown diario (time-in-market = 100%).

Convención de la curva de equity diaria:
  - En efectivo: equity constante.
  - En posición: marcada a mercado por el `close` diario.
  - Entrada al `open` del día de entrada; salida al `open` del día de salida,
    con el costo round-trip (COST_PER_TRADE) aplicado en la salida.
  - El drawdown es invariante a la re-base, así que cada corte se mide sobre la
    porción de la curva continua restringida a las fechas de la ventana.
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.config.logging_conf import get_logger
from src.config.study_config import (
    STUDY_START_DATE,
    STUDY_CUTOFF_DATE,
    STUDY_END_DATE,
    COST_PER_TRADE,
)

logger = get_logger("cap6_aggregates")

INDICATORS_DIR = project_root / "data_indicators" / "csv"
BACKTESTS_DIR = project_root / "data_public" / "backtests"

METHODS = ["HMA16", "EMA_12_26", "SMA_10_50_100"]
CUTS = ["total", "is", "oos"]
OOS_START_DATE = "2024-08-29"  # STUDY_CUTOFF_DATE + 1 día (inicio OOS)

WINDOWS = {
    "total": (STUDY_START_DATE, STUDY_END_DATE),
    "is": (STUDY_START_DATE, STUDY_CUTOFF_DATE),
    "oos": (OOS_START_DATE, STUDY_END_DATE),
}


def _years(cut):
    s, e = WINDOWS[cut]
    return (datetime.strptime(e, "%Y-%m-%d") - datetime.strptime(s, "%Y-%m-%d")).days / 365.25


def universe_of(ticker):
    if ticker.endswith("_BA"):
        return "LOCAL"
    if ticker.endswith("_MEP"):
        return "MEP"
    return None


def cagr(cum, years):
    if pd.isna(cum) or (1 + cum) <= 0 or years <= 0:
        return np.nan
    return (1 + cum) ** (1 / years) - 1


def _read_csv(path, parse_dates=("date",)):
    for enc in (None, "cp1252", "latin1"):
        try:
            return pd.read_csv(path, parse_dates=list(parse_dates), encoding=enc)
        except Exception:
            continue
    return pd.read_csv(path, parse_dates=list(parse_dates))


def build_strategy_equity(df_ind, trades):
    """Curva de equity diaria continua sobre todo el rango de df_ind.

    Devuelve DataFrame(date, equity, in_pos). `in_pos` marca los días en que se
    mantiene posición al cierre (entrada y holding); el día de salida queda flat.
    """
    df = df_ind.dropna(subset=["open", "close"]).sort_values("date").reset_index(drop=True)
    n = len(df)
    if n == 0:
        return pd.DataFrame(columns=["date", "equity", "in_pos"])
    dates = df["date"].dt.strftime("%Y-%m-%d").tolist()
    opens = df["open"].to_numpy(float)
    closes = df["close"].to_numpy(float)
    idx = {d: i for i, d in enumerate(dates)}

    state = ["cash"] * n  # cash / entry / hold / exit / single
    for _, t in trades.iterrows():
        ed, xd = str(t["entry_date"])[:10], str(t["exit_date"])[:10]
        if ed not in idx:
            continue
        i0 = idx[ed]
        i1 = idx[xd] if xd in idx else n - 1  # si sale fuera de rango, marca a fin de datos
        if i1 <= i0:
            if state[i0] == "cash":
                state[i0] = "single"
            continue
        if state[i0] == "cash":
            state[i0] = "entry"
        for k in range(i0 + 1, i1):
            if state[k] == "cash":
                state[k] = "hold"
        if state[i1] == "cash":
            state[i1] = "exit"

    equity = np.empty(n)
    in_pos = np.zeros(n, dtype=bool)
    e = 1.0
    for i in range(n):
        s = state[i]
        if s == "cash":
            m, pos = 1.0, False
        elif s == "entry":
            m, pos = closes[i] / opens[i], True
        elif s == "hold":
            m, pos = closes[i] / closes[i - 1], True
        elif s == "exit":
            m, pos = (opens[i] / closes[i - 1]) * (1 - COST_PER_TRADE), False
        else:  # single (entrada y salida el mismo día)
            m, pos = (1 - COST_PER_TRADE), False
        e *= m
        equity[i] = e
        in_pos[i] = pos
    return pd.DataFrame({"date": df["date"], "equity": equity, "in_pos": in_pos})


def build_bh_equity(df_ind):
    """Equity diaria de Buy & Hold: siempre invertido, MTM por close sobre el
    open de la primera rueda. El costo round-trip no altera la forma del drawdown."""
    df = df_ind.dropna(subset=["open", "close"]).sort_values("date").reset_index(drop=True)
    if len(df) == 0:
        return pd.DataFrame(columns=["date", "equity", "in_pos"])
    eq = df["close"].to_numpy(float) / df["open"].iloc[0]
    return pd.DataFrame({"date": df["date"], "equity": eq, "in_pos": True})


def max_drawdown(equity):
    eq = np.asarray(equity, float)
    if len(eq) == 0:
        return np.nan
    peak = np.maximum.accumulate(eq)
    return float((eq / peak - 1.0).min())


def _slice(curve, cut):
    s, e = WINDOWS[cut]
    m = (curve["date"] >= s) & (curve["date"] <= e)
    return curve.loc[m]


def build_per_ticker_metrics(summary):
    """Construye la tabla larga ticker×método×corte con cum, cagr, mdd, tim."""
    rows = []
    indicators = {}

    def _ind(ticker):
        if ticker not in indicators:
            f = INDICATORS_DIR / f"{ticker}_indicators.csv"
            indicators[ticker] = _read_csv(f) if f.exists() else None
        return indicators[ticker]

    for ticker in sorted(summary["ticker"].unique()):
        uni = universe_of(ticker)
        if uni is None:
            continue
        df_ind = _ind(ticker)

        for method in METHODS + ["B&H"]:
            srow = summary[(summary["ticker"] == ticker) & (summary["method"] == method)]
            if srow.empty:
                continue
            srow = srow.iloc[0]

            curve = None
            if df_ind is not None:
                if method == "B&H":
                    curve = build_bh_equity(df_ind)
                else:
                    tf = BACKTESTS_DIR / f"{ticker}_{method}_trades.csv"
                    if tf.exists():
                        trades = _read_csv(tf, parse_dates=[])
                        trades = trades.dropna(subset=["entry_date", "exit_date"])
                        curve = build_strategy_equity(df_ind, trades)

            for cut in CUTS:
                cum = srow.get(f"cumulative_return_{cut}")
                cum = float(cum) if pd.notna(cum) else np.nan
                mdd, tim = np.nan, np.nan
                if curve is not None and not curve.empty:
                    sl = _slice(curve, cut)
                    if not sl.empty:
                        mdd = max_drawdown(sl["equity"].to_numpy())
                        tim = float(sl["in_pos"].mean()) if method != "B&H" else 1.0
                rows.append({
                    "ticker": ticker,
                    "universe": uni,
                    "method": method,
                    "cut": cut,
                    "cum_return": cum,
                    "cagr": cagr(cum, _years(cut)),
                    "max_drawdown": mdd,
                    "time_in_market": tim,
                })
    return pd.DataFrame(rows)


def aggregate(per_ticker):
    """Agrega por universo×método×corte (media/mediana) y cuenta tickers que ganan a B&H."""
    out = []
    for uni in ["LOCAL", "MEP"]:
        sub = per_ticker[per_ticker["universe"] == uni]
        bh = sub[sub["method"] == "B&H"].set_index(["ticker", "cut"])["cum_return"]
        for method in METHODS + ["B&H"]:
            for cut in CUTS:
                g = sub[(sub["method"] == method) & (sub["cut"] == cut)]
                n_beats = np.nan
                if method != "B&H":
                    st = g.set_index("ticker")["cum_return"]
                    cmp = bh.xs(cut, level="cut") if cut in bh.index.get_level_values("cut") else pd.Series(dtype=float)
                    common = st.index.intersection(cmp.index)
                    mask = st.loc[common].notna() & cmp.loc[common].notna()
                    n_beats = int((st.loc[common][mask] > cmp.loc[common][mask]).sum())
                out.append({
                    "universe": uni,
                    "method": method,
                    "cut": cut,
                    "n_tickers": int(g["cum_return"].notna().sum()),
                    "cum_return_mean": g["cum_return"].mean(),
                    "cum_return_median": g["cum_return"].median(),
                    "cagr_mean": g["cagr"].mean(),
                    "cagr_median": g["cagr"].median(),
                    "max_drawdown_mean": g["max_drawdown"].mean(),
                    "max_drawdown_median": g["max_drawdown"].median(),
                    "time_in_market_mean": g["time_in_market"].mean(),
                    "n_beats_bh": n_beats,
                })
    return pd.DataFrame(out)


def _print_tables(agg):
    order = {m: i for i, m in enumerate(METHODS + ["B&H"])}
    for uni in ["LOCAL", "MEP"]:
        a = agg[agg["universe"] == uni].copy()
        a["o"] = a["method"].map(order)
        print(f"\n{'='*78}\n  UNIVERSO {uni}\n{'='*78}")
        for cut in CUTS:
            print(f"\n  [{cut.upper()}]")
            print(f"  {'método':<14}{'cum%':>9}{'CAGR%':>8}{'MDD%':>8}{'TIM%':>7}{'>B&H':>6}")
            cc = a[a["cut"] == cut].sort_values("o")
            for _, r in cc.iterrows():
                nb = "" if pd.isna(r["n_beats_bh"]) else f"{int(r['n_beats_bh'])}/{int(r['n_tickers'])}"
                print(f"  {r['method']:<14}{r['cum_return_mean']*100:>9.1f}{r['cagr_mean']*100:>8.1f}"
                      f"{r['max_drawdown_mean']*100:>8.1f}{r['time_in_market_mean']*100:>7.0f}{nb:>6}")


def main():
    summary = _read_csv(BACKTESTS_DIR / "summary_all_tickers.csv", parse_dates=[])
    per_ticker = build_per_ticker_metrics(summary)
    agg = aggregate(per_ticker)

    for uni in ["LOCAL", "MEP"]:
        out_file = BACKTESTS_DIR / f"cap6_aggregates_{uni}.csv"
        agg[agg["universe"] == uni].drop(columns=["universe"]).to_csv(
            out_file, index=False, encoding="utf-8-sig"
        )
        logger.info(f"Escrito {out_file.name}")

    _print_tables(agg)


if __name__ == "__main__":
    main()
