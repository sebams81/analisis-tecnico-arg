# Modulo: Processing
# Script: data_normalizer.py
# Objetivo: Estandarización, ajuste por splits y certificación de series históricas.
#
# Descripcion Funcional:
# Componente de la capa de procesamiento que transforma los archivos crudos (2020-2026)
# en series estandarizadas. Aplica ajustes por eventos corporativos (splits) para
# eliminar saltos nominales, asegura la coherencia de la estructura OHLCV y
# consolida la información a nivel diario, dejando la serie apta para el cálculo
# de indicadores técnicos y modelos de trading.

import json
from pathlib import Path

import pandas as pd
from src.config.logging_conf import get_logger

logger = get_logger("data_normalization")

# Configuración de rutas (src/processing/ -> raíz)
BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data_raw" / "csv"
OUT_DIR = BASE_DIR / "data_normalized" / "csv"
SPLITS_PATH = BASE_DIR / "src" / "config" / "splits.json"

NORMAL_COLUMNS = ["date", "open", "high", "low", "close", "volume", "ticker"]


def apply_split_adjustments(df, ticker, splits_config):
    # Ajusta precios históricos para evitar distorsiones en las medias móviles.
    if ticker not in splits_config:
        return df

    df_adj = df.copy()
    for event in splits_config[ticker]:
        split_date = pd.to_datetime(event["date"])
        factor = event["factor"]
        
        # Ajuste de precios anteriores al evento
        mask = df_adj["date"] < split_date
        for col in ["open", "high", "low", "close"]:
            df_adj.loc[mask, col] = df_adj.loc[mask, col] * factor
            
        logger.info(f"[%s] Ajuste por split aplicado (Factor: {factor})", ticker)
    
    return df_adj

def read_raw_ohlcv(ticker: str, splits_config: dict) -> pd.DataFrame:
    # Proceso de limpieza y validación de la serie temporal completa.
    path = RAW_DIR / f"{ticker}.csv"
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame()

    df.columns = [c.strip().lower() for c in df.columns]

    # Estandarización de nombres de columnas
    df = df.rename(columns={
        "fecha": "date", "datetime": "date",
        "openingprice": "open", "price": "close", "volumen": "volume"
    })

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()

    # Conversión numérica masiva
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Aplicación de splits antes de consolidar
    df = apply_split_adjustments(df, ticker, splits_config)

    df = df.dropna(subset=["close"]).copy()
    df = df.sort_values("date")

    # Consolidación a diario (elimina duplicados intradiarios)
    df_daily = df.groupby(df["date"].dt.date).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).reset_index()

    df_daily["date"] = df_daily["date"].astype(str)

    return df_daily

def main():
    # Orquestador del procesamiento masivo de datos.
    logger.info("Iniciando normalización de series históricas (2016-2026)")
    
    # Carga de splits
    splits_config = {}
    if SPLITS_PATH.exists():
        with open(SPLITS_PATH, "r") as f:
            splits_config = json.load(f)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    raw_files = list(RAW_DIR.glob("*.csv"))
    processed = 0

    for f in raw_files:
        ticker = f.stem
        df = read_raw_ohlcv(ticker, splits_config)

        if df.empty:
            continue

        df["ticker"] = ticker
        for c in ["open", "high", "low", "close"]:
            df[c] = df[c].round(2)

        out_path = OUT_DIR / f"{ticker}_normalized.csv"
        df[NORMAL_COLUMNS].to_csv(out_path, index=False)

        logger.info(f"✓ {ticker} normalizado correctamente.", extra={"summary": True})
        processed += 1

    logger.info(f"Proceso finalizado. {processed} activos listos.", extra={"summary": True})

if __name__ == "__main__":
    main()