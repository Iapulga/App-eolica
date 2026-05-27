# SMA 2.0 — Wind Project Analyzer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/built%20with-streamlit-FF4B4B.svg)](https://streamlit.io/)
[![CI](https://github.com/alandavidgomezmaestre/sma2/actions/workflows/ci.yml/badge.svg)](https://github.com/alandavidgomezmaestre/sma2/actions/workflows/ci.yml)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)

> Aplicación open-source en español para el análisis integral de parques eólicos:
> recurso de viento, AEP, estelas, pérdidas IEC 61400-15-2, evaluación económica
> (LCOE / NPV / IRR) y generación de reportes técnicos.

SMA 2.0 es una alternativa libre y gratuita a herramientas comerciales como WindPRO, WAsP u OpenWind, orientada a:

- **Consultoría e ingeniería de viento** en LatAm y España (pre-screening, pre-DD).
- **Académico y docencia** — código auditable, fórmulas explícitas, sin caja negra.
- **Proyectos pequeños y medianos** donde una licencia comercial de varios miles de euros no se justifica.

---

## Tabla de contenidos
- [Características](#características)
- [Instalación](#instalación)
- [Inicio rápido](#inicio-rápido)
- [Flujo de las 6 fases](#flujo-de-las-6-fases)
- [Módulos avanzados](#módulos-avanzados)
- [Comparativa vs WindPRO / WAsP / OpenWind](#comparativa-vs-herramientas-comerciales)
- [Validación científica](#validación-científica)
- [Roadmap](#roadmap)
- [Contribuir](#contribuir)
- [Licencia y créditos](#licencia-y-créditos)

---

## Características

### Núcleo técnico
- Lectura de datos NASA POWER (online o CSV/JSON) y torres meteorológicas (10-min CSV/Excel).
- Perfil de viento: exponencial, logarítmico, Log-A 2 puntos, promedio Log-Exp.
- MCP (Measure-Correlate-Predict) lineal global y sectorial.
- Ajuste **Weibull** y **Rayleigh** sectorial sobre 16 sectores.
- Corrección automática de densidad ρ(z, T).
- Validación de clase IEC 61400-1 (TI, V_avg, V_50yr).
- Modelo de estela Jensen sectorial (próximamente: PyWake con NOJ / Bastankhah / TurbOPark / Larsen / Fuga).
- **AEP bruto y neto** + Monte Carlo P50 / P75 / P90 / P99.
- Evaluación económica: CAPEX/OPEX, **LCOE descontado**, NPV, IRR (Newton-Raphson), payback, bankable con DSCR y WACC, soporte multi-moneda (14 monedas).

### Reportes
- DOCX bankable, PDF técnico, LaTeX (fallback), KML/GeoJSON (Google Earth, QGIS), CSV de coordenadas, ZIP de paquete completo.
- Manifiestos ambientales: ruido, sombras, aves, regulación CREG (Colombia) y equivalentes por país.

### Persistencia
- SQLite local con backups rotativos automáticos.
- Múltiples proyectos guardados, exportables como JSON portátil.

---

## Instalación

### Opción 1 — Desde fuente (recomendada para desarrollo)

Requisitos: **Python 3.11 o 3.12**, git.

```bash
git clone https://github.com/alandavidgomezmaestre/sma2.git
cd sma2

python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
streamlit run Inicio.py
```

La app abre en `http://localhost:8501`.

### Extras opcionales

```bash
pip install pvlib                  # Shadow flicker, planta híbrida solar
pip install elevation rasterio     # Descarga de DEM (SRTM) y análisis de terreno
pip install shapely pyproj         # Polígonos de concesión, proyecciones
pip install py_wake                # Modelos avanzados de estela (Bastankhah, TurbOPark, ...)
pip install folium streamlit-folium  # Mapa interactivo
```

O todo de una vez:

```bash
pip install -e ".[gis,solar,pywake,mapviewer]"
```

### Opción 2 — Binario Windows (.exe)

Disponible a partir de la release v1.0. Ver [Releases](https://github.com/alandavidgomezmaestre/sma2/releases).

---

## Inicio rápido

1. Ejecutar `streamlit run Inicio.py`.
2. En **Inicio**, hacer clic en *"Cargar proyecto demo"* (próximamente — por ahora, configurar manualmente).
3. Recorrer las fases:
   - **Fase 1**: subir o construir la curva de potencia.
   - **Fase 2**: cargar datos NASA POWER o un CSV, extrapolar a altura de buje.
   - **Fase 3**: ajustar Weibull/Rayleigh por sector.
   - **Fase 4**: definir el layout y calcular pérdidas por estela.
   - **Fase 5**: aplicar pérdidas detalladas, calcular AEP neto, LCOE y financiero.
   - **Fase 6**: exportar reportes DOCX/PDF/KML.

---

## Flujo de las 6 fases

| Fase | Objetivo | Entrada | Salida principal |
|------|----------|---------|------------------|
| **1 — Aerogenerador** | Definir curva de potencia y datos del modelo | CSV / formulario | Curva (v, P), C_p, diámetro, h_buje |
| **2 — Perfiles de viento** | Procesar el recurso y extrapolar a altura de buje | NASA POWER / torre met / GWA | Series corregidas, α, MCP |
| **3 — Rosa y velocidad** | Caracterizar el recurso por sector | Salida de F2 | Rosa 16 sectores, k & c por sector |
| **4 — Estelas y arreglo** | Definir layout y calcular pérdidas por estela | Posiciones X/Y, modelo de estela | Pérdida por sector, AEP por turbina |
| **5 — AEP bruta y neta** | Aplicar pérdidas y calcular economía | Pérdidas + CAPEX/OPEX + tasa | AEP P50–P99, LCOE, NPV, IRR |
| **6 — Exportar y guardar** | Generar reportes y persistir el proyecto | Configuración del país, autor | DOCX, PDF, KML, JSON proyecto |

---

## Módulos avanzados

Más allá de las 6 fases, SMA 2.0 incluye módulos especializados activables desde las fases correspondientes:

| Módulo | Archivo | Propósito |
|--------|---------|-----------|
| Ruido ISO 9613-2 | `ruido_iso9613.py` | Propagación sonora, LpA por receptor |
| Shadow flicker | `shadow_flicker.py` | Horas anuales de parpadeo de sombras |
| Colisión de aves | `bird_collision_band.py` | Modelo Band 2007 |
| Cold climate / icing | `cold_climate.py` | Derate por horas de hielo (IEA Task 19) |
| Planta híbrida | `hybrid_plant.py` | Combinación viento + solar + (futuro) BESS |
| Optimizador de layout | `layout_optimizer.py` | Differential Evolution con restricciones |
| Curtailment de red | `grid_curtailment.py` | Pérdidas técnicas/económicas por restricción |
| LCA / huella de carbono | `lca_carbon.py` | gCO₂eq/kWh ciclo de vida (ISO 14040) |
| Linear flow (Jackson-Hunt) | `linear_flow_model.py` | Speedup sobre colinas suaves |
| Pre-audit checklist | `pre_audit_checklist.py` | Scoring DNV-style de calidad del análisis |
| Repotenciación | `repowering_analysis.py` | Comparativa decommission vs repower vs life extension |
| Validación SCADA | `validacion_scada.py` | Filtros IEC 61400-12-1 sobre datos reales |
| GIS / DEM | `gis_helpers.py` | Descarga SRTM, rugosidad IGBP |
| Perfiles de país | `i18n_paises.py` | Límites legales y financieros por país (CO/MX/BR/CL/AR/PE/US/EU/JP/CN/IN/ZA/AU) |

Wrappers (requieren binario externo instalado):
- `cfd_openfoam_wrapper.py` — OpenFOAM (CFD RANS)
- `windninja_wrapper.py` — WindNinja (mass-consistent)

---

## Comparativa vs herramientas comerciales

| Capacidad | SMA 2.0 (gratis) | WindPRO | WAsP | OpenWind |
|-----------|:----------------:|:-------:|:----:|:--------:|
| Licencia | **MIT, gratis** | Comercial (€) | Comercial (€) | Free + Enterprise |
| Idioma UI | **Español** | Inglés | Inglés | Inglés |
| Web / multi-PC | **✅** | Desktop | Desktop | Desktop |
| Weibull/Rayleigh 16 sectores | ✅ | ✅ | ✅ | ✅ |
| MCP | Lineal global+sectorial | Matrix + Neural + Wbl | Sí | Sí |
| Wake Jensen | ✅ | ✅ (Park2) | ✅ | ✅ |
| Wake Bastankhah / TurbOPark / Larsen | 🛠 vía PyWake (planeado FASE 2) | ✅ | ✅ | ✅ |
| AEP P50–P99 | ✅ | ✅ | ✅ | ✅ |
| LCOE / NPV / IRR | **✅ integrado** | ✅ módulo | ❌ | ⚠ básico |
| Ruido ISO 9613 / Shadow flicker | ✅ | ✅ (DECIBEL/SHADOW) | ❌ | ⚠ |
| Layout optimizer | ✅ (scipy DE) | ✅ (Optimize) | ❌ | ✅ |
| Map viewer interactivo | 🛠 (planeado FASE 7) | ✅ | ✅ | ✅ |
| Reportes DOCX/PDF | ✅ | ✅ | ⚠ | ⚠ |
| Validación bancaria (DNV / IEC 61400-15-2) | 🛠 (planeado FASE 4) | ✅ | ✅ | ⚠ |
| Soporte oficial | Comunidad | Hotline + cursos | Hotline + cursos | Comunidad + Enterprise |

Honestidad: SMA 2.0 cubre ~70-80 % del flujo conceptual de WindPRO. Para proyectos bancables grandes (>50 MW) con due diligence formal sigue siendo recomendable validar con herramientas certificadas. Para pre-screening, académico, repotenciación rápida o consultoría en mercados sensibles a precio, SMA 2.0 es viable.

---

## Validación científica

> **Estado actual:** validación interna en curso (FASE 3 del roadmap).

La calidad científica se valida contra sitios open-data conocidos:
- **Horns Rev 1** (Vestas V80 × 80, datos Hansen 2012)
- **Lillgrund** (SWT-2.3-93 × 48, Dahlberg 2009)
- **IEA Wind Task 31 / Wakebench** (Tjæreborg, Sexbierum)

Cuando esté disponible, se publicará `benchmarks/report.html` con los resultados.

---

## Roadmap

Plan completo en [docs](docs/) (FASE 12 del roadmap). Resumen:

- ✅ **v0.9** (actual) — núcleo funcional + 16 módulos de dominio
- 🛠 **v1.0** — Foundation OS, tests ≥60 %, PyWake integrado, benchmarks, docs Sphinx, release público
- 🔜 **v1.1** — Loss catalogue IEC 61400-15-2, sensitivity tornado UI, layout variants
- 🔜 **v1.2** — Map viewer interactivo, MCP avanzado (matrix/neural), site compliance por turbina
- 🔮 **v2.0** — CFD nativo, offshore, fotomontaje

Ver `ROADMAP.md` y los issues con label `roadmap-v*`.

---

## Contribuir

¡Las contribuciones son muy bienvenidas! Lee [`CONTRIBUTING.md`](CONTRIBUTING.md) para:

- Configurar el entorno de desarrollo
- Convenciones de branches y commits (Conventional Commits)
- Cómo correr tests y linting
- Áreas con alto impacto donde se necesita ayuda

Issues abiertos con la label [`good-first-issue`](https://github.com/alandavidgomezmaestre/sma2/labels/good-first-issue) son un buen punto de partida.

---

## Licencia y créditos

**Licencia:** MIT — ver [LICENSE](LICENSE). Uso comercial permitido sin obligación de re-publicar.

**Autor original:** Alan David Gómez Maestre.

**Construido sobre el trabajo de:**
- [Streamlit](https://streamlit.io/) — framework UI
- [Plotly](https://plotly.com/python/) — gráficos interactivos
- [pvlib](https://pvlib-python.readthedocs.io/) — posición solar (shadow flicker)
- [PyWake](https://topfarm.pages.windenergy.dtu.dk/PyWake/) (DTU) — motor de estela avanzado (próxima integración)
- [NumPy](https://numpy.org/), [pandas](https://pandas.pydata.org/), [SciPy](https://scipy.org/) — núcleo numérico
- NASA POWER — datos meteorológicos globales gratuitos

**Citar este software:** ver [`CITATION.cff`](CITATION.cff).

---

<sub>Si SMA 2.0 te resulta útil, considera dejar una ⭐ en el repositorio.</sub>
