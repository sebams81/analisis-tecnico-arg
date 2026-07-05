"""Driver del benchmark de escalabilidad de la etapa de indicadores.
Corre un worker aislado por granularidad, arma la grilla 4x3 y emite CSV.
Celdas 'medido' = wall-clock real end-to-end; 'modelado' = n_tickers x seg/serie
(exacto porque la etapa es un for secuencial de tickers independientes)."""
import sys, json, subprocess, csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent          # validation/benchmark/scripts
BENCH_DIR = SCRIPT_DIR.parent                          # validation/benchmark (resultados)
REPO_ROOT = Path(__file__).resolve().parents[3]        # raiz del repo
ROOT = str(REPO_ROOT)
WORKER = SCRIPT_DIR / "worker_col.py"
N_TICKERS = [26, 100, 500, 1000]

# (nombre, filas_por_serie, n_tickers medidos end-to-end)
GRANS = [
    ("diario",       1400,   [26, 100, 500, 1000]),
    ("intradia_60m", 9000,   [26, 100, 500, 1000]),
    ("intradia_1m",  550000, [26]),  # resto modelado
]

results = {}
for name, rows, measured in GRANS:
    tmp = BENCH_DIR / f"tmp_{name}"
    print(f"[driver] worker {name} rows={rows} medidos={measured} ...", flush=True)
    p = subprocess.run(
        [sys.executable, str(WORKER), ROOT, str(rows), json.dumps(measured), str(tmp)],
        capture_output=True, text=True)
    if p.returncode != 0:
        print(f"[driver] FALLO {name}:\n{p.stderr}", flush=True)
        sys.exit(1)
    results[name] = json.loads(p.stdout.strip().splitlines()[-1])
    r = results[name]
    print(f"[driver]   {name}: seg/serie={r['per_series']:.4f}  pico_MB={r['peak_rss_mb']:.1f}", flush=True)

# armar grilla
out_csv = BENCH_DIR / "scalability_benchmark.csv"
with open(out_csv, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["granularidad", "n_tickers", "filas_por_serie", "filas_totales",
                "seg", "pico_MB", "fuente"])
    for name, rows, measured in GRANS:
        r = results[name]
        for n in N_TICKERS:
            filas_tot = rows * n
            if str(n) in r["agg"]:
                seg = r["agg"][str(n)]; fuente = "medido"
            else:
                seg = r["per_series"] * n; fuente = "modelado"
            w.writerow([name, n, rows, filas_tot, round(seg, 3),
                        round(r["peak_rss_mb"], 1), fuente])

print(f"[driver] CSV escrito: {out_csv}", flush=True)
print(out_csv.read_text(encoding="utf-8"))
