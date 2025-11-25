import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = BASE_DIR / "data_raw"
DATA_NORMALIZED_DIR = BASE_DIR / "data_normalized"

REQUIRED_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]

def ensure_output_dir():
    DATA_NORMALIZED_DIR.mkdir(exist_ok=True)

def normalize_single_file(csv_path: Path):
    df = pd.read_csv(csv_path)

    # 1) Verificar columnas mínimas
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{csv_path.name} falta columnas: {missing}")

    # 2) Quedarnos solo con las columnas necesarias y renombrar
    df = df[REQUIRED_COLUMNS].rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })

    # 3) Convertir tipos
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 4) Eliminar filas con datos faltantes críticos
    df = df.dropna(subset=["date", "open", "high", "low", "close", "volume"])

    # 5) Agregar ticker a partir del nombre del archivo
    ticker = csv_path.stem  # ej: PAMP_BA
    df["ticker"] = ticker

    # 6) Ordenar por fecha
    df = df.sort_values("date")

    # 7) Formato de fecha estándar en archivo
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    # 8) Guardar normalizado con sufijo
    out_name = f"{ticker}_normalized.csv"
    out_path = DATA_NORMALIZED_DIR / out_name
    df.to_csv(out_path, index=False)
    print(f"Guardado {out_path}")

def main():
    ensure_output_dir()

    csv_files = sorted(DATA_RAW_DIR.glob("*.csv"))
    if not csv_files:
        print("No hay CSV en data_raw. Ejecutá primero data_downloader.")
        return

    for csv_path in csv_files:
        print(f"Normalizando {csv_path.name}...")
        normalize_single_file(csv_path)

    print("\nNormalización completa.")

if __name__ == "__main__":
    main()