# Modulo: Config
# Script: logging_conf.py
# Objetivo: Registro centralizado de eventos y auditoría.
#
# Descripcion Funcional: 
# Gestiona la salida de logs en dos canales independientes: un archivo físico con el 
# detalle técnico completo (DEBUG) y la consola para resúmenes de ejecución (INFO). 
# Implementa un filtro personalizado para mantener la pantalla libre de ruido técnico, 
# asegurando que toda la actividad quede registrada cronológicamente en archivos 
# únicos por sesión para su posterior revisión.

import logging
from logging import Logger
from pathlib import Path
from datetime import datetime

# Se suben dos niveles (parents[2]) porque ahora el archivo está en src/config/
project_root = Path(__file__).resolve().parents[2]
logs_dir = project_root / "logs"
logs_dir.mkdir(exist_ok=True)

# Filtro para mostrar solo mensajes marcados como 'summary' en consola
class SummaryFilter(logging.Filter):
    def filter(self, record):
        return bool(getattr(record, "summary", False))

def get_logger(name: str) -> Logger:
    logger = logging.getLogger(name)
    
    # Evita duplicar configuraciones en la misma sesión
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = logs_dir / f"{name}_{timestamp}.log"

    # Salida a Archivo: Detalle técnico completo (DEBUG)
    fh = logging.FileHandler(file_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s %(message)s")
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)

    # Salida a Consola: Solo hitos importantes (INFO + Summary)
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.addFilter(SummaryFilter())
    sh_formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s %(message)s")
    sh.setFormatter(sh_formatter)
    logger.addHandler(sh)

    # Evitar propagación a handlers raíz
    logger.propagate = False

    return logger