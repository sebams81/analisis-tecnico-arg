# Análisis técnico de acciones argentinas

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21288495.svg)](https://doi.org/10.5281/zenodo.21288495)

Plataforma de análisis técnico con señales, gráficos interactivos y eventos
fundamentales sobre **13 acciones líderes del panel BYMA**, en dos universos:
la serie local en pesos y una serie sintética en dólares MEP construida por
arbitraje AL30/AL30D. En total, **26 series**.

**Sitio publicado:** https://sebams81.github.io/analisis-tecnico-arg/

Repositorio de apoyo al Trabajo Final de la Licenciatura en Gestión de
Tecnología Informática (UAI, 2026).

## Estado congelado y reproducibilidad

El estado que respalda los resultados del trabajo está etiquetado como
`v1.1-tf` (commit `7cb8d13`) y archivado en Zenodo con DOI permanente.
La rama `main` diverge de ese tag por las corridas diarias automáticas: la
verificación opera sobre el tag, no sobre `main`.

```bash
git clone https://github.com/sebams81/analisis-tecnico-arg.git
cd analisis-tecnico-arg
git config core.autocrlf true   # materialización CRLF, la del digest sellado
git checkout v1.1-tf
git ls-files data_raw | LC_ALL=C sort | xargs sha256sum | sha256sum
```

| Materialización | Digest esperado de `data_raw/` (29 archivos) |
|---|---|
| CRLF (`autocrlf=true`) | `46d5f326d4caf6cee4dd0e1fb7171093c2502146a94c58b0643b9425b6f46988` |
| LF (`autocrlf=false`) | `b45c463abdf3bb04528f5815364fbcd6165f2782b51c48c74578d3e5da3fbc91` |

El repositorio no incluye `.gitattributes`, de modo que la conversión de fin
de línea la determina la configuración de quien clona. Ambos digests
corresponden a idénticos objetos en la base de Git.

El protocolo completo está en el Anexo III del trabajo.

## Estructura del repositorio
