"""
json_generator.py
Lee los CSVs del backtester + signals + indicators + fundamentals
y emite los 29 JSONs consumidos por el frontend en docs/data/.

NO recalcula indicadores ni señales. Solo serializa lo emitido por el pipeline.
Standalone, no integrado al pipeline. Correr on-demand para regenerar JSONs.
"""

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.config.logging_conf import get_logger
from src.config.study_config import (
    TICKERS_ACCIONES,
    STUDY_START_DATE,
    STUDY_CUTOFF_DATE,
    STUDY_END_DATE,
    COST_PER_TRADE,
)

logger = get_logger("json_generator")

BACKTESTS_DIR = project_root / "data_public" / "backtests"
INDICATORS_DIR = project_root / "data_indicators" / "csv"
SIGNALS_DIR = project_root / "data_signals" / "csv"
FUNDAMENTALS_RAW = project_root / "data_fundamentals" / "fundamentals.json"
OUT_DIR = project_root / "docs" / "data"

METHODS = ["HMA16", "EMA_12_26", "SMA_10_50_100", "B&H"]
SIGNAL_METHODS = ["HMA16", "EMA_12_26", "SMA_10_50_100"]  # B&H no tiene trades signal-driven

INDICATOR_COLS = ["hma16", "sma10", "sma50", "sma100", "ema12", "ema26"]
SIGNAL_COLS = ["T_hma16", "T_ema12_26", "T_sma10_50_100"]

# Mapping ticker base → sector (D1 confirmado)
SECTOR_MAP = {
    "PAMP": "Energía",
    "CEPU": "Energía",
    "EDN": "Energía",
    "TGSU2": "Energía",
    "YPFD": "Petróleo y Gas",
    "BMA": "Bancos",
    "GGAL": "Bancos",
    "BBAR": "Bancos",
    "SUPV": "Bancos",
    "TXAR": "Acero / Industria",
    "LOMA": "Materiales / Cemento",
    "TECO2": "Telecomunicaciones",
}


def _all_tickers():
    """24 tickers: 12 _BA + 12 _MEP, derivados de TICKERS_ACCIONES."""
    return TICKERS_ACCIONES + [t.replace("_BA", "_MEP") for t in TICKERS_ACCIONES]


def _calculate_warmup_end_date():
    """Primer dia donde TODOS los tickers tienen SMA100 calculada (no-NaN)."""
    firsts = []
    for ticker in _all_tickers():
        path = INDICATORS_DIR / f"{ticker}_indicators.csv"
        if not path.exists():
            continue
        ind = pd.read_csv(path)
        if "sma100" not in ind.columns:
            continue
        valid = ind[ind["sma100"].notna()]
        if not valid.empty:
            firsts.append(str(valid["date"].iloc[0]))
    return max(firsts) if firsts else None


def _none_if_nan(v):
    """Convierte NaN/inf a None para serialización JSON segura."""
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _row_to_dict(row, cols):
    return {c: _none_if_nan(row[c]) for c in cols if c in row.index}


def _records(df, cols=None):
    """Convierte DataFrame a list[dict] limpiando NaN."""
    if cols is None:
        cols = list(df.columns)
    out = []
    for _, row in df.iterrows():
        out.append({c: _none_if_nan(row[c]) for c in cols if c in df.columns})
    return out


def gen_meta():
    meta = {
        "pipeline_run_date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "study_start_date": STUDY_START_DATE,
        "study_cutoff_date": STUDY_CUTOFF_DATE,
        "study_end_date": STUDY_END_DATE,
        "warmup_end_date": _calculate_warmup_end_date(),
        "tickers_count": len(_all_tickers()),
        "period": f"{STUDY_START_DATE} to {STUDY_END_DATE}",
        "methods": METHODS,
        "cost_per_trade": COST_PER_TRADE,
    }
    out = OUT_DIR / "_meta.json"
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"_meta.json generado")
    return meta


def gen_daily_panel():
    """Para cada fecha entre warmup_end_date y la ultima rueda disponible,
    emite un snapshot de 24 entries con misma estructura que summary.json
    pero por dia. NO recalcula nada: lee de data_signals/csv/ + sma100 de
    data_indicators/csv/ para filtrar dias pre-warmup."""
    warmup = _calculate_warmup_end_date()
    if warmup is None:
        logger.warning("No se pudo calcular warmup_end_date - daily_panel.json no generado")
        return

    panel = {}
    for ticker in _all_tickers():
        sig_path = SIGNALS_DIR / f"{ticker}_signals.csv"
        ind_path = INDICATORS_DIR / f"{ticker}_indicators.csv"
        if not sig_path.exists() or not ind_path.exists():
            continue
        sig = pd.read_csv(sig_path)
        ind = pd.read_csv(ind_path)[["date", "sma100"]]
        merged = sig.merge(ind, on="date", how="left")
        merged = merged[merged["sma100"].notna() & (merged["date"] >= warmup)]

        mercado = "MEP" if ticker.endswith("_MEP") else "BA"
        for _, row in merged.iterrows():
            date = str(row["date"])
            entry = {
                "ticker": ticker,
                "mercado": mercado,
                "signals": {
                    "HMA16": _none_if_nan(row.get("T_hma16")),
                    "EMA_12_26": _none_if_nan(row.get("T_ema12_26")),
                    "SMA_10_50_100": _none_if_nan(row.get("T_sma10_50_100")),
                },
                "vma20_cat": _none_if_nan(row.get("vma20_cat")),
                "candle": _none_if_nan(row.get("candle_pattern")),
                "last_date": date,
            }
            panel.setdefault(date, []).append(entry)

    # Ordenar entries dentro de cada date por (ticker_base, mercado)
    for date in panel:
        panel[date].sort(key=lambda e: (e["ticker"].split("_")[0], e["mercado"]))

    out = OUT_DIR / "daily_panel.json"
    out.write_text(json.dumps(panel, ensure_ascii=False, indent=None), encoding="utf-8")
    n_dates = len(panel)
    n_entries = sum(len(v) for v in panel.values())
    logger.info(f"daily_panel.json generado: {n_dates} fechas, {n_entries} entries totales")


def gen_summary():
    """24 entradas, una por ticker. Las metricas vienen de summary_all_tickers.csv."""
    df_summary = pd.read_csv(BACKTESTS_DIR / "summary_all_tickers.csv")

    out_rows = []
    for ticker in _all_tickers():
        # Cargar última fila del signals csv para etiquetas y candle del día
        sig_path = SIGNALS_DIR / f"{ticker}_signals.csv"
        last_signals = {"HMA16": None, "EMA_12_26": None, "SMA_10_50_100": None}
        last_vma = None
        last_candle = None
        last_date = None
        if sig_path.exists():
            sig_df = pd.read_csv(sig_path)
            if not sig_df.empty:
                last_row = sig_df.iloc[-1]
                last_date = str(last_row["date"])
                last_signals["HMA16"] = _none_if_nan(last_row.get("T_hma16"))
                last_signals["EMA_12_26"] = _none_if_nan(last_row.get("T_ema12_26"))
                last_signals["SMA_10_50_100"] = _none_if_nan(last_row.get("T_sma10_50_100"))
                last_vma = _none_if_nan(last_row.get("vma20_cat"))
                last_candle = _none_if_nan(last_row.get("candle_pattern"))

        # Métricas por método y subset (total/is/oos)
        metrics = {}
        for method in METHODS:
            row = df_summary[(df_summary["ticker"] == ticker) & (df_summary["method"] == method)]
            if row.empty:
                metrics[method] = {"total": None, "is": None, "oos": None}
                continue
            r = row.iloc[0]
            metrics[method] = {
                "total": {
                    "n_trades": int(r["n_trades_total"]) if pd.notna(r["n_trades_total"]) else 0,
                    "win_rate": _none_if_nan(r["win_rate_total"]),
                    "cumulative_return": _none_if_nan(r["cumulative_return_total"]),
                    "max_drawdown": _none_if_nan(r["max_drawdown_total"]),
                },
                "is": {
                    "n_trades": int(r["n_trades_is"]) if pd.notna(r["n_trades_is"]) else 0,
                    "win_rate": _none_if_nan(r["win_rate_is"]),
                    "cumulative_return": _none_if_nan(r["cumulative_return_is"]),
                    "max_drawdown": _none_if_nan(r["max_drawdown_is"]),
                },
                "oos": {
                    "n_trades": int(r["n_trades_oos"]) if pd.notna(r["n_trades_oos"]) else 0,
                    "win_rate": _none_if_nan(r["win_rate_oos"]),
                    "cumulative_return": _none_if_nan(r["cumulative_return_oos"]),
                    "max_drawdown": _none_if_nan(r["max_drawdown_oos"]),
                },
            }

        out_rows.append({
            "ticker": ticker,
            "mercado": "MEP" if ticker.endswith("_MEP") else "BA",
            "last_date": last_date,
            "signals": last_signals,
            "vma20_cat": last_vma,
            "candle": last_candle,
            "metrics": metrics,
        })

    out = OUT_DIR / "summary.json"
    out.write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"summary.json generado: {len(out_rows)} entradas")


def gen_validators():
    """72 entradas, una por (ticker, method) excluyendo B&H."""
    df = pd.read_csv(BACKTESTS_DIR / "validators_effectiveness.csv")
    out_rows = []
    for _, r in df.iterrows():
        out_rows.append({
            "ticker": r["ticker"],
            "method": r["method"],
            "vma": {
                "n_confirmed": int(r["n_vma_confirmed"]),
                "n_not_confirmed": int(r["n_vma_not_confirmed"]),
                "win_rate_confirmed": _none_if_nan(r["win_rate_vma_confirmed"]),
                "win_rate_not_confirmed": _none_if_nan(r["win_rate_vma_not_confirmed"]),
                "cumulative_confirmed": _none_if_nan(r["cumulative_vma_confirmed"]),
                "cumulative_not_confirmed": _none_if_nan(r["cumulative_vma_not_confirmed"]),
            },
            "candle": {
                "n_aligned": int(r["n_candle_aligned"]),
                "n_not_aligned": int(r["n_candle_not_aligned"]),
                "n_neutral": int(r["n_candle_neutral"]),
                "win_rate_aligned": _none_if_nan(r["win_rate_candle_aligned"]),
                "win_rate_not_aligned": _none_if_nan(r["win_rate_candle_not_aligned"]),
                "win_rate_neutral": _none_if_nan(r["win_rate_candle_neutral"]),
                "cumulative_aligned": _none_if_nan(r["cumulative_candle_aligned"]),
                "cumulative_not_aligned": _none_if_nan(r["cumulative_candle_not_aligned"]),
                "cumulative_neutral": _none_if_nan(r["cumulative_candle_neutral"]),
            },
        })
    out = OUT_DIR / "validators.json"
    out.write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"validators.json generado: {len(out_rows)} entradas")


def gen_local_vs_mep():
    """Lee adr_vs_local.csv (nombre legacy del pipeline) y emite local_vs_mep.json
    con campo mep_ticker (no adr_ticker). El MEP es tipo de cambio implicito,
    no un ADR; el rename refleja la realidad tecnica."""
    df = pd.read_csv(BACKTESTS_DIR / "adr_vs_local.csv")
    out_rows = []
    for _, r in df.iterrows():
        out_rows.append({
            "local_ticker": r["local_ticker"],
            "mep_ticker": r["adr_ticker"],
            "correlation": _none_if_nan(r["correlation"]),
            "avg_lag": _none_if_nan(r["avg_lag"]),
        })
    out = OUT_DIR / "local_vs_mep.json"
    out.write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"local_vs_mep.json generado: {len(out_rows)} entradas")


def gen_ticker(ticker):
    """Un archivo por ticker: OHLC + indicadores + señales mergeados por fecha + trades.

    Cada entry del array `ohlc` contiene los campos OHLCV + los 7 indicadores
    + las 3 señales por método + vma20_cat + candle. Pure merge: el generator
    no recalcula nada, solo serializa los CSVs ya producidos por el pipeline.
    """
    ind_path = INDICATORS_DIR / f"{ticker}_indicators.csv"
    sig_path = SIGNALS_DIR / f"{ticker}_signals.csv"
    if not ind_path.exists() or not sig_path.exists():
        logger.warning(f"Falta indicators o signals para {ticker} — skip")
        return False

    ind = pd.read_csv(ind_path)
    sig = pd.read_csv(sig_path)

    # Filtrar lower bound al inicio del estudio. SIN upper bound: el pipeline
    # debe operar "vivo" hasta la defensa y mas alla, reflejando la ultima rueda
    # descargada. El backtester filtra trades por STUDY_END_DATE; los OHLC e
    # indicadores del frontend se mantienen actualizados.
    ind = ind[ind["date"] >= STUDY_START_DATE].reset_index(drop=True)
    sig = sig[sig["date"] >= STUDY_START_DATE].reset_index(drop=True)

    # Merge por fecha. Inner join garantiza que cada día tenga ambos lados.
    # Si signals tiene más fechas que indicators (raro), se pierden — pero
    # eso preserva consistencia: cada entry del JSON tiene datos completos.
    merged = ind.merge(sig, on="date", how="inner", suffixes=("", "_sig"))

    # OHLC mergeado: cada entry contiene OHLCV + indicadores + señales.
    # Renombre semántico: candle_pattern (CSV) → candle (consistente con summary.json).
    ohlc = []
    for _, r in merged.iterrows():
        ohlc.append({
            "time":            str(r["date"]),
            "open":            _none_if_nan(r.get("open")),
            "high":            _none_if_nan(r.get("high")),
            "low":             _none_if_nan(r.get("low")),
            "close":           _none_if_nan(r.get("close")),
            "volume":          _none_if_nan(r.get("volume")),
            "hma16":           _none_if_nan(r.get("hma16")),
            "ema12":           _none_if_nan(r.get("ema12")),
            "ema26":           _none_if_nan(r.get("ema26")),
            "sma10":           _none_if_nan(r.get("sma10")),
            "sma50":           _none_if_nan(r.get("sma50")),
            "sma100":          _none_if_nan(r.get("sma100")),
            "vma20_ratio":     _none_if_nan(r.get("vma20_ratio")),
            "vma20_cat":       _none_if_nan(r.get("vma20_cat")),
            "T_hma16":         _none_if_nan(r.get("T_hma16")),
            "T_ema12_26":      _none_if_nan(r.get("T_ema12_26")),
            "T_sma10_50_100":  _none_if_nan(r.get("T_sma10_50_100")),
            "candle":          _none_if_nan(r.get("candle_pattern")),
        })

    # Trades por método (3 métodos signal-driven; B&H se excluye)
    trades = {}
    for method in SIGNAL_METHODS:
        trades_path = BACKTESTS_DIR / f"{ticker}_{method}_trades.csv"
        trades[method] = []
        if not trades_path.exists():
            continue
        td = pd.read_csv(trades_path)
        for _, r in td.iterrows():
            trades[method].append({
                "entry_date":           _none_if_nan(r.get("entry_date")),
                "entry_price":          _none_if_nan(r.get("entry_price")),
                "exit_date":            _none_if_nan(r.get("exit_date")),
                "exit_price":           _none_if_nan(r.get("exit_price")),
                "return":               _none_if_nan(r.get("return")),
                "holding_days":         _none_if_nan(r.get("holding_days")),
                "entry_vma20":          _none_if_nan(r.get("entry_vma20")),
                "vma20_confirm":        _none_if_nan(r.get("vma20_confirm")),
                "entry_candle_pattern": _none_if_nan(r.get("entry_candle_pattern")),
                "candle_aligned":       _none_if_nan(r.get("candle_aligned")),
                "is_in_sample":         _none_if_nan(r.get("is_in_sample")),
            })

    out = {
        "ticker": ticker,
        "ohlc": ohlc,
        "trades": trades,
    }
    (OUT_DIR / f"ticker_{ticker}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=None), encoding="utf-8"
    )
    return True


def _sector_for_event(tickers_afectados):
    """Mapea lista de tickers a sector (concatenado con ' / ' si hay varios)."""
    sectors = []
    for t in tickers_afectados:
        # Extraer base: PAMP_BA → PAMP, YPFD_MEP → YPFD
        base = t.replace("_BA", "").replace("_MEP", "")
        sec = SECTOR_MAP.get(base)
        if sec and sec not in sectors:
            sectors.append(sec)
    return " / ".join(sectors) if sectors else ""


def gen_fundamentals():
    """Lee el raw, limpia (PAM out, agrega id/fuente, popula sector) y escribe."""
    raw = json.loads(FUNDAMENTALS_RAW.read_text(encoding="utf-8"))
    out_rows = []
    for i, ev in enumerate(raw, start=1):
        tickers_clean = [t for t in ev.get("tickers_afectados", []) if t != "PAM"]
        out_rows.append({
            "id": i,
            "fecha": ev.get("fecha"),
            "tickers_afectados": tickers_clean,
            "sector": _sector_for_event(tickers_clean),
            "fuente": "manual",
            "evento": ev.get("evento"),
            "impacto": ev.get("impacto"),
        })
    (OUT_DIR / "fundamentals.json").write_text(
        json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"fundamentals.json generado: {len(out_rows)} entradas (PAM removido)")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando generacion de JSONs para frontend")

    gen_meta()
    gen_summary()
    gen_validators()
    gen_local_vs_mep()
    gen_fundamentals()
    gen_daily_panel()

    n_ok = 0
    for ticker in _all_tickers():
        if gen_ticker(ticker):
            n_ok += 1
    logger.info(f"ticker_*.json generados: {n_ok}/{len(_all_tickers())}")

    logger.info("Listo")


if __name__ == "__main__":
    main()
