# PERSISTENCIA_AUDIT_REPORT.md

# Reporte de Auditoría Técnica - Alfa App (SMA 2.0)

**Fecha:** 13 de Mayo de 2026  
**Estado:** Finalizado  
**Modo:** SOLO LECTURA (No se modificó ningún archivo)

## 1. Resumen Ejecutivo
Se realizó una auditoría técnica profunda de los 10 archivos core de la aplicación Alfa App. La estructura general es sólida y modular, pero existen riesgos acumulados en el manejo de codificación de caracteres, redundancia de constantes y una gestión de `session_state` que, aunque está siendo mejorada con `widget_helpers.py`, todavía presenta accesos directos que podrían causar inconsistencias en reruns complejos.

---

## 2. Hallazgos Críticos y Riesgos

### A. Errores de Sintaxis y Compilación
*   **Resultado:** **0 errores encontrados.**
*   **Verificación:** Ejecutado `python -m py_compile` sobre todos los archivos objetivo. Todos compilaron correctamente.

### B. Dependencias Circulares y Acoplamiento
*   **Hallazgo:** Existe un acoplamiento fuerte entre `db.py`, `calculos.py` y los módulos de `reportes`. 
*   **Riesgo:** Para evitar dependencias circulares a nivel de módulo, se utilizan imports dentro de funciones (ej. en `widget_helpers.py` e `informe_tecnico.py`). Aunque es una solución válida en Python, dificulta el rastreo de dependencias y el testing unitario.
*   **Recomendación:** Mover constantes compartidas (como `ROUGHNESS_OPTIONS`) a un archivo `constants.py` o `config.py` independiente.

### C. Inconsistencias de Codificación y Nombres (Encoding)
*   **Hallazgo:** Múltiples archivos (`calculos_energia.py`, `informe_tecnico.py`, `calculos.py`) contienen "hacks" para manejar caracteres especiales (ej. `z0 teÃ³rica`, `Direcci?n`, `CÃ©sped`).
*   **Riesgo:** Si el entorno de ejecución cambia de Windows (CP1252/UTF-8) a Linux (UTF-8 puro), estos strings podrían romperse o fallar en las comparaciones de columnas de DataFrames.
*   **Prioridad:** ALTA.

### D. Inconsistencia de Unidades
*   **Hallazgo:** 
    *   `db.py` / Fase 1: Almacena `Potencia_W` (Vatios).
    *   `calculos_energia.py`: Usa `W` para potencia media y convierte a `MWh` para AEP.
    *   `calculos_economicos.py`: Convierte `W` a `MW` dividiendo por `1e6`.
    *   `reportes/fase5_export_helpers.py`: Muestra `kW` dividiendo por `1000`.
*   **Riesgo:** Aunque los cálculos parecen correctos, la dispersión de factores de conversión (`1e3`, `1e6`, `/1000.0`) en diferentes archivos aumenta la probabilidad de error humano en futuras actualizaciones.
*   **Prioridad:** MEDIA.

### E. Deuda Técnica y Código Muerto
*   **Hallazgo:**
    *   `db.py`: La función `tabla_vacia_curva` está definida dos veces (Línea 131 y 147).
    *   `calculos.py`: Bloques de código comentados en el modelo de estelas de Jensen y lógica de interpolación.
    *   `normalize_base_viento_for_energy`: Contiene mapeos para nombres de modelos que ya no existen o están mal codificados.

---

## 3. Matriz de Hallazgos Detallada

| ID | Archivo | Hallazgo | Tipo | Prioridad |
| :--- | :--- | :--- | :--- | :--- |
| AUD-01 | `db.py` | Función `tabla_vacia_curva` duplicada. | Deuda Técnica | BAJA |
| AUD-02 | `calculos.py` | `ROUGHNESS_OPTIONS` duplicado en `informe_tecnico.py`. | Redundancia | MEDIA |
| AUD-03 | `reportes/informe_tecnico.py` | Hardcoding de nombres de columnas con errores de encoding (`Direcci?n`). | Riesgo de Datos | ALTA |
| AUD-04 | `widget_helpers.py` | Imports de `db` dentro de funciones. | Arquitectura | BAJA |
| AUD-05 | `calculos_economicos.py` | Petición de red externa a `open.er-api.com` sin fallback local robusto. | Riesgo Operativo | MEDIA |
| AUD-06 | `calculos_energia.py` | Normalización de nombres de modelos con caracteres rotos. | Deuda Técnica | MEDIA |
| AUD-07 | `db.py` | `init_db` usa concatenación de strings para SQL (aunque con valores internos). | Seguridad | BAJA |
| AUD-08 | `Inicio.py` | CSS embebido masivo (500+ líneas) dificulta mantenimiento. | UI/UX | BAJA |

---

## 4. Riesgos Específicos de Lógica

### Cálculos de Energía (AEP)
*   **Interpolación:** La función `interpolar_potencia_curva_preparada` asume que la curva está ordenada. Si un usuario carga una curva desordenada, el resultado de `np.interp` será erróneo.
*   **Estelas:** El modelo de Jensen es sensible a la resolución de la rosa de vientos. Se usa una rosa de 16 sectores; para parques muy grandes, esto puede subestimar pérdidas si no se aumenta la resolución.

### Base de Datos
*   **Concurrencia:** No se detectó el uso de `WAL mode` en SQLite. En Streamlit, múltiples usuarios o reruns rápidos pueden causar `database is locked`.

### Exportaciones
*   **Excel:** Se usa `openpyxl` directamente. Si el DataFrame es muy grande, el consumo de memoria puede dispararse.
*   **Word:** La dependencia de un "Master Docx" (`master_docx_bytes`) es un punto de fallo si el archivo subido no sigue exactamente la estructura esperada de bookmarks/estilos.

---

## 5. Recomendaciones de Acción (Roadmap)

1.  **Inmediato (Limpieza):**
    *   Eliminar duplicidad de `tabla_vacia_curva` en `db.py`.
    *   Centralizar `ROUGHNESS_OPTIONS` en `calculos.py` y que todos los demás lo importen.
2.  **Corto Plazo (Estabilidad):**
    *   Corregir todos los strings con encoding roto a UTF-8 puro.
    *   Implementar `PRAGMA journal_mode=WAL;` en `get_connection`.
3.  **Medio Plazo (Arquitectura):**
    *   Mover el CSS de `Inicio.py` a un archivo `assets/style.css`.
    *   Crear una clase `ProjectContext` para evitar pasar `config` (dict) a todas las funciones de reportes.

---
**Reporte generado por Antigravity AI.**
