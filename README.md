# Análisis técnico de acciones argentinas

Plataforma de análisis técnico con señales, gráficos interactivos y eventos fundamentales para 12 acciones líderes del panel BYMA (versión local en pesos y sintético MEP en dólares vía arbitraje AL30/AL30D).

**Sitio publicado:** https://sebams81.github.io/analisis-tecnico-arg/

## Estructura del repositorio

```
src/
  ingestion/        # data_downloader.py — extracción desde API PPI
  processing/       # data_normalizer.py, synthetic_mep_generator.py
  analysis/         # indicator_engine.py, signal_generator.py, backtester.py
  web/              # json_generator.py — serializa JSONs para el frontend
  config/           # study_config.py, logging_conf.py

docs/               # GitHub Pages (frontend estático)
  data/             # JSONs consumidos por la web
  vendor/           # Lightweight Charts v5.2 (bundle local)

data_raw/csv/                       # OHLCV crudo por instrumento (seed commiteado)
data_public/backtests/              # snapshot académico (solo summary_all_tickers.csv commiteado)
data_fundamentals/fundamentals.json # eventos curados manualmente

.github/workflows/  # automatización CI/CD
```

## Automatización

El pipeline corre automáticamente vía GitHub Actions:

- **Cuándo:** lunes a viernes a las **18:00 ART** (21:00 UTC), con 60 min de margen tras el cierre de rueda BYMA (17:00 ART).
- **Trigger manual:** Actions tab → "Daily pipeline" → "Run workflow" para forzar una corrida fuera de schedule.
- **Credenciales:** `PPI_PUBLIC_KEY` y `PPI_PRIVATE_KEY` se cargan desde GitHub Secrets — nunca aparecen en el repo ni en los logs (las enmascara GitHub automáticamente).
- **Qué se commitea automáticamente:**
  - `data_raw/csv/*.csv` — OHLCV crudo (necesario para que el incremental del downloader funcione en la próxima corrida).
  - `docs/data/*.json` — datos consumidos por el frontend.
  - `data_public/backtests/summary_all_tickers.csv` — snapshot académico de métricas.
- **Skip de commits vacíos:** si los outputs no cambiaron respecto a `main` (ej. fin de semana, feriado), el workflow termina en verde sin crear commits.
- **Mensaje de commit:** `automation: actualización del pipeline YYYY-MM-DD` (fecha UTC), firmado por `github-actions[bot]`.
- **Despliegue:** GitHub Pages detecta el push a `main` y re-deploya el frontend en ~1-3 minutos.

Workflow definido en [.github/workflows/daily-pipeline.yml](.github/workflows/daily-pipeline.yml).

## Desarrollo local

```bash
# Setup
pip install -r requirements.txt

# Credenciales PPI (crear .env en raíz)
echo 'PPI_PUBLIC_KEY=...' >> .env
echo 'PPI_PRIVATE_KEY=...' >> .env

# Correr el pipeline completo
python -m src.ingestion.data_downloader
python -m src.processing.data_normalizer
python -m src.processing.synthetic_mep_generator
python -m src.analysis.indicator_engine
python -m src.analysis.signal_generator
python -m src.analysis.backtester
python -m src.web.json_generator

# Servir el frontend
cd docs && python -m http.server 8765
# → http://localhost:8765
```

## Stack técnico

- **Pipeline:** Python 3.11, pandas, numpy, ppi-client.
- **Frontend:** vanilla HTML/CSS/JS, sin build step. Lightweight Charts v5 servido como bundle local.
- **Hosting:** GitHub Pages desde `docs/` en branch `main`.
- **Automatización:** GitHub Actions con cron lun-vie.
