# src/data_downloader.py

from pathlib import Path

# Carpeta base del proyecto (dos niveles arriba de este archivo)
BASE_DIR = Path(__file__).resolve().parents[1]

# Carpeta donde se guardan los datos crudos
DATA_RAW_DIR = BASE_DIR / "data_raw"


def ensure_data_raw_dir():
    """
    Crea la carpeta data_raw si no existe.
    """
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)


def main():
    """
    Punto de entrada principal del módulo.
    Por ahora solo asegura que exista la carpeta data_raw.
    Más adelante acá vamos a:
      - Descargar datos de la fuente elegida
      - Guardarlos en archivos CSV/JSON dentro de data_raw
    """
    ensure_data_raw_dir()
    print(f"Carpeta de datos verificada en: {DATA_RAW_DIR}")


if __name__ == "__main__":
    main()