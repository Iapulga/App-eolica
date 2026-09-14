"""Datos del proyecto para TODOS los exportables (una sola fuente de verdad).

Informe técnico (Word/PDF), Excel, Excel PRO, reporte bankable y JSON toman de aquí los
valores del proyecto ACTIVO: ubicación, aerogenerador, altura de buje, recurso, pérdidas,
incertidumbre, IEC, ambiental, economía y país. Nada queda fijo: todo sale de la
configuración guardada (BD) y, si la Fase 5 se abrió en esta sesión, de su contexto en
memoria (el resultado exacto de los cálculos).

No se calcula nada nuevo: se reutilizan las funciones de la app (calculos,
calculos_energia, calculos_economicos) con los mismos parámetros que usa cada fase, de
modo que los documentos muestran exactamente lo mismo que la app.
"""
from __future__ import annotations

import json
import math
from datetime import datetime

import pandas as pd

# ─────────────────────────────────────────────────────────────
# Utilidades de lectura
# ─────────────────────────────────────────────────────────────
_VACIOS = {"", "none", "nan", "—", "-", "n/d"}


def num(value, default=None):
    """float finito o `default` (acepta strings de la BD como '12.5')."""
    try:
        if value is None:
            return default
        if isinstance(value, str):
            texto = value.strip()
            if texto.lower() in _VACIOS:
                return default
            value = texto
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def cfg(config, *keys, default=None):
    """Primer valor no vacío entre varias claves de configuración."""
    for key in keys:
        value = (config or {}).get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() in _VACIOS:
            continue
        return value
    return default


def es_verdadero(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "si", "sí", "yes"}


def limpiar_cero(value, decimales=2):
    """Redondea y quita el '-0' que dejan los flotantes (-5.5e-14 → 0.0)."""
    x = num(value)
    if x is None:
        return None
    x = round(x, decimales)
    return 0.0 if x == 0 else x


# ─────────────────────────────────────────────────────────────
# Formato de números por idioma (es/pt: 1.234,56 · en: 1,234.56 · fr: 1 234,56)
# ─────────────────────────────────────────────────────────────
_SEPARADORES = {"es": (".", ","), "pt": (".", ","), "en": (",", "."), "fr": (" ", ",")}


def fmt_num(value, dec=2, lang="es", default="—"):
    x = num(value)
    if x is None:
        return default
    if abs(x) < 0.5 * 10 ** (-dec):
        x = 0.0
    texto = f"{x:,.{dec}f}"
    miles, decimal = _SEPARADORES.get(lang, _SEPARADORES["es"])
    return texto.replace(",", "\x00").replace(".", decimal).replace("\x00", miles)


def fmt_pct(value, dec=2, lang="es", default="—"):
    texto = fmt_num(value, dec, lang, default=None)
    return default if texto is None else f"{texto} %"


def fmt_money(value, moneda="USD", lang="es", dec=None, default="—"):
    x = num(value)
    if x is None:
        return default
    if dec is None:
        dec = 0 if abs(x) >= 1000 else 2
    return f"{moneda} {fmt_num(x, dec, lang)}"


def fmt_coord(value, lang="es", default="—"):
    return fmt_num(value, 6, lang, default)


# ─────────────────────────────────────────────────────────────
# Bloques de datos
# ─────────────────────────────────────────────────────────────
def _df(value):
    return value if isinstance(value, pd.DataFrame) else None


def _curva_preparada(df_curva_raw):
    try:
        from calculos import preparar_datos_curva

        curva = preparar_datos_curva(df_curva_raw)
        return curva if curva is not None and len(curva) > 0 else None
    except Exception:
        return None


def _nombre_turbina(config):
    """Nombre del modelo si la Fase 1 usa una curva guardada con nombre; si no, None."""
    curve_id = str(cfg(config, "f1_default_curve_id", default="") or "")
    if not curve_id or curve_id == "default":
        return None
    try:
        from db import cargar_power_curves

        curva = cargar_power_curves().get(curve_id) or {}
        nombre = str(curva.get("nombre") or "").strip()
        return nombre or None
    except Exception:
        return None


def _layout(runtime_context):
    df_layout = _df((runtime_context or {}).get("df_layout"))
    if df_layout is None:
        try:
            from db import cargar_layout_parque

            df_layout = cargar_layout_parque()
        except Exception:
            df_layout = pd.DataFrame()
    filas = []
    for i, (_, fila) in enumerate(df_layout.iterrows()):
        filas.append({
            "id": str(fila.get("turbina_id") or f"T{i + 1}"),
            "x_m": limpiar_cero(fila.get("x_m"), 2) or 0.0,
            "y_m": limpiar_cero(fila.get("y_m"), 2) or 0.0,
        })
    return filas


def evaluar_iec(v_media_buje, ti_15, clase, categoria):
    """Misma clasificación que la Fase 5 (calculos.clasificar_iec_61400_1)."""
    from calculos import IEC_CLASES_VELOCIDAD, clasificar_iec_61400_1

    v = num(v_media_buje, float("nan"))
    ti = num(ti_15, float("nan"))
    res = clasificar_iec_61400_1(v, ti, clase or "II", categoria or "B")
    res["v_ref_clase"] = IEC_CLASES_VELOCIDAD.get(res["clase_velocidad"], {}).get("v_ref")
    return res


def cadena_perdidas(aep_bruta, aep_con_estela, perdidas_pct, res=None):
    """Cascada AEP bruta → neta con las MISMAS pérdidas y el mismo orden secuencial de la Fase 5."""
    from calculos_energia import LOSS_BUCKET_ORDER, desglose_perdidas_secuencial

    bruta = num(aep_bruta, 0.0) or 0.0
    con_estela = num(aep_con_estela, bruta) or 0.0
    res = res or {}
    estela_mwh = num(res.get("perdida_estela_mwh"), bruta - con_estela)
    pasos = [{"clave": "bruta", "etiqueta": "AEP bruta", "pct": None, "perdida_mwh": 0.0, "acumulada_mwh": bruta}]
    pasos.append({
        "clave": "estela", "etiqueta": "Estelas",
        "pct": (estela_mwh / bruta * 100.0) if bruta > 0 else 0.0,
        "perdida_mwh": estela_mwh, "acumulada_mwh": con_estela,
    })
    desglose = desglose_perdidas_secuencial(con_estela, perdidas_pct or {})
    claves_res = {"disp_turb": "perdida_disp_mwh"}
    base = con_estela
    for clave, etiqueta in LOSS_BUCKET_ORDER:
        mwh = num(res.get(claves_res.get(clave, f"perdida_{clave}_mwh")), desglose.get(f"perdida_{clave}_mwh", 0.0))
        pct = num((perdidas_pct or {}).get(clave), 0.0) or 0.0
        base = base - (mwh or 0.0)
        pasos.append({"clave": clave, "etiqueta": etiqueta, "pct": pct, "perdida_mwh": mwh or 0.0, "acumulada_mwh": base})
    return pasos, base


def _perdidas_pct(config, res):
    if res and isinstance(res.get("perdidas_dict"), dict):
        return {k: num(v, 0.0) or 0.0 for k, v in res["perdidas_dict"].items()}
    return {
        "disp_turb": num(cfg(config, "f5_disp_pct"), 0.0) or 0.0,
        "disp_red": num(cfg(config, "f5_loss_disp_red_pct"), 0.0) or 0.0,
        "elec": num(cfg(config, "f5_elec_pct"), 0.0) or 0.0,
        "hielo": num(cfg(config, "f5_loss_hielo_pct"), 0.0) or 0.0,
        "histeresis": num(cfg(config, "f5_loss_histeresis_pct"), 0.0) or 0.0,
        "curtailment": num(cfg(config, "f5_loss_curtailment_pct"), 0.0) or 0.0,
        "otras": num(cfg(config, "f5_otras_pct"), 0.0) or 0.0,
    }


def resumen_incertidumbre(config, energia):
    """Monte Carlo guardado por la Fase 5 + presupuesto equivalente sobre la AEP con el MISMO modelo.

    El Monte Carlo de la Fase 5 aplica: viento → AEP con σ = 2,5·σc + 0,3·σk; curva → σ directa;
    estela y pérdidas → σ RELATIVAS al valor de cada pérdida (no a la energía). Aquí se traduce cada
    una a su efecto equivalente sobre la AEP para que la tabla cuadre con el resultado del Monte Carlo.
    """
    p50 = num(cfg(config, "f5_aep_p50"))
    p90 = num(cfg(config, "f5_aep_p90"))
    media = num(cfg(config, "f5_aep_mc_mean"))
    desv = num(cfg(config, "f5_aep_mc_std"))
    sig = {
        "k": num(cfg(config, "f5_mc_sigma_k_pct"), 3.0),
        "c": num(cfg(config, "f5_mc_sigma_c_pct"), 4.0),
        "curva": num(cfg(config, "f5_mc_sigma_curva_pct"), 3.0),
        "perdidas": num(cfg(config, "f5_mc_sigma_perdidas_pct"), 20.0),
        "estela": num(cfg(config, "f5_mc_sigma_wake_pct"), 15.0),
    }
    bruta = num(energia.get("aep_bruta_mwh"), 0.0) or 0.0
    estela_frac = (num(energia.get("perdida_estela_mwh"), 0.0) or 0.0) / bruta if bruta > 0 else 0.0
    perdidas = [v / 100.0 for v in (energia.get("perdidas_pct") or {}).values() if (num(v, 0.0) or 0.0) > 0]
    presupuesto = [
        {"clave": "recurso", "sigma_entrada": f"σk {sig['k']:g} % · σc {sig['c']:g} %", "sigma_aep": 2.5 * sig["c"] + 0.3 * sig["k"]},
        {"clave": "curva", "sigma_entrada": f"{sig['curva']:g} %", "sigma_aep": sig["curva"]},
        {"clave": "estela", "sigma_entrada": f"{sig['estela']:g} % (relativa)", "sigma_aep": sig["estela"] * estela_frac},
        {"clave": "perdidas", "sigma_entrada": f"{sig['perdidas']:g} % (relativa)",
         "sigma_aep": math.sqrt(sum((sig["perdidas"] * p) ** 2 for p in perdidas)) if perdidas else 0.0},
    ]
    sigma_rss = math.sqrt(sum(item["sigma_aep"] ** 2 for item in presupuesto))
    # El Monte Carlo solo se guarda al pulsar «Ejecutar Monte Carlo» en la Fase 5. Si después cambió la AEP neta
    # (altura, turbina, sitio, pérdidas…), sus percentiles ya no son de este proyecto y no se usan.
    neta_actual = num(energia.get("aep_neta_mwh"))
    base_mc = num(cfg(config, "f5_mc_aep_neta_base_mwh"))
    mc_obsoleto = None
    if p50 and p90 and neta_actual:
        referencia = base_mc if base_mc else media  # sin la AEP base guardada, se compara con la media del MC
        tolerancia = 0.001 if base_mc else 0.02
        if referencia and abs(referencia - neta_actual) / neta_actual > tolerancia:
            mc_obsoleto = {"base": referencia, "actual": neta_actual}
    if p50 and p90 and not mc_obsoleto:
        return {
            "fuente": "monte_carlo",
            "p50": p50, "p75": num(cfg(config, "f5_aep_p75")), "p90": p90, "p99": num(cfg(config, "f5_aep_p99")),
            "media": media, "desv": desv,
            "cv_pct": (desv / media * 100.0) if (media and desv) else None,
            "n": num(cfg(config, "f5_mc_n_samples")), "semilla": num(cfg(config, "f5_mc_seed")),
            "sigmas_entrada": sig, "presupuesto": presupuesto, "sigma_rss_pct": sigma_rss,
            "ratio_p90_p50": p90 / p50 if p50 else None,
        }
    # Sin Monte Carlo: estimación gaussiana con las categorías genéricas de calculos_uncertainty.
    from calculos_uncertainty import CATEGORY_LABELS, DEFAULT_SIGMAS_PCT, percentiles_gaussian

    neta = num(energia.get("aep_neta_mwh"), 0.0) or 0.0
    gauss = percentiles_gaussian(neta)
    return {
        "fuente": "generica",
        "p50": gauss["P50"], "p75": gauss["P75"], "p90": gauss["P90"], "p99": gauss["P99"],
        "media": neta, "desv": neta * gauss["sigma_total_pct"] / 100.0, "cv_pct": gauss["sigma_total_pct"],
        "n": None, "semilla": None, "sigmas_entrada": dict(DEFAULT_SIGMAS_PCT),
        "categorias": [(CATEGORY_LABELS.get(k, k), v) for k, v in DEFAULT_SIGMAS_PCT.items()],
        "presupuesto": [], "sigma_rss_pct": gauss["sigma_total_pct"],
        "ratio_p90_p50": gauss["P90"] / gauss["P50"] if gauss["P50"] else None,
        "mc_obsoleto": mc_obsoleto,
    }


def resumen_economico(config, runtime_econ=None, energia_neta=None):
    """CAPEX/OPEX/flujo de caja/sensibilidad con las mismas funciones y entradas que la Fase 5."""
    from calculos_economicos import (
        calcular_capex,
        calcular_metricas_financieras,
        calcular_opex,
        obtener_factor_conversion,
    )

    runtime_econ = runtime_econ or {}

    def _v(clave_cfg, clave_rt=None, default=None):
        """Valor de la configuración (BD) o, si falta, del contexto económico de la Fase 5."""
        valor = num(cfg(config, clave_cfg))
        if valor is None and clave_rt:
            valor = num(runtime_econ.get(clave_rt))
        return default if valor is None else valor

    moneda_base = str(cfg(config, "f5_moneda_base", default=runtime_econ.get("moneda_base") or "USD")).upper()
    moneda_vis = str(cfg(config, "f5_moneda_visualizacion",
                         default=runtime_econ.get("moneda_visualizacion") or moneda_base)).upper()
    fx = _v("f5_fx_rate_cop_per_usd", "fx_rate_cop_per_usd", 0.0) or 0.0
    factor = obtener_factor_conversion(moneda_base, moneda_vis, fx)
    if factor is None:
        factor, moneda_vis = 1.0, moneda_base
    p_inst = num(cfg(config, "f5_potencia_instalada_mw"),
                 num((runtime_econ.get("base_metrics") or {}).get("potencia_instalada_mw"), 0.0)) or 0.0
    energia = num(cfg(config, "f5_aep_neta_mwh_anio", "f5_aep_neta_total_mwh"), num(energia_neta, 0.0)) or 0.0

    def _json(key):
        try:
            data = json.loads(cfg(config, key, default="{}") or "{}")
            return {k: num(v, 0.0) or 0.0 for k, v in data.items()} if isinstance(data, dict) else {}
        except (TypeError, ValueError):
            return {}

    capex_mode = str(cfg(config, "f5_capex_mode", default="semi_auto_mw"))
    capex_res = None
    if runtime_econ.get("capex_breakdown"):
        capex_res = {"capex_total": num(runtime_econ.get("capex_total"), 0.0), "breakdown": runtime_econ["capex_breakdown"]}
    else:
        try:
            capex_res = calcular_capex(
                mode=capex_mode, potencia_instalada_mw=p_inst,
                inputs={
                    "capex_total": num(cfg(config, "f5_capex_total"), 0.0),
                    "costo_turbina_por_mw": num(cfg(config, "f5_capex_turbina_por_mw"), 0.0),
                    "costo_bop_por_mw": num(cfg(config, "f5_capex_bop_por_mw"), 0.0),
                    "costo_red_por_mw": num(cfg(config, "f5_capex_red_por_mw"), 0.0),
                    "porcentaje_desarrollo": num(cfg(config, "f5_capex_pct_desarrollo"), 0.0),
                    "porcentaje_contingencia": num(cfg(config, "f5_capex_pct_contingencia"), 0.0),
                },
                components=_json("f5_capex_componentes_json"),
            )
        except Exception:
            capex_res = None
    capex_total = _v("f5_capex_total", "capex_total", num((capex_res or {}).get("capex_total"), 0.0)) or 0.0
    capex_items = [
        {"concepto": str(item.get("Concepto")), "valor": num(item.get("Valor"), 0.0) or 0.0}
        for item in (capex_res or {}).get("breakdown", [])
        if "total" not in str(item.get("Concepto", "")).lower()
    ]

    opex_mode = str(cfg(config, "f5_opex_mode", default="fixed_variable"))
    opex_res = None
    if runtime_econ.get("opex_breakdown"):
        opex_res = {"breakdown": runtime_econ["opex_breakdown"]}
    else:
        try:
            opex_res = calcular_opex(
                mode=opex_mode, potencia_instalada_mw=p_inst, energia_mwh_anio=energia,
                inputs={
                    "opex_total_anual": num(cfg(config, "f5_opex_total_anual"), 0.0),
                    "opex_fijo_por_mw_anio": num(cfg(config, "f5_opex_fijo_por_mw_anio"), 0.0),
                    "opex_variable_por_mwh": num(cfg(config, "f5_opex_variable_por_mwh"), 0.0),
                    "seguros_anuales": num(cfg(config, "f5_seguros_anuales"), 0.0),
                    "terreno_anual": num(cfg(config, "f5_terreno_anual"), 0.0),
                    "administracion_anual": num(cfg(config, "f5_admin_anual"), 0.0),
                },
                components=_json("f5_opex_componentes_json"),
            )
        except Exception:
            opex_res = None
    opex_total = _v("f5_opex_total_anual", "opex_total_anual", 0.0) or 0.0
    opex_items = [
        {"concepto": str(item.get("Concepto")), "valor": num(item.get("Valor"), 0.0) or 0.0}
        for item in (opex_res or {}).get("breakdown", [])
        if "total" not in str(item.get("Concepto", "")).lower()
    ]

    opex_fijo = num(cfg(config, "f5_opex_fijo_anual"), opex_total) or 0.0
    opex_var = num(cfg(config, "f5_opex_variable_por_mwh"), 0.0) or 0.0
    vida = int(_v("f5_vida_util_anios", "vida_util", 20) or 20)
    tasa = _v("f5_tasa_descuento_pct", "tasa_descuento", 8.0) or 0.0
    degr = _v("f5_degradacion_energia_pct", "degradacion_pct", 0.0) or 0.0
    residual = _v("f5_valor_residual", "valor_residual", 0.0) or 0.0
    precio = _v("f5_precio_energia_mwh", "precio_energia_mwh")
    delta = _v("f5_sens_delta_pct", "sens_delta_pct", 15.0) or 15.0

    base_kwargs = dict(
        capex_total=capex_total, opex_fijo_anual=opex_fijo, opex_variable_por_mwh=opex_var,
        energia_base_mwh_anio=energia, vida_util_anios=vida, tasa_descuento_pct=tasa,
        degradacion_energia_pct=degr, valor_residual=residual, precio_energia_mwh=precio or 0.0,
    )
    flujo_anual, sensibilidad, metricas = [], [], {}
    if precio is not None and energia > 0:
        metricas = calcular_metricas_financieras(**base_kwargs)
        flujos = list(metricas["flujos"])
        r = tasa / 100.0
        acum = acum_desc = 0.0
        for t, flujo in enumerate(flujos):
            energia_t = energia * ((1.0 - degr / 100.0) ** (t - 1)) if t > 0 else 0.0
            ingresos = energia_t * precio
            opex_t = (opex_fijo + opex_var * energia_t) if t > 0 else 0.0
            desc = flujo / ((1.0 + r) ** t)
            acum += flujo
            acum_desc += desc
            flujo_anual.append({
                "anio": t, "energia_mwh": energia_t, "ingresos": ingresos, "opex": opex_t,
                "inversion": capex_total if t == 0 else 0.0,
                "residual": residual if (t == vida and residual) else 0.0,
                "flujo": flujo, "flujo_desc": desc, "acumulado": acum, "acumulado_desc": acum_desc,
            })
        for clave, cambio in (
            ("precio", lambda kw, s: {**kw, "precio_energia_mwh": kw["precio_energia_mwh"] * s}),
            ("aep", lambda kw, s: {**kw, "energia_base_mwh_anio": kw["energia_base_mwh_anio"] * s}),
            ("capex", lambda kw, s: {**kw, "capex_total": kw["capex_total"] * s}),
            ("opex", lambda kw, s: {**kw, "opex_fijo_anual": kw["opex_fijo_anual"] * s, "opex_variable_por_mwh": kw["opex_variable_por_mwh"] * s}),
        ):
            bajo = calcular_metricas_financieras(**cambio(base_kwargs, 1 - delta / 100.0))["npv"]
            alto = calcular_metricas_financieras(**cambio(base_kwargs, 1 + delta / 100.0))["npv"]
            sensibilidad.append({"clave": clave, "npv_menos": bajo, "npv_mas": alto, "rango": abs(alto - bajo)})
        sensibilidad.sort(key=lambda item: item["rango"], reverse=True)

    # Plausibilidad: costo por kW y precio en USD (solo si la moneda se puede pasar a USD).
    a_usd = 1.0 if moneda_base == "USD" else (1.0 / fx if (moneda_base == "COP" and fx > 0) else None)
    capex_usd_kw = (capex_total * a_usd / (p_inst * 1000.0)) if (a_usd and p_inst > 0 and capex_total > 0) else None
    precio_usd = (precio * a_usd) if (a_usd and precio) else None

    return {
        "moneda_base": moneda_base, "moneda": moneda_vis, "factor": factor, "fx_cop_usd": fx or None,
        "potencia_instalada_mw": p_inst, "energia_neta_mwh": energia,
        "capex_mode": capex_mode, "capex_total": capex_total, "capex_items": capex_items,
        "opex_mode": opex_mode, "opex_total": opex_total, "opex_items": opex_items,
        "opex_fijo": opex_fijo, "opex_variable_mwh": opex_var,
        "lcoe_mwh": _v("f5_lcoe_mwh", "lcoe_mwh"), "lcoe_kwh": _v("f5_lcoe_kwh", "lcoe_kwh"),
        "npv": _v("f5_npv", "npv", metricas.get("npv")), "irr_pct": _v("f5_irr_pct", "irr_pct", metricas.get("irr_pct")),
        "payback_simple": _v("f5_payback_simple_anios", "payback_simple", metricas.get("payback_simple_anios")),
        "payback_desc": _v("f5_payback_descontado_anios", "payback_descontado", metricas.get("payback_descontado_anios")),
        "vp_costos": _v("f5_vp_costos", "vp_costos"),
        "vida_util": vida, "tasa_pct": tasa, "degradacion_pct": degr, "valor_residual": residual,
        "precio_mwh": precio, "sens_delta_pct": delta,
        "flujo_anual": flujo_anual, "sensibilidad": sensibilidad,
        "capex_usd_kw": capex_usd_kw, "precio_usd_mwh": precio_usd,
    }


def en_moneda(valor, eco):
    """Valor en moneda base → moneda de visualización (misma conversión que la Fase 5)."""
    x = num(valor)
    return None if x is None else x * (eco.get("factor") or 1.0)


# ─────────────────────────────────────────────────────────────
# Constructor principal
# ─────────────────────────────────────────────────────────────
def construir_datos_exportacion(config, runtime_context=None):
    config = config or {}
    rc = runtime_context or {}
    res = rc.get("res") or {}

    # ── Proyecto y ubicación ──
    lat, lon = num(cfg(config, "nasa_lat")), num(cfg(config, "nasa_lon"))
    try:
        from i18n_paises import get_country_profile, inferir_pais_por_coordenadas
    except ImportError:  # pragma: no cover
        get_country_profile = inferir_pais_por_coordenadas = None
    pais_inferido = inferir_pais_por_coordenadas(lat, lon) if inferir_pais_por_coordenadas else None
    pais_codigo = str(cfg(config, "f7_country_code", default=pais_inferido or "OTRO")).upper()
    perfil_pais = get_country_profile(pais_codigo) if get_country_profile else {}
    proyecto = {
        "nombre": str(rc.get("project_name_default") or rc.get("project_name") or cfg(config, "project_name", default="Proyecto eólico")),
        "lat": lat, "lon": lon,
        "fuente": str(cfg(config, "nasa_fuente", default="NASA POWER API")),
        "inicio": str(cfg(config, "nasa_inicio", default="—")), "fin": str(cfg(config, "nasa_fin", default="—")),
        "pais_codigo": pais_codigo, "pais_nombre": perfil_pais.get("nombre", pais_codigo), "perfil_pais": perfil_pais,
        "pais_inferido": pais_inferido,
        "pais_inferido_nombre": get_country_profile(pais_inferido).get("nombre") if (pais_inferido and get_country_profile) else None,
        "autor": str(cfg(config, "f7_bankable_autor", default="") or "").strip(),
        "cliente": str(cfg(config, "f7_bankable_cliente", default="") or "").strip(),
        "fecha": datetime.now().strftime("%Y-%m-%d"),
    }

    # ── Aerogenerador ──
    df_curva_raw = _df(rc.get("df_curva_raw"))
    if df_curva_raw is None:
        try:
            from db import cargar_tabla_curva

            df_curva_raw = cargar_tabla_curva()
        except Exception:
            df_curva_raw = None
    curva = _curva_preparada(df_curva_raw)
    p_nominal_curva_kw = float(curva["Potencia_W"].max()) / 1000.0 if curva is not None else None
    cut_in = cfg(config, "f35_cutin", "f3_prob_cutin")
    v_nom = cfg(config, "f35_nominal", "f3_prob_nominal")
    cut_out = cfg(config, "f35_cutout", "f3_prob_cutout")
    if curva is not None and (cut_in is None or v_nom is None or cut_out is None):
        try:
            from calculos import inferir_puntos_operacion_curva

            ci, vn, co = inferir_puntos_operacion_curva(curva)
            cut_in, v_nom, cut_out = cut_in or ci, v_nom or vn, cut_out or co
        except Exception:
            pass
    n_turbinas = int(num(rc.get("n_turbinas"), num(cfg(config, "f5_n_turbinas", "f4_num_turbinas"), 0)) or 0)
    p_inst = num(cfg(config, "f5_potencia_instalada_mw"))
    if p_inst is None and p_nominal_curva_kw and n_turbinas:
        p_inst = p_nominal_curva_kw * n_turbinas / 1000.0
    turbina = {
        "modelo": _nombre_turbina(config),
        "diametro_m": num(cfg(config, "diametro")),
        "altura_buje_m": num(rc.get("altura_deseada"), num(cfg(config, "f5_altura_deseada", "perfil_hhub"))),
        "p_nominal_kw": p_nominal_curva_kw,
        "p_nominal_mw_f5": num(cfg(config, "f5_potencia_nominal_turbina_mw")),
        "n_turbinas": n_turbinas, "p_instalada_mw": p_inst,
        "cut_in": num(cut_in), "v_nominal": num(v_nom), "cut_out": num(cut_out),
        "ct": num(rc.get("ct"), num(cfg(config, "f5_ct", "f4_ct"))),
        "densidad_curva": num(cfg(config, "densidad")),
        "df_curva": curva,
    }
    if turbina["diametro_m"]:
        turbina["area_m2"] = math.pi * (turbina["diametro_m"] / 2.0) ** 2

    # ── Recurso eólico ──
    df_analisis = _df(rc.get("df_analisis"))
    v_media_buje = num(cfg(config, "f5_v_media_buje_ms"))
    if v_media_buje is None and df_analisis is not None and "WS_ANALISIS" in df_analisis.columns:
        v_media_buje = num(pd.to_numeric(df_analisis["WS_ANALISIS"], errors="coerce").mean())
    serie_uso = str(cfg(config, "f2_serie_uso", default="nasa")).lower()
    altura_ref = 50.0
    if serie_uso not in ("nasa", "") and num(cfg(config, "f2_mast_altura_sensor")):
        altura_ref = num(cfg(config, "f2_mast_altura_sensor"))
    recurso = {
        "v10": num(cfg(config, "perfil_vref")), "v50": num(cfg(config, "perfil_v50")),
        "v_media_buje": v_media_buje,
        "alpha": num(cfg(config, "perfil_alpha")),
        "alpha_mediana": num(cfg(config, "f2_alpha_calc_mediana")),
        "alpha_p25": num(cfg(config, "f2_alpha_calc_p25")), "alpha_p75": num(cfg(config, "f2_alpha_calc_p75")),
        "alpha_n": num(cfg(config, "f2_alpha_calc_n")),
        "u_star": num(cfg(config, "perfil_ustar")), "z0": num(cfg(config, "perfil_z0")),
        "rugosidad": str(rc.get("roughness_label") or cfg(config, "f5_roughness_label", "perfil_roughness_label", default="—")),
        "modelo_altura": str(rc.get("base_viento") or cfg(config, "f5_base_viento", default="—")),
        "direccion": str(rc.get("dir_altura") or cfg(config, "f5_dir_altura", "f3_direccion_fuente", default="WD50M")),
        "ti_15": num(cfg(config, "f5_ti_15ms_calc")), "ti_ambiente": num(cfg(config, "f5_ambient_ti")),
        "densidad_sitio": num(cfg(config, "f5_densidad_sitio")),
        "altitud_m": num(cfg(config, "f5_altitud_sitio_m")), "temperatura_c": num(cfg(config, "f5_temperatura_media_c")),
        "serie_uso": serie_uso, "altura_referencia_m": altura_ref,
        "mcp_aplicado": es_verdadero(cfg(config, "f2_mcp_calculado", default="False")),
        "mcp_r2": num(cfg(config, "f2_mcp_r2")), "mcp_rmse": num(cfg(config, "f2_mcp_rmse")),
        "torre_disponible": es_verdadero(cfg(config, "f2_mast_disponible", default="False")),
        "torre_recovery_pct": num(cfg(config, "f2_mast_recovery_pct")),
        "resumen_sectorial": _df(rc.get("resumen_rosa")),
        "df_analisis": df_analisis,
        "df_nasa": _df(rc.get("df_nasa")),
    }

    # ── Energía y pérdidas (resultado exacto de la Fase 5) ──
    aep_bruta = num(res.get("aep_bruta_total"), num(cfg(config, "f5_aep_bruta_total_mwh")))
    aep_con_estela = num(res.get("aep_con_estela_total"), num(cfg(config, "f5_aep_con_estela_total_mwh")))
    perdida_estela = num(res.get("perdida_estela_mwh"), num(cfg(config, "f5_perdida_estela_total_mwh")))
    if aep_con_estela is None and aep_bruta is not None and perdida_estela is not None:
        aep_con_estela = aep_bruta - perdida_estela
    if perdida_estela is None and aep_bruta is not None and aep_con_estela is not None:
        perdida_estela = aep_bruta - aep_con_estela
    perdidas_pct = _perdidas_pct(config, res)
    pasos, neta_cadena = cadena_perdidas(aep_bruta, aep_con_estela, perdidas_pct, res) if aep_bruta else ([], None)
    aep_neta = num(res.get("aep_neta_total"), num(cfg(config, "f5_aep_neta_total_mwh"), neta_cadena))
    wake_mode = str(rc.get("wake_mode") or cfg(config, "f5_wake_mode", default="—"))
    energia = {
        "aep_bruta_mwh": aep_bruta, "aep_con_estela_mwh": aep_con_estela, "aep_neta_mwh": aep_neta,
        "perdida_estela_mwh": perdida_estela,
        "estela_pct": (perdida_estela / aep_bruta * 100.0) if (aep_bruta and perdida_estela is not None) else None,
        "perdida_total_pct": ((aep_bruta - aep_neta) / aep_bruta * 100.0) if (aep_bruta and aep_neta) else None,
        "fp_bruto_pct": num(res.get("factor_planta_bruto"), num(cfg(config, "f5_factor_planta_bruto_pct"))),
        "fp_neto_pct": num(res.get("factor_planta_neto"), num(cfg(config, "f5_factor_planta_neto_pct"))),
        "metodo": str(rc.get("metodo_detalle") or cfg(config, "f5_metodo_detalle", "f5_modo_estadistico", default="Weibull")),
        "wake_mode": wake_mode, "wake_automatica": "autom" in wake_mode.lower(),
        "wake_model": str(cfg(config, "f5_wake_model", "f4_wake_model", default="Jensen")),
        "wake_manual_pct": num(rc.get("wake_manual_pct"), num(cfg(config, "f5_wake_manual_pct"))),
        "f4_perdida_ponderada_pct": num(cfg(config, "f4_weighted_wake_loss_pct")),
        "peor_sector": cfg(config, "f4_worst_sector"), "peor_sector_pct": num(cfg(config, "f4_worst_sector_loss_pct")),
        "sectores_criticos": cfg(config, "f4_geom_critical_sectors"),
        "perdidas_pct": perdidas_pct, "cascada": pasos, "neta_cadena_mwh": neta_cadena,
        "aep_serie_horaria_mwh": num(cfg(config, "f5_aep_serie_horaria_total")),
        "df_aep_sector": _df(rc.get("df_aep_sector")), "tabla_perdidas": _df(rc.get("tabla_perdidas")),
    }

    # ── Incertidumbre ──
    incert = resumen_incertidumbre(config, {**energia, "aep_neta_mwh": aep_neta})

    # ── IEC 61400-1 (mismo criterio que la Fase 5) ──
    clase = str(cfg(config, "f5_iec_clase_declarada", default="II"))
    categoria = str(cfg(config, "f5_iec_turb_declarada", default="B"))
    iec_eval = evaluar_iec(v_media_buje, recurso["ti_15"], clase, categoria)
    guardado = str(cfg(config, "f5_iec_cumple", default="")).strip().lower()
    iec = {
        **iec_eval,
        "clase_declarada": clase, "categoria_declarada": categoria,
        "cumple_guardado": True if guardado == "true" else (False if guardado == "false" else None),
        "ti_indicativa": True,  # la serie de la app es horaria: la TI de la norma usa 10 minutos
    }

    # ── Ambiental (Fase 6) ──
    ruido = num(cfg(config, "f5_ruido_max_db"))
    flicker = num(cfg(config, "f5_flicker_max_h"))
    ambiental = {
        "ruido_analizado": ruido is not None, "ruido_max_db": ruido,
        "ruido_lim_dia": num(cfg(config, "f6_ruido_lim_diurno"), perfil_pais.get("limite_ruido_diurno_db")),
        "ruido_lim_noche": num(cfg(config, "f6_ruido_lim_nocturno"), perfil_pais.get("limite_ruido_nocturno_db")),
        "ruido_lwa_db": num(cfg(config, "f6_ruido_lwa_db")),
        "flicker_analizado": flicker is not None, "flicker_max_h": flicker,
        "flicker_lim_h": num(cfg(config, "f6_flicker_limite_h"), 30.0),
    }

    # ── Economía ──
    eco = resumen_economico(config, rc.get("economics"), energia_neta=aep_neta)

    # ── Avisos de coherencia (se muestran en los informes) ──
    avisos = []
    if pais_inferido and pais_inferido != pais_codigo:
        avisos.append({"clave": "pais", "pais": proyecto["pais_nombre"], "inferido": proyecto["pais_inferido_nombre"]})
    if eco.get("capex_usd_kw") is not None and not (500.0 <= eco["capex_usd_kw"] <= 4000.0):
        avisos.append({"clave": "capex", "valor": eco["capex_usd_kw"], "moneda": eco["moneda_base"]})
    if eco.get("precio_usd_mwh") is not None and not (15.0 <= eco["precio_usd_mwh"] <= 400.0):
        avisos.append({"clave": "precio", "valor": eco["precio_usd_mwh"], "moneda": eco["moneda_base"]})
    if incert.get("mc_obsoleto"):
        avisos.append({"clave": "mc_obsoleto", **incert["mc_obsoleto"]})
    elif incert["fuente"] != "monte_carlo":
        avisos.append({"clave": "sin_mc"})
    if recurso["ti_15"] is not None:
        avisos.append({"clave": "ti_horaria", "valor": recurso["ti_15"]})

    return {
        "proyecto": proyecto, "turbina": turbina, "recurso": recurso, "energia": energia,
        "incertidumbre": incert, "iec": iec, "ambiental": ambiental, "economia": eco,
        "layout": {
            "turbinas": _layout(rc),
            "tipo": cfg(config, "f4_layout_type"), "dx_D": num(cfg(config, "f4_dx_D")), "dy_D": num(cfg(config, "f4_dy_D")),
        },
        "avisos": avisos,
    }


_AVISOS = {
    "pais": {
        "es": "El país del informe ({pais}) no coincide con la ubicación del sitio, que parece estar en {inferido}. Revise el país en la Fase 7.",
        "en": "The report country ({pais}) does not match the site location, which appears to be in {inferido}. Check the country in Phase 7.",
        "pt": "O país do relatório ({pais}) não coincide com a localização do sítio, que parece estar em {inferido}. Revise o país na Fase 7.",
        "fr": "Le pays du rapport ({pais}) ne correspond pas à la localisation du site, qui semble se trouver en {inferido}. Vérifiez le pays en Phase 7.",
    },
    "capex": {
        "es": "El CAPEX equivale a {valor} USD/kW, fuera del rango típico de la eólica terrestre (≈ 1.000–2.500 USD/kW). Revise la moneda ({moneda}) y los costos de la Fase 5.",
        "en": "CAPEX is equivalent to {valor} USD/kW, outside the typical onshore wind range (≈ 1,000–2,500 USD/kW). Check the currency ({moneda}) and the Phase 5 costs.",
        "pt": "O CAPEX equivale a {valor} USD/kW, fora da faixa típica da eólica terrestre (≈ 1.000–2.500 USD/kW). Revise a moeda ({moneda}) e os custos da Fase 5.",
        "fr": "Le CAPEX équivaut à {valor} USD/kW, hors de la plage typique de l'éolien terrestre (≈ 1 000–2 500 USD/kW). Vérifiez la devise ({moneda}) et les coûts de la Phase 5.",
    },
    "precio": {
        "es": "El precio de venta equivale a {valor} USD/MWh, fuera del rango habitual (≈ 30–150 USD/MWh). Revise la moneda ({moneda}) en la Fase 5.",
        "en": "The energy price is equivalent to {valor} USD/MWh, outside the usual range (≈ 30–150 USD/MWh). Check the currency ({moneda}) in Phase 5.",
        "pt": "O preço de venda equivale a {valor} USD/MWh, fora da faixa habitual (≈ 30–150 USD/MWh). Revise a moeda ({moneda}) na Fase 5.",
        "fr": "Le prix de vente équivaut à {valor} USD/MWh, hors de la plage habituelle (≈ 30–150 USD/MWh). Vérifiez la devise ({moneda}) en Phase 5.",
    },
    "sin_mc": {
        "es": "No se ha ejecutado el Monte Carlo de la Fase 5: P50/P90 son una estimación genérica.",
        "en": "The Phase 5 Monte Carlo has not been run: P50/P90 are a generic estimate.",
        "pt": "O Monte Carlo da Fase 5 não foi executado: P50/P90 são uma estimativa genérica.",
        "fr": "Le Monte Carlo de la Phase 5 n'a pas été exécuté : P50/P90 sont une estimation générique.",
    },
    "mc_obsoleto": {
        "es": "El Monte Carlo guardado corresponde a una AEP neta de {base} MWh/año, pero la actual es {actual} MWh/año "
              "(cambiaron los datos del proyecto). Vuelva a ejecutarlo en la Fase 5; mientras tanto, P50/P90 son una "
              "estimación genérica.",
        "en": "The saved Monte Carlo corresponds to a net AEP of {base} MWh/yr, but the current one is {actual} MWh/yr "
              "(the project data changed). Run it again in Phase 5; meanwhile, P50/P90 are a generic estimate.",
        "pt": "O Monte Carlo salvo corresponde a uma AEP líquida de {base} MWh/ano, mas a atual é {actual} MWh/ano "
              "(os dados do projeto mudaram). Execute-o novamente na Fase 5; enquanto isso, P50/P90 são uma "
              "estimativa genérica.",
        "fr": "Le Monte Carlo enregistré correspond à une AEP nette de {base} MWh/an, alors que l'actuelle est de "
              "{actual} MWh/an (les données du projet ont changé). Relancez-le en Phase 5 ; en attendant, P50/P90 "
              "sont une estimation générique.",
    },
    "ti_horaria": {
        "es": "La intensidad de turbulencia (TI a 15 m/s = {valor}) se estima con datos horarios: es indicativa (la norma usa estadísticos de 10 minutos).",
        "en": "Turbulence intensity (TI at 15 m/s = {valor}) is estimated from hourly data: it is indicative (the standard uses 10-minute statistics).",
        "pt": "A intensidade de turbulência (TI a 15 m/s = {valor}) é estimada com dados horários: é indicativa (a norma usa estatísticas de 10 minutos).",
        "fr": "L'intensité de turbulence (TI à 15 m/s = {valor}) est estimée à partir de données horaires : elle est indicative (la norme utilise des statistiques 10 minutes).",
    },
}


def texto_aviso(aviso, lang="es"):
    plantilla = _AVISOS.get(aviso.get("clave"), {})
    texto = plantilla.get(lang) or plantilla.get("es") or ""
    decimales = {"capex": 2, "precio": 3, "ti_horaria": 3}.get(aviso.get("clave"), 2)
    return texto.format(
        pais=aviso.get("pais", ""), inferido=aviso.get("inferido", ""), moneda=aviso.get("moneda", ""),
        valor=fmt_num(aviso.get("valor"), decimales, lang),
        base=fmt_num(aviso.get("base"), 0, lang), actual=fmt_num(aviso.get("actual"), 0, lang),
    )


__all__ = ["texto_aviso", 
    "cadena_perdidas", "cfg", "construir_datos_exportacion", "en_moneda", "es_verdadero", "evaluar_iec",
    "fmt_coord", "fmt_money", "fmt_num", "fmt_pct", "limpiar_cero", "num", "resumen_economico",
    "resumen_incertidumbre",
]
