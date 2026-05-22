# Cómo compilar la app a `.exe`

## Opción 1 — Doble click (más fácil)

Doble click en **`build.bat`**.

Espera 2-3 min. Cuando termine, el `.exe` está en:
```
dist/Alfa App/Alfa App.exe
```

## Opción 2 — Terminal (un solo comando)

Abre PowerShell / CMD en la carpeta del proyecto y ejecuta:

```bash
python build_exe.py
```

o más corto (con doble-click bat):

```bash
build
```

## Qué hace automáticamente

1. Instala PyInstaller si falta
2. Mata procesos `Alfa App.exe` previos (libera archivos bloqueados)
3. Borra `dist/` y `build/` viejas
4. Compila con `AppEolica.spec` (incluye assets, mapas, gráficos, BD, metadata)
5. Verifica que el `.exe` exista

## Archivos clave (no borrar)

| Archivo | Para qué |
|---|---|
| `AppEolica.spec` | Config PyInstaller (qué incluir) |
| `build_exe.py` | Script Python de compilación |
| `build.bat` | Atajo Windows (doble click) |
| `launcher.py` | Entry point del `.exe` |

## Distribución del `.exe`

Copia la carpeta completa **`dist/Alfa App/`** (no solo el `.exe`).
Contiene:
- `Alfa App.exe`
- `_internal/` (todas las dependencias)

En cualquier PC Windows, doble click → arranca → abre browser en `http://127.0.0.1:8501`.

## Problemas comunes

| Error | Solución |
|---|---|
| `Permission denied` borrando `dist/` | Cierra el `.exe` antes de recompilar |
| `No package metadata was found` | Spec ya tiene `copy_metadata()` — verifica `AppEolica.spec` |
| Antivirus bloquea | UPX desactivado en spec — añade exclusión en antivirus |
| Mapas/gráficos no cargan | Verifica `assets/`, `pages/`, `reportes/` no se borraron |
