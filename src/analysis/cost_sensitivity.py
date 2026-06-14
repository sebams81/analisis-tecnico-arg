# ============================================================================
# cost_sensitivity.py
# ============================================================================
"""
cost_sensitivity.py
Escenario de sensibilidad al costo de transacción para el Capítulo 6.

NO re-corre el backtest ni modifica la config canónica (COST_PER_TRADE = 1%).
El costo es aditivo por trade (net = gross - costo), así que el retorno a un costo
arbitrario c se reconstruye desde los trades ya generados:

    ret_a_costo_c = return_canónico + (COST_PER_TRADE - c)

(el número de operaciones no depende del costo: la lógica de entrada/salida es la
misma). Para Buy & Hold, un solo round trip por ventana: cum_c = cum_canónico + (COST_PER_TRADE - c).

Para los niveles de costo pedidos (por defecto 0%, 0,5%, 1%) escribe, por universo
(LOCAL en peso / MEP en USD), un CSV con CAGR y retorno acumulado (media y mediana)
por método × corte × costo, el conteo de operaciones por método, y cuántos tickers
le ganan a B&H en cada nivel.
"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.config.logging_conf import get_logger
from src.config.study_config import STUDY_CUTOFF_DATE, COST_PER_TRADE
from src.analysis.cap6_aggregates import (
    universe_of,
    cagr,
    _years,
    METHODS,
    CUTS,
    BACKTESTS_DIR,
)

logger = get_logger("cost_sensitivity")

CANON_COST = COST_PER_TRADE  # config canónica (1%), no se modifica
COST_LEVELS = [0.0, 0.005, 0.01]


def _bucket(entry_date):
    return "is" if str(entry_date)[:10] <= STUDY_CUTOFF_DATE else "oos"


def build_per_ticker(summary, cost_levels):
    """ticker × método × corte × costo -> cum, cagr y n (trades). Reconstrucción
    aditiva desde los *_trades.csv canónicos; B&H desde summary."""
    rows = []
    for ticker in sorted(summary["ticker"].unique()):
        uni = universe_of(ticker)
        if uni is None:
            continue
        for method in METHODS:
            f = BACKTESTS_DIR / f"{ticker}_{method}_trades.csv"
            if not f.exists():
                continue
            td = pd.read_csv(f).dropna(subset=["return"])
            if "entry_date" not in td.columns:
                continue
            td["cut"] = td["entry_date"].apply(_bucket)
            for cut in CUTS:
                sub = td if cut == "total" else td[td["cut"] == cut]
                r = sub["return"].to_numpy(float)
                for c in cost_levels:
                    cum = (np.prod(1 + (r + (CANON_COST - c))) - 1) if len(r) else np.nan
                    rows.append({
                        "ticker": ticker, "universe": uni, "method": method,
                        "cut": cut, "cost": c, "n_trades": len(r),
                        "cum_return": cum, "cagr": cagr(cum, _years(cut)),
                    })
        bh = summary[(summary["ticker"] == ticker) & (summary["method"] == "B&H")]
        if not bh.empty:
            bh = bh.iloc[0]
            for cut in CUTS:
                v = bh.get(f"cumulative_return_{cut}")
                for c in cost_levels:
                    cum = (float(v) + (CANON_COST - c)) if pd.notna(v) else np.nan
                    rows.append({
                        "ticker": ticker, "universe": uni, "method": "B&H",
                        "cut": cut, "cost": c, "n_trades": (1 if pd.notna(v) else 0),
                        "cum_return": cum, "cagr": cagr(cum, _years(cut)),
                    })
    return pd.DataFrame(rows)


def aggregate(per_ticker, cost_levels):
    """Agrega por universo × método × corte × costo (media/mediana) y cuenta
    tickers que superan a B&H en cada nivel."""
    out = []
    for uni in ["LOCAL", "MEP"]:
        sub = per_ticker[per_ticker["universe"] == uni]
        for method in METHODS + ["B&H"]:
            for cut in CUTS:
                for c in cost_levels:
                    g = sub[(sub["method"] == method) & (sub["cut"] == cut) & (sub["cost"] == c)]
                    n_beats = np.nan
                    if method != "B&H":
                        bh = sub[(sub["method"] == "B&H") & (sub["cut"] == cut) & (sub["cost"] == c)].set_index("ticker")["cum_return"]
                        st = g.set_index("ticker")["cum_return"]
                        common = st.index.intersection(bh.index)
                        mask = st.loc[common].notna() & bh.loc[common].notna()
                        n_beats = int((st.loc[common][mask] > bh.loc[common][mask]).sum())
                    out.append({
                        "universe": uni, "method": method, "cut": cut, "cost": c,
                        "n_tickers": int(g["cum_return"].notna().sum()),
                        "n_trades_total": int(g["n_trades"].sum()),
                        "cagr_mean": g["cagr"].mean(), "cagr_median": g["cagr"].median(),
                        "cum_return_mean": g["cum_return"].mean(), "cum_return_median": g["cum_return"].median(),
                        "n_beats_bh": n_beats,
                    })
    return pd.DataFrame(out)


def _print_tables(agg, cost_levels):
    order = {m: i for i, m in enumerate(METHODS + ["B&H"])}
    for uni in ["LOCAL", "MEP"]:
        a = agg[agg["universe"] == uni]
        print(f"\n{'='*72}\n  UNIVERSO {uni}  -- CAGR media (mediana) por nivel de costo\n{'='*72}")
        for cut in CUTS:
            print(f"\n  [{cut.upper()}]")
            head = f"  {'metodo':<14}" + "".join(f"{str(c*100)+'%':>16}" for c in cost_levels)
            print(head)
            cc = a[a["cut"] == cut].copy()
            for m in sorted(cc["method"].unique(), key=lambda x: order[x]):
                row = f"  {m:<14}"
                for c in cost_levels:
                    g = cc[(cc["method"] == m) & (cc["cost"] == c)].iloc[0]
                    row += f"{g['cagr_mean']*100:>9.1f} ({g['cagr_median']*100:>4.0f})"
                print(row)

    print(f"\n{'='*72}\n  OPERACIONES por metodo (constante en todos los costos)\n{'='*72}")
    print(f"  {'metodo':<14}{'LOCAL':>10}{'MEP':>10}{'TOTAL':>10}")
    base = agg[(agg["cut"] == "total") & (agg["cost"] == cost_levels[0])]
    for m in METHODS:
        l = int(base[(base["method"] == m) & (base["universe"] == "LOCAL")]["n_trades_total"].sum())
        me = int(base[(base["method"] == m) & (base["universe"] == "MEP")]["n_trades_total"].sum())
        print(f"  {m:<14}{l:>10}{me:>10}{l+me:>10}")

    print(f"\n{'='*72}\n  Tickers que SUPERAN a B&H por nivel de costo\n{'='*72}")
    for uni in ["LOCAL", "MEP"]:
        print(f"\n  {uni}:")
        for cut in CUTS:
            for c in cost_levels:
                cells = ""
                for m in METHODS:
                    g = agg[(agg["universe"] == uni) & (agg["method"] == m) & (agg["cut"] == cut) & (agg["cost"] == c)].iloc[0]
                    cells += f"  {m}:{int(g['n_beats_bh'])}/{int(g['n_tickers'])}"
                print(f"    {cut.upper():<6} costo {str(c*100)+'%':<5}{cells}")


def main(cost_levels=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    levels = cost_levels or COST_LEVELS

    summary = pd.read_csv(BACKTESTS_DIR / "summary_all_tickers.csv")
    per_ticker = build_per_ticker(summary, levels)
    agg = aggregate(per_ticker, levels)

    for uni in ["LOCAL", "MEP"]:
        out_file = BACKTESTS_DIR / f"cost_sensitivity_{uni}.csv"
        agg[agg["universe"] == uni].drop(columns=["universe"]).to_csv(
            out_file, index=False, encoding="utf-8-sig"
        )
        logger.info(f"Escrito {out_file.name}")

    _print_tables(agg, levels)


if __name__ == "__main__":
    cli = [float(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else None
    main(cli)
