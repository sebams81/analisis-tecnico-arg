# ============================================================================
# regime_episode.py
# ============================================================================
"""
regime_episode.py
Robustez del régimen en el PEOR episodio de caída de B&H (Capítulo 6).

Selección objetiva por ticker (solo precio de B&H, sin cherry-picking):
  - Sobre la ventana Total, se identifica la mayor caída pico-a-valle de B&H
    (la que define su max drawdown): pico previo, valle, y recuperación.
  - La ventana del episodio va del PICO PREVIO hasta que B&H recupera ese pico;
    si no recupera dentro del dataset, hasta el final.
  - La ventana NO depende de ninguna estrategia.

Sobre esa misma ventana se miden las 4 alarmas sobre base B&H (ambas parten de
1.0 en el pico previo; la alarma paga 0,5% por pata en cada salida/reentrada, B&H
solo mantiene):
  - drawdown de cada alarma dentro de la ventana (¿sufrió menos en el crash?),
  - timing del exit (días antes del piso; positivo = salió antes = protector),
  - riqueza al recuperar B&H su pico: si la alarma queda por encima de B&H,
    protegió en neto incluyendo el rebote; si por debajo, perdió el rebote.

Se agrega por mediana entre los 12 tickers de cada universo y se reporta cuántos
terminan por encima de B&H al recuperar. NO optimiza nada, NO prueba ventanas
alternativas, NO toca la config canónica ni los CSV de Cap. 6.
"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.config.logging_conf import get_logger
from src.analysis.cap6_aggregates import universe_of, max_drawdown, WINDOWS, BACKTESTS_DIR
from src.analysis.bh_alarm import load_ticker, _positions, LEG, ALARMS

logger = get_logger("regime_episode")


def episode_window(df):
    """Ventana del peor episodio de B&H: pico previo -> recuperación (o fin)."""
    s, e = WINDOWS["total"]
    d = df[(df["date"] >= s) & (df["date"] <= e)].dropna(subset=["open", "close"]).reset_index(drop=True)
    eq = d["close"].to_numpy(float)
    if len(eq) < 3:
        return None
    runmax = np.maximum.accumulate(eq)
    dd = eq / runmax - 1.0
    trough = int(np.argmin(dd))
    peak = int(np.argmax(eq[: trough + 1]))
    peak_val = eq[peak]
    rec = next((t for t in range(trough + 1, len(eq)) if eq[t] >= peak_val), None)
    recovered = rec is not None
    if rec is None:
        rec = len(eq) - 1
    return {"d": d, "peak": peak, "trough": trough, "rec": rec,
            "bh_mdd": float(dd[trough]), "recovered": recovered}


def episode_equity(dep, kind, col):
    """Equity de una alarma dentro de la ventana, partiendo de 1.0 en el pico.
    Sin costo de compra inicial ni venta final (es continuación del hold); solo
    0,5% por pata en salidas/reentradas. Devuelve (equity, primer_dia_en_cash)."""
    pos = _positions(dep, kind, col)  # pos[0]="in" (en el pico, invertido)
    op = dep["open"].to_numpy(float)
    cl = dep["close"].to_numpy(float)
    n = len(dep)
    eq = np.empty(n)
    eq[0] = 1.0
    e = 1.0
    for t in range(1, n):
        p, pp = pos[t], pos[t - 1]
        if p == "in" and pp == "in":
            m = cl[t] / cl[t - 1]
        elif p == "in" and pp == "out":
            m = (cl[t] / op[t]) * (1 - LEG)
        elif p == "out" and pp == "in":
            m = (op[t] / cl[t - 1]) * (1 - LEG)
        else:
            m = 1.0
        e *= m
        eq[t] = e
    first_cash = next((t for t in range(n) if pos[t] == "out"), None)
    return eq, first_cash


def build(summary):
    rows = []
    for ticker in sorted(summary["ticker"].unique()):
        uni = universe_of(ticker)
        if uni is None:
            continue
        df = load_ticker(ticker)
        if df is None:
            continue
        ep = episode_window(df)
        if ep is None:
            continue
        d, peak, trough, rec = ep["d"], ep["peak"], ep["trough"], ep["rec"]
        dep = d.iloc[peak : rec + 1].reset_index(drop=True)
        trough_w = trough - peak  # índice del valle dentro de la ventana
        bh_eq, _ = episode_equity(dep, "signal", "__none__")  # B&H = nunca sale
        for name, kind, col in ALARMS:
            eq, first_cash = episode_equity(dep, kind, col)
            timing = (trough_w - first_cash) if first_cash is not None else np.nan
            rows.append({
                "ticker": ticker, "universe": uni, "alarm": name,
                "bh_mdd": ep["bh_mdd"], "recovered": ep["recovered"],
                "window_len": len(dep), "trough_day": trough_w,
                "alarm_mdd": max_drawdown(eq),
                "exit_days_before_floor": timing,
                "alarm_wealth_rec": float(eq[-1]),
                "bh_wealth_rec": float(bh_eq[-1]),
                "above_bh": bool(eq[-1] > bh_eq[-1]),
            })
    return pd.DataFrame(rows)


def aggregate(per_ticker):
    out = []
    for uni in ["LOCAL", "MEP"]:
        sub = per_ticker[per_ticker["universe"] == uni]
        n_tk = sub["ticker"].nunique()
        bh_mdd_med = sub.drop_duplicates("ticker")["bh_mdd"].median()
        n_rec = int(sub.drop_duplicates("ticker")["recovered"].sum())
        win_med = sub.drop_duplicates("ticker")["window_len"].median()
        for name, _, _ in ALARMS:
            g = sub[sub["alarm"] == name]
            out.append({
                "universe": uni, "alarm": name, "n_tickers": n_tk,
                "bh_episode_mdd_median": bh_mdd_med,
                "n_recovered": n_rec, "window_len_median": win_med,
                "alarm_mdd_median": g["alarm_mdd"].median(),
                "exit_days_before_floor_median": g["exit_days_before_floor"].median(),
                "alarm_wealth_at_recovery_median": g["alarm_wealth_rec"].median(),
                "bh_wealth_at_recovery_median": g["bh_wealth_rec"].median(),
                "n_above_bh_at_recovery": int(g["above_bh"].sum()),
            })
    return pd.DataFrame(out)


def _print_tables(agg):
    order = {a[0]: i for i, a in enumerate(ALARMS)}
    for uni in ["LOCAL", "MEP"]:
        a = agg[agg["universe"] == uni].sort_values("alarm", key=lambda s: s.map(order))
        ctx = a.iloc[0]
        print(f"\n{'='*90}")
        print(f"  UNIVERSO {uni}  (n={int(ctx['n_tickers'])})  -- peor episodio de B&H, medianas entre tickers")
        print(f"  B&H MDD del episodio (mediana): {ctx['bh_episode_mdd_median']*100:.1f}%   "
              f"recuperaron pico: {int(ctx['n_recovered'])}/{int(ctx['n_tickers'])}   "
              f"largo ventana (mediana): {ctx['window_len_median']:.0f} ruedas")
        print(f"{'='*90}")
        print(f"  {'alarma':<16}{'MDD alarma%':>13}{'exit (d antes piso)':>21}{'riqueza al recup.':>19}{'>B&H':>8}")
        for _, r in a.iterrows():
            print(f"  {r['alarm']:<16}{r['alarm_mdd_median']*100:>13.1f}{r['exit_days_before_floor_median']:>21.0f}"
                  f"{r['alarm_wealth_at_recovery_median']:>19.3f}{int(r['n_above_bh_at_recovery']):>6}/{int(r['n_tickers'])}")
        print(f"  {'(B&H referencia)':<16}{ctx['bh_episode_mdd_median']*100:>13.1f}{'-':>21}{ctx['bh_wealth_at_recovery_median']:>19.3f}{'-':>8}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    summary = pd.read_csv(BACKTESTS_DIR / "summary_all_tickers.csv")
    per_ticker = build(summary)
    agg = aggregate(per_ticker)
    for uni in ["LOCAL", "MEP"]:
        out_file = BACKTESTS_DIR / f"regime_episode_{uni}.csv"
        agg[agg["universe"] == uni].drop(columns=["universe"]).to_csv(out_file, index=False, encoding="utf-8-sig")
        logger.info(f"Escrito {out_file.name}")
    _print_tables(agg)


if __name__ == "__main__":
    main()
