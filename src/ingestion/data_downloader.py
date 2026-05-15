# Modulo: Ingestion
# Script: data_downloader.py
# Objetivo: Backfill histórico desde 2020-09-04 e ingesta incremental diaria.
#
# Descripcion Funcional:
# Gestiona la extracción de datos desde la API de PPI con lógica de persistencia
# incremental. En su primera ejecución, realiza un backfill completo desde el 04/09/2020.
# En ejecuciones subsiguientes, identifica la última fecha registrada en el repositorio local
# y solicita únicamente el diferencial de datos hasta la fecha actual. El componente
# garantiza la continuidad de las series temporales para los 12 activos y bonos, evitando
# duplicaciones mediante la validación de fechas y consolidando la información en archivos
# CSV crudos.

from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import os
from dotenv import load_dotenv
from ppi_client.ppi import PPI
from src.config.logging_conf import get_logger
from src.config.study_config import BONOS, ACCIONES

load_dotenv()
logger = get_logger("data_ingestion")

# Configuración de rutas y parámetros temporales
BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data_raw"
CSV_DIR = RAW_DIR / "csv"

START_DATE_BACKFILL = datetime(2020, 9, 4)
TIMEFRAME = "A-48HS"


def get_client():
    ppi = PPI(sandbox=False)
    ppi.account.login_api(os.getenv("PPI_PUBLIC_KEY"), os.getenv("PPI_PRIVATE_KEY"))
    return ppi

def process_data(data):
    # Estandarización de columnas y consolidación OHLCV diaria
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    df['Day'] = df['date'].dt.strftime("%Y-%m-%d")
    
    return df.groupby("Day").agg({
        'openingPrice': 'first',
        'max': 'max',
        'min': 'min',
        'price': 'last',
        'volume': 'sum'
    }).rename(columns={
        'openingPrice': 'Open', 'max': 'High', 'min': 'Low', 'price': 'Close', 'volume': 'Volume'
    }).reset_index().rename(columns={'Day': 'Date'})

def run_ingestion():
    CSV_DIR.mkdir(parents=True, exist_ok=True)

    ppi = get_client()
    end_date = datetime.now()

    for ticker, label in (BONOS + ACCIONES):
        csv_path = CSV_DIR / f"{label}.csv"
        tipo = "BONOS" if (ticker, label) in BONOS else "ACCIONES"
        
        # Determinación del punto de inicio (Backfill vs Incremental)
        if csv_path.exists():
            existing_df = pd.read_csv(csv_path)
            last_date_str = existing_df["Date"].max()
            start_date = datetime.strptime(last_date_str, "%Y-%m-%d") + timedelta(days=1)
            mode = "incremental"
        else:
            start_date = START_DATE_BACKFILL
            mode = "backfill"

        # Validación: Si la fecha de inicio es mayor o igual a hoy, saltar
        if start_date.date() >= end_date.date():
            logger.info(f"– {label} ya está actualizado.", extra={"summary": True})
            continue

        try:
            logger.info(f"Descargando {label} ({mode}) desde {start_date.date()}")
            raw = ppi.marketdata.search(ticker, tipo, TIMEFRAME, start_date, end_date)
            
            if raw:
                new_df = process_data(raw)
                
                # Integración de datos: Append si existe, creación si es nuevo
                if mode == "incremental":
                    final_df = pd.concat([existing_df, new_df]).drop_duplicates(subset=["Date"])
                else:
                    final_df = new_df

                final_df.to_csv(csv_path, index=False)

                logger.info(f"✓ {label} {mode} completado.", extra={"summary": True})
            else:
                logger.warning(f"! {label} sin datos nuevos.", extra={"summary": True})
                
        except Exception as e:
            logger.error(f"✗ Error en {label}: {e}", extra={"summary": True})

if __name__ == "__main__":
    run_ingestion()