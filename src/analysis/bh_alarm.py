# ============================================================================
# bh_alarm.py
# ============================================================================
"""
bh_alarm.py
Escenario "Buy & Hold + alarma anti-desastre" para el Capítulo 6.

Base: comprar al inicio de la ventana y mantener; salir a efectivo cuando la
alarma marca bajista y reentrar cuando vuelve a alcista. NO optimiza ningún
período (usa los indicadores/señales tal cual). NO toca la config canónica.

Cuatro alarmas:
  - HMA16            (rápida)      -> señal T_hma16
  - EMA_12_26        (media)       -> señal T_ema12_26
  - SMA_10_50_100    (lenta)       -> señal T_sma10_50_100
  - precio<SMA100    (régimen puro)-> close vs sma100 (regla precio-vs-línea)

Mecánica (sin look-ahead): la alarma se evalúa al cierre del día t y la
salida/reentrada se ejecuta al open de t+1. Costo 0,5% por pata (1% por round
trip salida->reentrada); la compra inicial y la venta final también pagan 0,5%
cada una (= 1% del round trip base, igual que B&H puro).

Curva de equity diaria: invertido -> MTM por close; en cash -> equity constante.
Por universo (LOCAL/MEP) y corte (Total/IS/OOS) compara cada variante vs B&H puro
en CAGR, max drawdown diario, Calmar (CAGR/|MDD|) y peor caída de un día, y marca
dónde el Calmar mejora respecto de B&H.
"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.config.logging_conf import get_logger
from src.analysis.backtester import norm_sig
from src.analysis.cap6_aggregates import (
    universe_of,
    cagr,
    _years,
    max_drawdown,
    WINDOWS,
    CUTS,
    INDICATORS_DIR,
    BACKTESTS_DIR,
)

logger = get_logger("bh_alarm")

SIGNALS_DIR = project_root / "data_signals" / "csv"
LEG = 0.005  # costo por pata (1% por round trip)

# (nombre, tipo, columna)
ALARMS = [
    ("HMA16", "signal", "T_hma16"),
    ("EMA_12_26", "signal", "T_ema12_26"),
    ("SMA_10_50_100", "signal", "T_sma10_50_100"),
    ("precio<SMA100", "price_sma", "sma100"),
]


def _read(path):
    for enc in (None, "cp1252", "latin1"):
        try:
            return pd.read_csv(path, parse_dates=["date"], encoding=enc)
        except Exception:
            continue
    return None


def load_ticker(ticker):
    """Indicadores (precios + sma100) con las señales T_* unidas por fecha."""
    ind = _read(INDICATORS_DIR / f"{ticker}_indicators.csv")
    sig = _read(SIGNALS_DIR / f"{ticker}_signals.csv")
    if ind is None:
        return None
    cols = [c for c in ["date", "open", "close", "sma100"] if c in ind.columns]
    df = ind[cols].copy()
    if sig is not None:
        keep = [c for c in ["date", "T_hma16", "T_ema12_26", "T_sma10_50_100"] if c in sig.columns]
        df = df.merge(sig[keep], on="date", how="left")
    return df.sort_values("date").reset_index(drop=True)


def _positions(dfw, kind, col):
    """Estado diario in/out de la alarma (régimen con histéresis), ya rezagado un
    día (se ejecuta al open siguiente). Arranca invertido (B&H base)."""
    n = len(dfw)
    state = "in"
    raw = []
    for t in range(n):
        if kind == "signal":
            s = norm_sig(dfw[col].iloc[t]) if col in dfw.columns else 0
        else:  # price_sma
            c, sm = dfw["close"].iloc[t], dfw["sma100"].iloc[t]
            s = 0 if pd.isna(sm) or pd.isna(c) else (1 if c >= sm else -1)
        if s == 1:
            state = "in"
        elif s == -1:
            state = "out"
        raw.append(state)
    return ["in"] + raw[:-1]  # pos[0]=in (compra inicial); pos[t]=raw[t-1]


def _equity(dfw, pos):
    """Equity diaria con MTM en posición, plana en cash, costo 0,5% por pata."""
    n = len(dfw)
    op = dfw["open"].to_numpy(float)
    cl = dfw["close"].to_numpy(float)
    eq = np.empty(n)
    e = 1.0
    n_exits = 0
    for t in range(n):
        p = pos[t]
        pp = pos[t - 1] if t > 0 else "out"
        if p == "in" and pp == "in":
            m = cl[t] / cl[t - 1]
        elif p == "in" and pp == "out":
            m = (cl[t] / op[t]) * (1 - LEG)  # reentrada (compra)
        elif p == "out" and pp == "in":
            m = (op[t] / cl[t - 1]) * (1 - LEG)  # salida (venta)
            n_exits += 1
        else:
            m = 1.0
        e *= m
        eq[t] = e
    if pos[-1] == "in":
        eq[-1] *= (1 - LEG)  # venta final
    return eq, n_exits


def metrics_for(df, kind, col, cut):
    s, e = WINDOWS[cut]
    dfw = df[(df["date"] >= s) & (df["date"] <= e)].dropna(subset=["open", "close"]).reset_index(drop=True)
    if len(dfw) < 2:
        return None
    pos = _positions(dfw, kind, col)
    eq, n_exits = _equity(dfw, pos)
    cum = eq[-1] - 1.0
    cg = cagr(cum, _years(cut))
    mdd = max_drawdown(eq)
    rets = np.concatenate([[eq[0] - 1.0], np.diff(eq) / eq[:-1]])
    worst_day = float(rets.min())
    calmar = (cg / abs(mdd)) if (mdd is not None and mdd < 0 and cg == cg) else np.nan
    return {"cagr": cg, "mdd": mdd, "calmar": calmar, "worst_day": worst_day, "n_exits": n_exits}


def build(summary):
    variants = [("B&H", "allin", None)] + ALARMS  # B&H puro = siempre invertido
    rows = []
    for ticker in sorted(summary["ticker"].unique()):
        uni = universe_of(ticker)
        if uni is None:
            continue
        df = load_ticker(ticker)
        if df is None:
            continue
        for name, kind, col in variants:
            for cut in CUTS:
                if kind == "allin":
                    m = metrics_for(df, "signal", "__none__", cut)  # sin señal -> nunca sale
                else:
                    m = metrics_for(df, kind, col, cut)
                if m is None:
                    continue
                rows.append({"ticker": ticker, "universe": uni, "variant": name, "cut": cut, **m})
    return pd.DataFrame(rows)


def aggregate(per_ticker):
    variants = ["B&H"] + [a[0] for a in ALARMS]
    out = []
    for uni in ["LOCAL", "MEP"]:
        sub = per_ticker[per_ticker["universe"] == uni]
        bh = {cut: sub[(sub["variant"] == "B&H") & (sub["cut"] == cut)]["calmar"].median() for cut in CUTS}
        for v in variants:
            for cut in CUTS:
                g = sub[(sub["variant"] == v) & (sub["cut"] == cut)]
                if g.empty:
                    continue
                cal_med = g["calmar"].median()
                improves = "" if v == "B&H" else ("si" if (pd.notna(cal_med) and pd.notna(bh[cut]) and cal_med > bh[cut]) else "no")
                out.append({
                    "universe": uni, "variant": v, "cut": cut, "n_tickers": int(g["cagr"].notna().sum()),
                    "n_exits_mean": g["n_exits"].mean(),
                    "cagr_mean": g["cagr"].mean(), "cagr_median": g["cagr"].median(),
                    "mdd_mean": g["mdd"].mean(), "mdd_median": g["mdd"].median(),
                    "calmar_mean": g["calmar"].mean(), "calmar_median": cal_med,
                    "worstday_mean": g["worst_day"].mean(), "worstday_median": g["worst_day"].median(),
                    "calmar_improves_vs_bh": improves,
                })
    return pd.DataFrame(out)


def _print_tables(agg):
    variants = ["B&H"] + [a[0] for a in ALARMS]
    order = {v: i for i, v in enumerate(variants)}
    for uni in ["LOCAL", "MEP"]:
        a = agg[agg["universe"] == uni]
        print(f"\n{'='*86}\n  UNIVERSO {uni}  -- mediana entre tickers (CAGR/MDD/peor dia en %, Calmar ratio)\n{'='*86}")
        for cut in CUTS:
            print(f"\n  [{cut.upper()}]")
            print(f"  {'variante':<16}{'CAGR%':>8}{'MDD%':>8}{'Calmar':>9}{'peorDia%':>10}{'exits':>7}{'Calmar>B&H':>12}")
            cc = a[a["cut"] == cut]
            for v in sorted(cc["variant"].unique(), key=lambda x: order[x]):
                r = cc[cc["variant"] == v].iloc[0]
                print(f"  {v:<16}{r['cagr_median']*100:>8.1f}{r['mdd_median']*100:>8.1f}{r['calmar_median']:>9.2f}"
                      f"{r['worstday_median']*100:>10.1f}{r['n_exits_mean']:>7.1f}{r['calmar_improves_vs_bh']:>12}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    summary = pd.read_csv(BACKTESTS_DIR / "summary_all_tickers.csv")
    per_ticker = build(summary)
    agg = aggregate(per_ticker)
    for uni in ["LOCAL", "MEP"]:
        out_file = BACKTESTS_DIR / f"bh_alarm_{uni}.csv"
        agg[agg["universe"] == uni].drop(columns=["universe"]).to_csv(out_file, index=False, encoding="utf-8-sig")
        logger.info(f"Escrito {out_file.name}")
    _print_tables(agg)


if __name__ == "__main__":
    main()
