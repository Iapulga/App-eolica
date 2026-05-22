import html
import re
import unicodedata

try:
    import pandas as pd
except Exception:
    pd = None


_DIRECT_REPLACEMENTS = {
    "Ã¡": "á",
    "Ã©": "é",
    "Ã­": "í",
    "Ã³": "ó",
    "Ãº": "ú",
    "Ã": "Á",
    "Ã‰": "É",
    "Ã": "Í",
    "Ã“": "Ó",
    "Ãš": "Ú",
    "Ã±": "ñ",
    "Ã‘": "Ñ",
    "Â°": "°",
    "Â¿": "¿",
    "Â¡": "¡",
    "â€“": "–",
    "â€”": "—",
    "â€œ": "“",
    "â€": "”",
    "â€˜": "‘",
    "â€™": "’",
    "â€¢": "•",
    "\u00a0": " ",
}

_QUESTION_REPLACEMENTS = {
    # palabras generales
    "An?lisis": "Análisis",
    "an?lisis": "análisis",
    "Analisis": "Análisis",
    "analisis": "análisis",
    "Anual ponderado": "Anual ponderado",
    "Geometr?a": "Geometría",
    "geometr?a": "geometría",
    "Geom?trico": "Geométrico",
    "geom?trico": "geométrico",
    "Geom?trica": "Geométrica",
    "geom?trica": "geométrica",
    "Geom?tricos": "Geométricos",
    "geom?tricos": "geométricos",
    "Caracterizaci?n": "Caracterización",
    "caracterizaci?n": "caracterización",
    "Configuraci?n": "Configuración",
    "configuraci?n": "configuración",
    "Distribuci?n": "Distribución",
    "distribuci?n": "distribución",
    "Comparaci?n": "Comparación",
    "comparaci?n": "comparación",
    "Continuaci?n": "Continuación",
    "continuaci?n": "continuación",
    "Construcci?n": "Construcción",
    "construcci?n": "construcción",
    "Documentaci?n": "Documentación",
    "documentaci?n": "documentación",
    "Definici?n": "Definición",
    "definici?n": "definición",
    "Selecci?n": "Selección",
    "selecci?n": "selección",
    "Direcci?n": "Dirección",
    "direcci?n": "dirección",
    "Direcciones": "Direcciones",
    "e?lico ": "eólico ",
    "estad?stico ": "estadístico ",
    "Interacci?n": "Interacción",
    "interacci?n": "interacción",
    "Representaci?n": "Representación",
    "representaci?n": "representación",
    "Aplicaci?n": "Aplicación",
    "aplicaci?n": "aplicación",
    "Validaci?n": "Validación",
    "validaci?n": "validación",

    # energía y pérdidas
    "Energ?a": "Energía",
    "energ?a": "energía",
    "Energ?tico": "Energético",
    "energ?tico": "energético",
    "Energ?ticos": "Energéticos",
    "energ?ticos": "energéticos",
    "Energ?ticas": "Energéticas",
    "energ?ticas": "energéticas",
    "P?rdida": "Pérdida",
    "p?rdida": "pérdida",
    "P?rdidas": "Pérdidas",
    "p?rdidas": "pérdidas",
    "Perdida": "Pérdida",
    "perdida": "pérdida",
    "Perdidas": "Pérdidas",
    "perdidas": "pérdidas",

    # métricas y tablas
    "M?xima": "Máxima",
    "m?xima": "máxima",
    "M?nima": "Mínima",
    "m?nima": "mínima",
    "N?mero": "Número",
    "n?mero": "número",
    "V?lido": "Válido",
    "v?lido": "válido",
    "V?lidos": "Válidos",
    "v?lidos": "válidos",
    "Est?ndar": "Estándar",
    "est?ndar": "estándar",
    "Te?rica": "Teórica",
    "te?rica": "teórica",
    "Te?rico": "Teórico",
    "te?rico": "teórico",
    "Probabilidad": "Probabilidad",

    # gráficos
    "Gr?fica": "Gráfica",
    "gr?fica": "gráfica",
    "Gr?ficas": "Gráficas",
    "gr?ficas": "gráficas",

    # unidades y años
    "a?o": "año",
    "a?os": "años",
    "A?o": "Año",
    "A?os": "Años",
    "MWh/a?o": "MWh/año",
    "MWh/a?os": "MWh/años",

    # frases frecuentes en tu informe
    "An?lisis geom?trico puro": "Análisis geométrico puro",
    "An?lisis geom?trico puro del arreglo": "Análisis geométrico puro del arreglo",
    "An?lisis anual ponderado": "Análisis anual ponderado",
    "Indicadores geom?tricos clave": "Indicadores geométricos clave",
    "Indicadores resumidos del an?lisis geom?trico puro.": "Indicadores resumidos del análisis geométrico puro.",
    "Distribuci?n polar de la criticidad geom?trica del arreglo.": "Distribución polar de la criticidad geométrica del arreglo.",
    "Distribuci?n polar de p?rdidas ponderadas y criticidad anual.": "Distribución polar de pérdidas ponderadas y criticidad anual.",
    "Resultados energ?ticos": "Resultados energéticos",
    "Resultados energ?ticos consolidados del proyecto, incluyendo AEP, factor de planta y distribuci?n de p?rdidas.": "Resultados energéticos consolidados del proyecto, incluyendo AEP, factor de planta y distribución de pérdidas.",
    "Distribuci?n de p?rdidas (Weibull)": "Distribución de pérdidas (Weibull)",
    "Distribuci?n relativa de p?rdidas energ?ticas para el escenario Weibull.": "Distribución relativa de pérdidas energéticas para el escenario Weibull.",
    "Tabla de p?rdidas energ?ticas": "Tabla de pérdidas energéticas",
    "Detalle de p?rdidas energ?ticas por concepto para el escenario evaluado.": "Detalle de pérdidas energéticas por concepto para el escenario evaluado.",
    "Tabla completa de resultados energ?ticos por sector.": "Tabla completa de resultados energéticos por sector.",
    "Energ?a bruta total": "Energía bruta total",
    "Energ?a con estela total": "Energía con estela total",
    "P?rdida ponderada media": "Pérdida ponderada media",
    "P?rdida Geom?trica media": "Pérdida Geométrica media",
    "P?rdida Geom?trica m?xima": "Pérdida Geométrica máxima",
    "Documentaci?n del layout del parque y del an?lisis de estelas del proyecto.": "Documentación del layout del parque y del análisis de estelas del proyecto.",
    "Vista en planta del parque con posiciones y rotor representado cuando est? disponible.": "Vista en planta del parque con posiciones y rotor representado cuando está disponible.",
}


def _badness_score(text: str) -> int:
    if not text:
        return 0
    score = 0
    score += text.count("Ã") * 10
    score += text.count("Â") * 10
    score += text.count("�") * 15
    score += len(re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]\?[A-Za-zÁÉÍÓÚáéíóúÑñ]", text)) * 8
    return score


def _try_redecode(text: str) -> str:
    candidates = [text]

    for codec in ("latin-1", "cp1252"):
        try:
            candidates.append(text.encode(codec, errors="strict").decode("utf-8", errors="strict"))
        except Exception:
            pass

    return min(candidates, key=_badness_score)


def _apply_direct_replacements(text: str) -> str:
    for bad, good in _DIRECT_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text


def _apply_question_replacements(text: str) -> str:
    for bad, good in _QUESTION_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text


def normalize_visible_text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        return value

    text = html.unescape(value)

    for _ in range(4):
        original = text

        text = _apply_direct_replacements(text)
        text = _try_redecode(text)
        text = _apply_question_replacements(text)

        text = unicodedata.normalize("NFC", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)

        if text == original:
            break

    # barrido final por patrones muy frecuentes que queden sueltos
    text = re.sub(r"\benerg\?a\b", "energía", text, flags=re.IGNORECASE)
    text = re.sub(r"\ban\?lisis\b", "análisis", text, flags=re.IGNORECASE)
    text = re.sub(r"\bgeom\?trico\b", "geométrico", text, flags=re.IGNORECASE)
    text = re.sub(r"\bgeom\?trica\b", "geométrica", text, flags=re.IGNORECASE)
    text = re.sub(r"\bgeom\?tricos\b", "geométricos", text, flags=re.IGNORECASE)
    text = re.sub(r"\bm\?xima\b", "máxima", text, flags=re.IGNORECASE)
    text = re.sub(r"\bp\?rdida\b", "pérdida", text, flags=re.IGNORECASE)
    text = re.sub(r"\bp\?rdidas\b", "pérdidas", text, flags=re.IGNORECASE)
    text = re.sub(r"\bdistribuci\?n\b", "distribución", text, flags=re.IGNORECASE)
    text = re.sub(r"\bdirecci\?n\b", "dirección", text, flags=re.IGNORECASE)
    text = re.sub(r"\bdocumentaci\?n\b", "documentación", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcaracterizaci\?n\b", "caracterización", text, flags=re.IGNORECASE)
    text = re.sub(r"\bconfiguraci\?n\b", "configuración", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcomparaci\?n\b", "comparación", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcontinuaci\?n\b", "continuación", text, flags=re.IGNORECASE)
    text = re.sub(r"\ba\?o\b", "año", text, flags=re.IGNORECASE)
    text = text.replace("MWh/a?o", "MWh/año")
    text = text.replace("MWh/a?os", "MWh/años")

    return text.strip()


def normalize_spanish_text(value):
    return normalize_visible_text(value)


def normalize_headers(headers):
    return [
        normalize_spanish_text(item) if isinstance(item, str) else item
        for item in list(headers or [])
    ]


def normalize_table_cell(value):
    if isinstance(value, str):
        return normalize_spanish_text(value)
    return value


def normalize_text_deep(obj):
    if obj is None:
        return None

    if isinstance(obj, str):
        return normalize_spanish_text(obj)

    if pd is not None and isinstance(obj, pd.DataFrame):
        out = obj.copy()
        out.columns = [
            normalize_spanish_text(col) if isinstance(col, str) else col
            for col in out.columns
        ]
        try:
            out.index = [
                normalize_spanish_text(idx) if isinstance(idx, str) else idx
                for idx in out.index
            ]
        except Exception:
            pass
        for col in out.columns:
            out[col] = out[col].map(
                lambda v: normalize_spanish_text(v) if isinstance(v, str) else v
            )
        return out

    if isinstance(obj, dict):
        return {
            normalize_spanish_text(k) if isinstance(k, str) else k: normalize_text_deep(v)
            for k, v in obj.items()
        }

    if isinstance(obj, list):
        return [normalize_text_deep(item) for item in obj]

    if isinstance(obj, tuple):
        return tuple(normalize_text_deep(item) for item in obj)

    if isinstance(obj, set):
        return {normalize_text_deep(item) for item in obj}

    return obj


__all__ = [
    "normalize_visible_text",
    "normalize_spanish_text",
    "normalize_headers",
    "normalize_table_cell",
    "normalize_text_deep",
]
