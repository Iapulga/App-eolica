"""Helpers para manejo de `st.session_state` por fase.

Provee utilidades para identificar la fase actual a partir
del script y limpiar claves de sesión pertenecientes a otras fases.
"""
from __future__ import annotations

PHASE_PREFIXES = ["f1_", "f2_", "f3_", "f4_", "f5_", "f6_", "f7_"]


def _normalize_script(script: str) -> str:
    if not script:
        return ""
    return script.replace("\\", "/").lower()


def script_to_phase_prefix(script: str) -> str | None:
    s = _normalize_script(script)
    if "1_fase_1" in s or "/pages/1_" in s or "1_fase_1_aerogenerador" in s:
        return "f1_"
    if "2_fase_2" in s or "/pages/2_" in s:
        return "f2_"
    if "3_fase_3" in s or "/pages/3_" in s:
        return "f3_"
    if "4_fase_4" in s or "/pages/4_" in s:
        return "f4_"
    if "5_fase_5" in s or "/pages/5_" in s:
        return "f5_"
    if "6_fase_6" in s or "/pages/6_" in s:
        return "f6_"
    if "7_fase_7" in s or "/pages/7_" in s:
        return "f7_"
    return None


def clear_other_phase_state(current_script: str) -> None:
    """No-op intencional para preservar widget state al navegar entre fases.

    Antes este helper borraba todas las claves f1_..f6_ que no pertenecieran
    a la fase actual. Eso causaba que ediciones no-guardadas se perdieran al
    cambiar de pestaña y forzaba reseed desde DB en cada montaje (lento).
    Mantener el estado entre fases es barato en memoria y elimina el
    "se recargó todo lento" reportado por el usuario.
    """
    return
