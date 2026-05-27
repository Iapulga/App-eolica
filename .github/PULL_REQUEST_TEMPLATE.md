## Resumen
<!-- Descripción breve del cambio. ¿Qué hace y por qué? -->

## Tipo de cambio
- [ ] Bugfix (cambio no rompe API y arregla un problema)
- [ ] Feature (cambio no rompe API y añade funcionalidad)
- [ ] Breaking change (cambio que rompe compatibilidad con escenarios o reportes guardados)
- [ ] Documentación
- [ ] Refactor / limpieza interna (sin cambio funcional visible)
- [ ] Tests / infra (CI, pre-commit, etc.)

## Issue relacionado
Closes #

## Cambios principales
- 
- 
- 

## ¿Cómo se probó?
- [ ] `pytest tests/ -v` pasa local
- [ ] `ruff check .` y `ruff format --check .` pasan
- [ ] Probado manualmente en la app (`streamlit run Inicio.py`) — describir flujo:
- [ ] Benchmarks no se degradan (si aplica): `python benchmarks/run_all.py`

## Compatibilidad
- [ ] No rompe escenarios guardados en `park_scenarios` ni `saved_projects`
- [ ] Si rompe: incluida migración en `db.py`
- [ ] Documentado en `CHANGELOG.md` bajo `[Unreleased]`

## Checklist
- [ ] El código sigue el estilo del proyecto (ruff configurado en `pyproject.toml`)
- [ ] Docstrings y comentarios añadidos donde el porqué no es obvio
- [ ] Tests nuevos cubren el cambio (si aplica)
- [ ] Documentación actualizada (README / docs / docstrings)
