"""Grafico log-log de escalabilidad desde scalability_merged.csv.
X=filas_totales (log), Y=seg (log), una linea por granularidad.
Tramos/marcadores medido = lleno; modelado = punteado/hueco. Salida SVG."""
import csv
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use("svg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

BENCH = Path(__file__).resolve().parent.parent         # validation/benchmark
src = BENCH / "scalability_merged.csv"

data = defaultdict(list)
with open(src, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        data[r["granularidad"]].append(
            (int(r["filas_totales"]), float(r["seg"]), r["fuente"]))

labels = {"diario": "Diario (1 400 filas/serie)",
          "intradia_60m": "Intradía 60m (9 000)",
          "intradia_1m": "Intradía 1m (550 000)"}
colors = {"diario": "#2563eb", "intradia_60m": "#16a34a", "intradia_1m": "#dc2626"}
order = ["diario", "intradia_60m", "intradia_1m"]

fig, ax = plt.subplots(figsize=(8.2, 5.6))
for g in order:
    pts = sorted(data[g])
    c = colors[g]
    # segmentos: solido si ambos extremos medido, punteado si alguno modelado
    for (x0, y0, f0), (x1, y1, f1) in zip(pts, pts[1:]):
        style = "-" if (f0 == "medido" and f1 == "medido") else ":"
        ax.plot([x0, x1], [y0, y1], style, color=c, lw=2, zorder=2)
    # marcadores: lleno=medido, hueco=modelado
    for x, y, fnt in pts:
        if fnt == "medido":
            ax.plot(x, y, "o", color=c, ms=7, zorder=3)
        else:
            ax.plot(x, y, "o", mfc="white", mec=c, mew=1.8, ms=7, zorder=3)

ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("Filas totales procesadas (n_tickers × filas/serie)  [log]")
ax.set_ylabel("Wall-clock de la etapa de indicadores [s, log]")
ax.set_title("Costo computacional de la etapa de indicadores sobre series sintéticas")
ax.grid(True, which="both", ls="--", lw=0.5, alpha=0.4)

# leyenda: granularidades + convencion de estilo
leg1 = [Line2D([0], [0], color=colors[g], lw=2, marker="o", ms=7, label=labels[g]) for g in order]
style_leg = [
    Line2D([0], [0], color="#555", lw=2, ls="-", marker="o", ms=7, label="medido (end-to-end)"),
    Line2D([0], [0], color="#555", lw=2, ls=":", marker="o", mfc="white", mec="#555", ms=7,
           label="modelado (n × seg/serie)"),
]
l1 = ax.legend(handles=leg1, loc="upper left", fontsize=9, framealpha=0.9)
ax.add_artist(l1)
ax.legend(handles=style_leg, loc="lower right", fontsize=9, framealpha=0.9)

fig.tight_layout()
out = BENCH / "scalability.svg"
fig.savefig(out, format="svg")
print("SVG:", out)
