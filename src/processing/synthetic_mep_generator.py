# Modulo: Processing
# Script: synthetic_mep_generator.py
# Objetivo: Generación de precios sintéticos en MEP para toda la cartera.
#
# Descripcion Funcional: 
# Calcula el tipo de cambio MEP base (AL30/AL30D) y lo aplica como factor de 
# conversión a todos los activos locales normalizados. Genera una nueva serie 
# de tiempo para cada acción donde los precios (OHLC) se expresan en dólares MEP. 
# Esto permite analizar el rendimiento real de los activos omitiendo el efecto 
# inflacionario y de devaluación del peso argentino.

from pathlib import Path
import pandas as pd
from src.config.logging_conf import get_logger
from src.config.study_config import TICKERS_ACCIONES

logger = get_logger("synthetic_mep_generation")

# Configuración de rutas
BASE_DIR = Path(__file__).resolve().parents[2]
IN_DIR = BASE_DIR / "data_normalized" / "csv"
OUT_DIR = BASE_DIR / "data_normalized" / "csv"


def calculate_base_mep():
    # Genera la serie de referencia del dólar MEP (AL30/AL30D)
    path_ars = IN_DIR / "AL30_BA_normalized.csv"
    path_usd = IN_DIR / "AL30D_BA_normalized.csv"

    if not path_ars.exists() or not path_usd.exists():
        logger.error("Faltan bonos AL30 para calcular base MEP.")
        return None

    df_ars = pd.read_csv(path_ars)[['date', 'close']].rename(columns={'close': 'mep_price'})
    df_usd = pd.read_csv(path_usd)[['date', 'close']].rename(columns={'close': 'al30d_price'})
    
    df_mep = pd.merge(df_ars, df_usd, on='date', how='inner')
    df_mep['mep_value'] = df_mep['mep_price'] / df_mep['al30d_price']
    return df_mep[['date', 'mep_value']]

def main():
    logger.info("Iniciando generación de sintéticos MEP")

    df_mep_base = calculate_base_mep()
    if df_mep_base is None:
        return

    logger.info(f"Referencia MEP generada: {len(df_mep_base)} días")

    processed_count = 0
    for ticker in TICKERS_ACCIONES:
        path_in = IN_DIR / f"{ticker}_normalized.csv"
        
        if not path_in.exists():
            logger.warning(f"Archivo no encontrado para {ticker}")
            continue

        # Carga de acción en pesos y cruce con el valor del dólar MEP
        df_stock = pd.read_csv(path_in)
        df_merged = pd.merge(df_stock, df_mep_base, on='date', how='inner')

        # Conversión de toda la estructura de precios a MEP
        for col in ['open', 'high', 'low', 'close']:
            df_merged[col] = (df_merged[col] / df_merged['mep_value']).round(2)

        # Limpieza de nombres para el nuevo activo sintético
        ticker_mep = ticker.replace("_BA", "_MEP")
        df_merged['ticker'] = ticker_mep
        cols_final = ["date", "open", "high", "low", "close", "volume", "ticker"]
        
        out_path = OUT_DIR / f"{ticker_mep}_normalized.csv"
        df_merged[cols_final].to_csv(out_path, index=False)

        logger.info(f"[{ticker_mep}] Sintético MEP OK")
        processed_count += 1

    logger.info(f"Generación de sintéticos finalizada: {processed_count} tickers procesados")

if __name__ == "__main__":
    main()