# Cómo compilar la app a `.exe`

## Opción 1 — Doble click (más fácil)

Doble click en **`build.bat`**.

Espera varios minutos. Cuando termine, el `.exe` está en:
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
4. Compila con `AppEolica.spec` (incluye código, páginas, assets, reportes,
   dependencias de exportación y Qt WebEngine)
5. Verifica que el `.exe` exista

## Archivos clave (no borrar)

| Archivo | Para qué |
|---|---|
| `AppEolica.spec` | Config PyInstaller (qué incluir) |
| `build_exe.py` | Script Python de compilación |
| `build.bat` | Atajo Windows (doble click) |
| `desktop_shell.py` | Entry point de la ventana nativa |
| `launcher.py` | Servidor Streamlit del proceso hijo |

## Distribución del `.exe`

Copia la carpeta completa **`dist/Alfa App/`** (no solo el `.exe`).
Contiene:
- `Alfa App.exe`
- `_internal/` (todas las dependencias)

En cualquier PC Windows, copia la carpeta completa y haz doble click en `Alfa App.exe`.
La aplicación abre una ventana nativa con Qt WebEngine; el servidor local usa
`http://127.0.0.1:8501` internamente.

La base de datos no se distribuye dentro del bundle. En modo `.exe` se crea y
guarda en `%LOCALAPPDATA%\AppEolica\app_eolica.db`, para que cada usuario tenga
sus propios proyectos y la carpeta de instalación no necesite permisos de escritura.
Si necesitas trasladar proyectos existentes, copia tu `app_eolica.db` a esa ruta
antes de iniciar la aplicación.

El bundle puede ocupar alrededor de 1 GB porque incluye Qt WebEngine, librerías
numéricas, mapas y exportación de informes. Es normal: distribuye siempre la
carpeta completa, no solo el archivo `.exe`.

## Problemas comunes

| Error | Solución |
|---|---|
| `Permission denied` borrando `dist/` | Cierra el `.exe` antes de recompilar |
| `No package metadata was found` | Spec ya tiene `copy_metadata()` — verifica `AppEolica.spec` |
| Antivirus bloquea | UPX desactivado en spec — añade exclusión en antivirus |
| Mapas/gráficos no cargan | Verifica `assets/`, `pages/`, `reportes/` no se borraron |
| La app no inicia | Cierra otra instancia de Alfa App o un servidor de desarrollo que use el puerto 8501 |
