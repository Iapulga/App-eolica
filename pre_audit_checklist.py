"""Pre-audit checklist DNV-style. NO reemplaza certificación real.

Detecta gaps documentación/data quality antes de pagar auditor externo.
Reduce horas-consultor → ahorra $5-30k según calidad proyecto.

Score:
   >85: ready for auditor
   70-85: gaps menores, refinar
   <70: aún no listo para auditor
"""

from __future__ import annotations

import pandas as pd

PESO_CATEGORIA = {
    "Data Quality": 25,
    "Wake": 15,
    "IEC 61400-1": 20,
    "Económico": 20,
    "Ambiental": 10,
    "Social": 10,
}


PRE_AUDIT_ITEMS = [
    # ── Data Quality ──
    {"id": "DQ01", "categoria": "Data Quality", "criterio": "≥3 años datos satelitales NASA POWER",
     "check_key": "n_anios_nasa", "umbral": 3, "operador": ">="},
    {"id": "DQ02", "categoria": "Data Quality", "criterio": "Torre meteorológica ≥12 meses overlap",
     "check_key": "n_meses_torre", "umbral": 12, "operador": ">="},
    {"id": "DQ03", "categoria": "Data Quality", "criterio": "MCP R² ≥ 0.85 (sat ↔ torre)",
     "check_key": "mcp_r2", "umbral": 0.85, "operador": ">="},
    {"id": "DQ04", "categoria": "Data Quality", "criterio": "Recovery torre ≥ 90%",
     "check_key": "mast_recovery_pct", "umbral": 90, "operador": ">="},
    {"id": "DQ05", "categoria": "Data Quality", "criterio": "Temperatura T2M en NASA disponible (para densidad real)",
     "check_key": "t2m_disponible", "umbral": True, "operador": "=="},

    # ── Wake ──
    {"id": "WK01", "categoria": "Wake", "criterio": "Modelo gold-standard (py_wake DTU o WAsP)",
     "check_key": "wake_model_gold_std", "umbral": True, "operador": "=="},
    {"id": "WK02", "categoria": "Wake", "criterio": "Comparación ≥2 modelos wake distintos",
     "check_key": "n_wake_modelos_comparados", "umbral": 2, "operador": ">="},
    {"id": "WK03", "categoria": "Wake", "criterio": "Spacing mínimo turbinas ≥ 3D",
     "check_key": "spacing_min_D", "umbral": 3.0, "operador": ">="},

    # ── IEC 61400-1 ──
    {"id": "IEC01", "categoria": "IEC 61400-1", "criterio": "Site suitability completo cumple",
     "check_key": "iec_cumple_global", "umbral": True, "operador": "=="},
    {"id": "IEC02", "categoria": "IEC 61400-1", "criterio": "V_ref 50y calculado (Gumbel)",
     "check_key": "v_ref_50y_calculado", "umbral": True, "operador": "=="},
    {"id": "IEC03", "categoria": "IEC 61400-1", "criterio": "TI(15 m/s) ≤ límite categoría",
     "check_key": "ti_cumple", "umbral": True, "operador": "=="},

    # ── Económico ──
    {"id": "EC01", "categoria": "Económico", "criterio": "DSCR mínimo ≥ 1.3",
     "check_key": "dscr_min", "umbral": 1.3, "operador": ">="},
    {"id": "EC02", "categoria": "Económico", "criterio": "WACC desglosado calculado",
     "check_key": "wacc_calculado", "umbral": True, "operador": "=="},
    {"id": "EC03", "categoria": "Económico", "criterio": "P90 banca calculado (Monte Carlo)",
     "check_key": "p90_calculado", "umbral": True, "operador": "=="},
    {"id": "EC04", "categoria": "Económico", "criterio": "IRR > WACC (proyecto viable)",
     "check_key": "irr_supera_wacc", "umbral": True, "operador": "=="},

    # ── Ambiental ──
    {"id": "EN01", "categoria": "Ambiental", "criterio": "Shadow flicker <30h/año en todo receptor",
     "check_key": "flicker_max_h_anio", "umbral": 30, "operador": "<="},
    {"id": "EN02", "categoria": "Ambiental", "criterio": "Ruido ≤ 50 dB(A) diurno residencial",
     "check_key": "ruido_max_diurno_db", "umbral": 50, "operador": "<="},
    {"id": "EN03", "categoria": "Ambiental", "criterio": "Bird collision risk evaluado",
     "check_key": "bird_collision_evaluado", "umbral": True, "operador": "=="},

    # ── Social ──
    {"id": "SO01", "categoria": "Social", "criterio": "Consulta previa Wayuu documentada (manual)",
     "check_key": "consulta_previa_docs", "umbral": True, "operador": "==", "manual": True},
    {"id": "SO02", "categoria": "Social", "criterio": "Mesa diálogo activa con comunidades (manual)",
     "check_key": "mesa_dialogo", "umbral": True, "operador": "==", "manual": True},
]


def _aplicar_operador(valor, umbral, operador):
    """Aplica operador comparación. Returns True (PASS), False (FAIL), None (sin dato)."""
    if valor is None:
        return None
    try:
        if operador == ">=":
            return float(valor) >= float(umbral)
        if operador == "<=":
            return float(valor) <= float(umbral)
        if operador == ">":
            return float(valor) > float(umbral)
        if operador == "<":
            return float(valor) < float(umbral)
        if operador == "==":
            if isinstance(umbral, bool):
                return bool(valor) == bool(umbral)
            return valor == umbral
    except Exception:
        return None
    return None


def ejecutar_pre_audit(context):
    """Para cada item del checklist, evalúa contra context dict.

    context: dict con check_key → valor. Items missing → status N/A.

    Returns DataFrame con id, categoria, criterio, status (PASS/FAIL/N/A/MANUAL), evidencia.
    """
    rows = []
    for item in PRE_AUDIT_ITEMS:
        check_key = item["check_key"]
        manual = item.get("manual", False)
        if check_key not in context and not manual:
            status = "N/A"
            evidencia = "Sin dato"
        elif manual:
            valor = context.get(check_key)
            if valor is None:
                status = "MANUAL"
                evidencia = "Requiere verificación manual"
            else:
                ok = _aplicar_operador(valor, item["umbral"], item["operador"])
                status = "PASS" if ok else "FAIL"
                evidencia = f"Documentado: {valor}"
        else:
            valor = context.get(check_key)
            ok = _aplicar_operador(valor, item["umbral"], item["operador"])
            if ok is None:
                status = "N/A"
                evidencia = "Sin dato"
            elif ok:
                status = "PASS"
                evidencia = f"valor={valor}"
            else:
                status = "FAIL"
                evidencia = f"valor={valor} no cumple {item['operador']} {item['umbral']}"

        rows.append({
            "id": item["id"],
            "categoria": item["categoria"],
            "criterio": item["criterio"],
            "status": status,
            "evidencia": evidencia,
        })
    return pd.DataFrame(rows)


def calcular_audit_score(df_audit):
    """Score 0-100 ponderado por categoría críticidad."""
    if df_audit is None or len(df_audit) == 0:
        return {"score": 0.0, "ready": False, "msg": "Sin checklist"}

    # Score por categoría
    cat_scores = {}
    for cat, peso in PESO_CATEGORIA.items():
        items_cat = df_audit[df_audit["categoria"] == cat]
        if len(items_cat) == 0:
            cat_scores[cat] = 0
            continue
        pass_count = (items_cat["status"] == "PASS").sum()
        na_count = (items_cat["status"].isin(["N/A", "MANUAL"])).sum()
        # PASS = 1.0, N/A o MANUAL = 0.5, FAIL = 0
        total = pass_count + 0.5 * na_count
        score_cat = total / len(items_cat) * peso
        cat_scores[cat] = score_cat

    score_total = sum(cat_scores.values())
    n_fail = int((df_audit["status"] == "FAIL").sum())
    n_pass = int((df_audit["status"] == "PASS").sum())
    n_na = int((df_audit["status"].isin(["N/A", "MANUAL"])).sum())

    if score_total >= 85:
        readiness = "READY FOR AUDITOR"
        msg = f"Score {score_total:.1f} — el proyecto está listo para auditor externo (DNV/UL/TÜV)."
    elif score_total >= 70:
        readiness = "MINOR GAPS"
        msg = f"Score {score_total:.1f} — gaps menores, refinar antes de enviar a auditor."
    else:
        readiness = "NOT READY"
        msg = f"Score {score_total:.1f} — no enviar a auditor todavía. Cerrar {n_fail} FAILs."

    return {
        "score": float(score_total),
        "ready": score_total >= 85,
        "readiness_level": readiness,
        "msg": msg,
        "scores_por_categoria": cat_scores,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "n_na_manual": n_na,
        "n_total": int(len(df_audit)),
    }


def construir_contexto_desde_config_sma(config):
    """Mapea config SMA → context para checklist."""
    def _f(k, default=None):
        v = config.get(k)
        if v in (None, "", "None"):
            return default
        try:
            return float(v)
        except Exception:
            return v

    n_anios = 0
    try:
        ini = config.get("nasa_inicio", "")
        fin = config.get("nasa_fin", "")
        if ini and fin:
            n_anios = (pd.to_datetime(fin).year - pd.to_datetime(ini).year) + 1
    except Exception:
        pass

    irr = _f("f5_irr_pct", 0) or 0
    tasa_desc = _f("f5_tasa_descuento_pct", 0) or 0

    wake_model = str(config.get("f5_wake_model", "Jensen")).lower()
    wake_gold = wake_model.startswith("pywake") or wake_model in ("wasp",)

    return {
        # Data Quality
        "n_anios_nasa": n_anios,
        "n_meses_torre": 12 if config.get("f2_mast_disponible") == "True" else 0,
        "mcp_r2": _f("f2_mcp_r2", 0),
        "mast_recovery_pct": _f("f2_mast_recovery_pct", 0),
        "t2m_disponible": True if _f("f5_densidad_modo") == "mensual" else False,
        # Wake
        "wake_model_gold_std": wake_gold,
        "n_wake_modelos_comparados": 1,
        "spacing_min_D": _f("f4_dx_D", 0),
        # IEC
        "iec_cumple_global": str(config.get("f5_iec_cumple", "")).lower() in ("true", "1"),
        "v_ref_50y_calculado": True,
        "ti_cumple": str(config.get("f5_iec_cumple", "")).lower() in ("true", "1"),
        # Económico
        "dscr_min": _f("f5_dscr_min", 0),
        "wacc_calculado": True,
        "p90_calculado": bool(_f("f5_aep_p90")),
        "irr_supera_wacc": (irr > tasa_desc) if (irr and tasa_desc) else None,
        # Ambiental
        "flicker_max_h_anio": _f("f5_flicker_max_h"),
        "ruido_max_diurno_db": _f("f5_ruido_max_db"),
        "bird_collision_evaluado": False,
        # Social
        "consulta_previa_docs": None,
        "mesa_dialogo": None,
    }
