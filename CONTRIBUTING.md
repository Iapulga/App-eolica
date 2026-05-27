# Contribuir a SMA 2.0

¡Gracias por interesarte en SMA 2.0! Este proyecto es open-source bajo licencia MIT y se desarrolla principalmente en español. Toda contribución es bienvenida: bugs, ideas, código, documentación, traducciones, benchmarks o casos de uso.

## Tabla de contenidos
- [Código de conducta](#código-de-conducta)
- [Cómo reportar un bug](#cómo-reportar-un-bug)
- [Cómo proponer una mejora](#cómo-proponer-una-mejora)
- [Setup de desarrollo](#setup-de-desarrollo)
- [Flujo de trabajo (branches y commits)](#flujo-de-trabajo)
- [Estilo de código](#estilo-de-código)
- [Tests](#tests)
- [Pull requests](#pull-requests)
- [Áreas con alto impacto](#áreas-con-alto-impacto)

---

## Código de conducta

Este proyecto adhiere al [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). Al participar se espera que respetes este código.

---

## Cómo reportar un bug

1. Verifica que no exista un issue similar en [Issues](https://github.com/alandavidgomezmaestre/sma2/issues).
2. Abre uno nuevo usando la plantilla **Bug report**.
3. Incluye traceback completo, SO, versión de Python, y pasos reproducibles.

## Cómo proponer una mejora

1. Abre un issue con la plantilla **Feature request**.
2. Explica el problema que resuelve y enlaza referencias (papers, normas IEC/ISO, documentación de herramientas comparables).
3. Espera feedback antes de implementar — algunas ideas pueden estar fuera del alcance o duplicadas.

---

## Setup de desarrollo

Requisitos: Python 3.11 o 3.12, git.

```bash
git clone https://github.com/alandavidgomezmaestre/sma2.git
cd sma2

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements-dev.txt

# Extras opcionales (instala según lo que toques)
pip install pvlib                  # solar / shadow flicker
pip install elevation rasterio     # DEM / GIS
pip install py_wake                # FASE 2 (motor de estela avanzado)

# Hooks pre-commit
pre-commit install

# Levantar la app
streamlit run Inicio.py
```

La app crea automáticamente la BD SQLite en `app_eolica.db` la primera vez.

---

## Flujo de trabajo

### Branches
- `main`: rama estable. Solo merges aprobados vía PR.
- `feature/<descripcion-corta>`: nueva funcionalidad.
- `fix/<descripcion-corta>`: arreglo de bug.
- `docs/<descripcion-corta>`: solo documentación.
- `refactor/<descripcion-corta>`: refactor interno sin cambio funcional.

### Commits (Conventional Commits)

Formato: `<tipo>(<scope opcional>): <resumen en imperativo>`

Tipos principales:
- `feat`: nueva funcionalidad
- `fix`: bugfix
- `docs`: documentación
- `style`: formato/estilo sin cambio de lógica
- `refactor`: cambio interno sin afectar comportamiento
- `test`: agregar/corregir tests
- `chore`: tareas de mantenimiento (deps, build, CI)
- `perf`: mejora de rendimiento

Ejemplos:
```
feat(wake): integrar PyWake como motor principal con fallback Jensen
fix(fase5): corregir cálculo LCOE cuando OPEX es cero
docs(readme): añadir badges y sección de validación
test(calculos): añadir tests roundtrip Weibull k,c
```

Para commits con cambios extensos, añadir un cuerpo explicando el porqué.

---

## Estilo de código

- **Ruff** se encarga del linting y formato. Configuración en `pyproject.toml`.
- Antes de commitear: `ruff check . && ruff format .`
- Type hints donde aporten claridad — no es obligatorio en todo el código.
- Docstrings: estilo Google o NumPy. Solo donde el "por qué" no sea obvio.
- Comentarios: explicar **por qué**, no **qué**. El código bien nombrado explica el qué.
- Idioma del código: nombres de funciones/clases en **español** (consistente con el resto del proyecto); strings de UI en **español**. Comentarios pueden ser español o inglés.

---

## Tests

```bash
# Todos
pytest tests/ -v

# Con coverage
pytest tests/ --cov=. --cov-report=html
# Abrir htmlcov/index.html

# Solo rápidos (excluir slow / requires_*)
pytest tests/ -m "not slow and not requires_gis"
```

Markers disponibles (definidos en `pyproject.toml`):
- `slow`: tests >5s
- `requires_gis`: necesita `elevation` + `rasterio`
- `requires_pvlib`: necesita `pvlib`
- `requires_pywake`: necesita `py_wake`
- `integration`: tests multi-módulo end-to-end

Si añades una funcionalidad, **acompáñala de tests**. La meta del proyecto es ≥60% de coverage sobre los módulos de cálculo (`calculos.py`, `calculos_energia.py`, `calculos_economicos.py`, `db.py`).

---

## Pull requests

1. Crea tu branch desde `main` actualizado: `git switch -c feature/mi-cambio`
2. Haz commits siguiendo Conventional Commits.
3. Asegúrate de que pasan: `pytest`, `ruff check`, `ruff format --check`.
4. Actualiza `CHANGELOG.md` bajo `## [Unreleased]`.
5. Abre el PR usando la plantilla. Vincula el issue con `Closes #N`.
6. CI debe estar en verde antes del merge.
7. Sé paciente con las revisiones — somos pocos maintainers.

---

## Áreas con alto impacto

Si buscas dónde empezar, estas áreas están abiertas y bien delimitadas:

- **Tests** — cualquier módulo sin cobertura. Ver [Issue label `good-first-issue`](https://github.com/alandavidgomezmaestre/sma2/labels/good-first-issue).
- **Benchmarks** — añadir sitios open-data (Sexbierum, Tjæreborg, sitios IEA Wakebench).
- **Modelos de estela** — integrar más modelos de PyWake o validar contra papers.
- **Reportes** — mejorar plantillas DOCX/PDF, añadir formatos (HTML standalone, Markdown).
- **Documentación** — tutoriales por fase, casos de estudio, comparativas con herramientas comerciales.
- **i18n** del catálogo de países en `i18n_paises.py` — añadir nuevos países y normativas de ruido/flicker.
- **Validación SCADA** — extender `validacion_scada.py` con más métricas IEC 61400-12-1.

---

## Preguntas

- Issues con la label `question`
- GitHub Discussions (habilitado a partir de v1.0)
- Discord (próximamente, ver README)

¡Gracias por contribuir!
