"""Merge tiempo (scalability_benchmark.csv) + memoria (memory_benchmark.csv)
por granularidad. Descarta la columna pico_MB (PeakWorkingSetSize, no fiable)
y adjunta pico_neto_MB de tracemalloc."""
import csv
from pathlib import Path

SB = Path(__file__).resolve().parent.parent            # validation/benchmark

mem = {}
with open(SB / "memory_benchmark.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        mem[row["granularidad"]] = row["pico_neto_MB"]

rows_out = []
with open(SB / "scalability_benchmark.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        rows_out.append([
            row["granularidad"], row["n_tickers"], row["filas_por_serie"],
            row["filas_totales"], row["seg"], mem.get(row["granularidad"], ""),
            row["fuente"],
        ])

out = SB / "scalability_merged.csv"
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["granularidad", "n_tickers", "filas_por_serie", "filas_totales",
                "seg", "pico_neto_MB", "fuente"])
    w.writerows(rows_out)
print(f"CSV merge: {out}")
print(out.read_text(encoding="utf-8"))
