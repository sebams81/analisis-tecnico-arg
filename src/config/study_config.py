"""
Constantes metodológicas de la tesis - NO MODIFICAR sin actualizar el doc.

Estas constantes definen el alcance metodológico del estudio y son inmutables
una vez fijadas. Cualquier cambio invalida la reproducibilidad de los
resultados reportados en la tesis.
"""

# Inicio del estudio: primera rueda en que el dólar MEP sintético tuvo cotización
# (AL30 listó el 07/09/2020 pero AL30D recién el 14/09/2020 → la base MEP arranca ahí).
STUDY_START_DATE = "2020-09-14"

# Fecha de corte para el split in-sample / out-of-sample (70/30).
# Calculada sobre 1380 ruedas entre STUDY_START_DATE y STUDY_END_DATE.
# IS: 965 ruedas (69.93%), OOS: 415 ruedas (30.07%).
STUDY_CUTOFF_DATE = "2024-08-28"

# Cierre del snapshot. Datos posteriores no se usan en la tesis.
STUDY_END_DATE = "2026-05-12"

# Costo total round-trip (entrada + salida) como fracción decimal
# 0.5% es el costo conservador estimado para inversores minoristas argentinos
# (comisión de broker + arancel de mercado + costo de bid-ask spread)
COST_PER_TRADE = 0.005

# Universo del estudio: bonos para construir el MEP, acciones a analizar.
# El primer elemento de cada tupla es el código PPI; el segundo es el label
# usado como nombre de archivo en data_*/csv/.
BONOS = [
    ("AL30", "AL30_BA"),
    ("AL30D", "AL30D_BA"),
]

ACCIONES = [
    ("PAMP", "PAMP_BA"), ("GGAL", "GGAL_BA"), ("YPFD", "YPFD_BA"),
    ("BMA", "BMA_BA"), ("CEPU", "CEPU_BA"), ("SUPV", "SUPV_BA"),
    ("BBAR", "BBAR_BA"), ("EDN", "EDN_BA"), ("TXAR", "TXAR_BA"),
    ("LOMA", "LOMA_BA"), ("TECO2", "TECO2_BA"), ("TGSU2", "TGSU2_BA"),
]

# Solo los labels (XXX_BA) — para módulos que solo necesitan iterar
# sobre las acciones (ej. synthetic_mep_generator).
TICKERS_ACCIONES = [label for _, label in ACCIONES]
