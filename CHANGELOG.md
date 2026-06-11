# Changelog

Todos los cambios notables de SMA 2.0 se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Añadido
- **Fase 6 · Estudios avanzados** (`pages/6_Fase_6_Estudios_avanzados.py`): nueva fase que
  cablea a la UI los 13 módulos de cálculo que existían sin interfaz — IEC 61400-1 site
  suitability, flujo lineal sobre terreno (Jackson-Hunt), clima frío/icing, ruido ISO 9613-2,
  shadow flicker, colisión de aves (Band 2007), huella de carbono LCA, validación SCADA,
  curtailment de red, planta híbrida viento+solar+BESS, optimizador de layout (Differential
  Evolution), análisis de fin de vida (repowering) y pre-audit checklist DNV-style.
- El `.exe` vuelve a incluir `scipy` (requerido por el optimizador de layout, el ajuste
  Gumbel y las estadísticas del reporte bankable).

### Cambiado
- La fase de exportaciones pasa de **Fase 6 a Fase 7** (`pages/7_Fase_7_Exportar_y_guardar.py`);
  sus claves persistidas `f6_*` migran automáticamente a `f7_*` (migración de esquema v3,
  también al restaurar proyectos guardados con la numeración anterior).
- Estructura open-source: `LICENSE` (MIT), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`, `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`.
- Workflow CI de GitHub Actions (lint + tests sobre Python 3.11 y 3.12).
- Plantillas de issue y pull request.
- Configuración `pre-commit` (ruff + higiene básica).

### Cambiado
- `README.md` reorganizado como documento público (instalación, demo, créditos).
- `.gitignore` ampliado con artefactos de tests, coverage y docs.

### Arreglado
- **F4** — el input "Número de aerogeneradores" quedaba desincronizado con la tabla
  editable cuando el layout real tenía un número distinto al guardado en `config`.
  Ahora se siembra desde `len(cargar_layout_parque())` cuando el layout existe
  ([pages/4_Fase_4_Estelas_y_arreglo.py](pages/4_Fase_4_Estelas_y_arreglo.py)).
- **F4** — `db.py` ya no usa `np.nan` sin importar `numpy` en
  `guardar_nasa_hourly` (bug F821 latente).
- **F2** — `pages/2_Fase_2_Perfiles_de_viento.py` ahora importa `datetime` antes
  de usar `datetime.date(...)` en los defaults de Global Wind Atlas.
- **F6** — cuando los resultados existen en BD pero la sesión de Streamlit
  no tiene `runtime_context` (p. ej. tras refresco de página), se muestra un
  botón directo "Ir a Fase 5 y activar exportaciones" con `st.switch_page`,
  en lugar de un warning pasivo. Mejora UX del flujo cargar-proyecto → exportar.
- **reportes/manifiestos.py** — eliminadas 3 líneas de código muerto tras un
  `return` en `build_informe_tecnico_model`.

### Conocido (a tratar en FASE 1 del roadmap)
- Si el usuario refresca F6 o navega vía URL directa (no sidebar), Streamlit
  pierde `runtime_context` y los botones de exportación quedan inactivos hasta
  reejecutar F5. Solución planeada: extraer el pipeline de cálculo de F5 a una
  función reutilizable y rehidratar `runtime_context` desde `config` automáticamente.

---

## [0.9.0] — 2026-05-26

Estado inicial pre-release antes de la apertura del repositorio.

### Características principales
- 6 fases de cálculo: aerogenerador, perfiles de viento, rosa de vientos, estelas/arreglo, AEP bruta/neta, exportación.
- Ajuste Weibull/Rayleigh sectorial (16 sectores).
- Perfiles log/exponencial/promedio Log-Exp, MCP lineal global y sectorial.
- Validación IEC 61400-1 (clase del sitio).
- Modelo de estela Jensen (16 direcciones).
- Monte Carlo P50/P75/P90/P99 sobre AEP.
- Análisis económico: LCOE, NPV, IRR, payback, bankable DSCR/WACC.
- Reportes en DOCX, PDF, LaTeX, KML/GeoJSON.
- 16 módulos de dominio: ruido ISO 9613-2, shadow flicker, colisión aves (Band 2007),
  cold climate, hybrid plant, layout optimizer, grid curtailment, LCA carbon, etc.
- Persistencia SQLite con backups rotativos.
