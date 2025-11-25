from pathlib import Path
from datetime import datetime, timedelta

import yfinance as yf


# Carpeta base del proyecto (dos niveles arriba de este archivo)
BASE_DIR = Path(__file__).resolve().parents[1]

# Carpeta donde se guardan los datos crudos
DATA_RAW_DIR = BASE_DIR / "data_raw"


# Pares Local / ADR tomados del mock.html
PAIRS = [
    ("PAMP.BA", "PAM"),
    ("GGAL.BA", "GGAL"),
    ("YPFD.BA", "YPF"),
    ("BMA.BA", "BMA"),
    ("CEPU.BA", "CEPU"),
    ("SUPV.BA", "SUPV"),
    ("BBAR.BA", "BBAR"),
    ("EDN.BA", "EDN"),
    ("TXAR.BA", "TX"),
    ("LOMA.BA", "LOMA"),
    ("TECO2.BA", "TEO"),
    ("TGSU2.BA", "TGS"),
]

# A partir de los pares armamos la lista completa de tickers a descargar
TICKERS = sorted({t for pair in PAIRS for t in pair})

# Días de histórico a descargar (ajustable)
HIST_DAYS = 365  # 1 año por ahora


def ensure_data_raw_dir():
    """
    Crea la carpeta data_raw si no existe.
    """
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)


def download_history_for_ticker(ticker: str):
    """
    Descarga datos históricos para un ticker usando yfinance
    y los guarda en un CSV dentro de data_raw.

    Por ahora: baja hasta HIST_DAYS días hacia atrás.
    """
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=HIST_DAYS)

    print(f"[{ticker}] Descargando desde {start_date} hasta {end_date}...")

    data = yf.download(
        ticker,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        progress=True,
        auto_adjust=True,
    )

    if data.empty:
        print(f"[{ticker}] Advertencia: yfinance devolvió un DataFrame vacío.")
        return

    # Aseguramos índice como columna para guardar la fecha
    data.reset_index(inplace=True)

    # Reemplazamos el punto por guion bajo para el nombre del archivo
    output_file = DATA_RAW_DIR / f"{ticker.replace('.', '_')}.csv"
    data.to_csv(output_file, index=False)
    print(f"[{ticker}] Datos guardados en: {output_file} (filas: {len(data)})")


def main():
    """
    Flujo:
      1. Asegura carpeta data_raw.
      2. Usa la lista de tickers derivada de PAIRS (locales + ADR).
      3. Descarga histórico para cada ticker y guarda CSVs.
    """
    ensure_data_raw_dir()
    print(f"Carpeta de datos verificada en: {DATA_RAW_DIR}")

    if not TICKERS:
        print("No hay tickers definidos en TICKERS. Revisar configuración.")
        return

    print(f"Tickers a procesar ({len(TICKERS)}): {', '.join(TICKERS)}")

    for ticker in TICKERS:
        download_history_for_ticker(ticker)

    print("Descarga finalizada.")


if __name__ == "__main__":
    main()