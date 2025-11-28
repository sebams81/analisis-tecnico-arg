from pathlib import Path
import pandas as pd

BASE_DIR = Path.cwd()
DATA_INDICATORS_DIR = BASE_DIR / "data_indicators"
DATA_SIGNALS_DIR = BASE_DIR / "data_signals"

BOARD_FILE = DATA_SIGNALS_DIR / "board_general.csv"

def ensure_output_dir():
    DATA_SIGNALS_DIR.mkdir(parents=True, exist_ok=True)

def infer_mercado(ticker: str) -> str:
    t = str(ticker).upper() if pd.notna(ticker) else ""
    # Acepta sufijos .BA, _BA y -BA como Local
    if t.endswith(".BA") or t.endswith("_BA") or t.endswith("-BA"):
        return "Local"
    return "ADR"

def label_first_second_occurrence(series: pd.Series) -> pd.Series:
    """
    Convierte ocurrencias Compra/Venta a Compra/ Venta Temprana/Confirmada.
    - Si ya está etiquetado como 'Compra Temprana/Confirmada' o 'Venta Temprana/Confirmada' se mantiene.
    - Celdas vacías se mantienen vacías.
    """
    result = []
    compra_count = 0
    venta_count = 0
    last_signal_type = None

    for val in series:
        if pd.isna(val) or str(val).strip() == "":
            result.append("")
            last_signal_type = "Otro"
            compra_count = venta_count = 0
            continue

        val_str = str(val).strip()

        # Mantener etiquetas ya convertidas
        if val_str.lower().startswith("compra tempr") or val_str.lower().startswith("compra conf"):
            result.append(val_str)
            last_signal_type = "Compra"
            compra_count = max(compra_count, 1)
            venta_count = 0
            continue
        if val_str.lower().startswith("venta tempr") or val_str.lower().startswith("venta conf"):
            result.append(val_str)
            last_signal_type = "Venta"
            venta_count = max(venta_count, 1)
            compra_count = 0
            continue

        # Normalizar inputs que contienen la palabra compra/venta
        if "compra" in val_str.lower():
            if last_signal_type != "Compra":
                compra_count = 0
            compra_count += 1
            result.append("Compra Temprana" if compra_count == 1 else "Compra Confirmada")
            last_signal_type = "Compra"
            venta_count = 0
            continue

        if "venta" in val_str.lower():
            if last_signal_type != "Venta":
                venta_count = 0
            venta_count += 1
            result.append("Venta Temprana" if venta_count == 1 else "Venta Confirmada")
            last_signal_type = "Venta"
            compra_count = 0
            continue

        # Otros estados se copian tal cual
        result.append(val_str)
        last_signal_type = "Otro"
        compra_count = venta_count = 0

    return pd.Series(result, index=series.index)

def process_ticker_board(ind_file: Path) -> pd.DataFrame:
    # Lectura robusta y eliminación de posibles filas que reintroducen el header
    df = pd.read_csv(ind_file, header=0)
    if 'date' in df.columns:
        df = df[df['date'].astype(str).str.lower() != 'date']
    else:
        return pd.DataFrame()

    # Normalizar ticker; si no existe, tomar del nombre del archivo
    if 'ticker' in df.columns:
        df['ticker'] = df['ticker'].astype(str).str.strip().str.upper() \
                       .str.replace(r'\.BA$', '_BA', regex=True) \
                       .str.replace(r'-BA$', '_BA', regex=True)
    else:
        df['ticker'] = ind_file.stem.replace('_indicators', '').upper()

    required_cols = [
        "date",
        "ticker",
        "ema50",
        "T_hma16",
        "T_ema12_26",
        "T_ema10_50_100",
        "vma20_cat",
        "candle_signal",
        "candle_pattern",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{ind_file.name} falta columnas requeridas: {missing}")

    # Ordenar por fecha y parsear fechas de forma segura
    df["date"] = pd.to_datetime(df["date"], errors='coerce')
    df = df.sort_values("date").reset_index(drop=True)

    # Filtrar filas donde ema50 ya tiene valor (no NaN)
    df = df[~df["ema50"].isna()].copy()
    if df.empty:
        return pd.DataFrame()

    # Inferir mercado
    df["mercado"] = df["ticker"].astype(str).apply(infer_mercado)

    # Aplicar lógica de primera/segunda ocurrencia para cada indicador
    df["hma16_ui"] = label_first_second_occurrence(df["T_hma16"])
    df["ema_12_26_ui"] = label_first_second_occurrence(df["T_ema12_26"])
    df["ema_10_50_100_ui"] = label_first_second_occurrence(df["T_ema10_50_100"])

    # Copiar vma20_cat a vma20
    df["vma20_ui"] = df["vma20_cat"].fillna("").astype(str)

    # Asegurar que candle_* sean strings
    df["candle_signal"] = df["candle_signal"].fillna("").astype(str)
    df["candle_pattern"] = df["candle_pattern"].fillna("").astype(str)

    # Seleccionar y renombrar columnas al formato final de Hoja 1
    out_cols = {
        "date": "date",
        "ticker": "ticker",
        "mercado": "mercado",
        "ema_12_26_ui": "ema_12_26",
        "ema_10_50_100_ui": "ema_10_50_100",
        "hma16_ui": "hma16",
        "vma20_ui": "vma20",
        "candle_signal": "candle_signal",
        "candle_pattern": "candle_pattern",
    }

    df_out = df[list(out_cols.keys())].rename(columns=out_cols)

    return df_out

def build_board_general() -> pd.DataFrame:
    indicator_files = sorted(DATA_INDICATORS_DIR.glob("*_indicators.csv"))
    if not indicator_files:
        print("⚠️  No se encontraron archivos *_indicators.csv en data_indicators.")
        print("    Ejecutá primero: python src/indicator_calculator.py")
        return pd.DataFrame()

    all_rows = []

    print(f"Archivos de indicadores encontrados: {len(indicator_files)}\n")

    for ind_file in indicator_files:
        ticker_name = ind_file.stem.replace("_indicators", "")
        print(f"Procesando Hoja 1 para {ticker_name}...")

        df_ticker = process_ticker_board(ind_file)

        if df_ticker.empty:
            print(f"  ⚠️  {ticker_name}: sin filas con ema50 válida. Se omite en el board.")
            continue

        all_rows.append(df_ticker)
        print(f"  ✓ {ticker_name}: {len(df_ticker)} filas agregadas al board.")

    if not all_rows:
        print("⚠️  No se generó información para ningún ticker.")
        return pd.DataFrame()

    board = pd.concat(all_rows, ignore_index=True)

    # Orden final: por fecha y luego ticker
    board = board.sort_values(["date", "ticker"]).reset_index(drop=True)

    return board

def main():
    ensure_output_dir()

    print("=" * 70)
    print("MÓDULO 4 – Generación de Hoja 1 (board_general.csv)")
    print("=" * 70)
    print(f"Entrada:  {DATA_INDICATORS_DIR}")
    print(f"Salida:   {BOARD_FILE}\n")

    board = build_board_general()
    if board.empty:
        print("⚠️  No se generó board_general.csv por falta de datos.")
        return

    board.to_csv(BOARD_FILE, index=False)
    print(f"\n✓ board_general.csv generado con {len(board)} filas.")
    print(f"  Ubicación: {BOARD_FILE}")

    print("\n" + "=" * 70)
    print("Módulo 4 – Hoja 1 completado")
    print("=" * 70)

if __name__ == "__main__":
    main()