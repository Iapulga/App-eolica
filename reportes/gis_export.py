"""Exportación GIS del parque — KML (Google Earth), GeoJSON (QGIS / web), CSV y ZIP.

Las coordenadas WGS84 salen del layout x/y (m) de la Fase 4 alrededor del centro del sitio
(latitud/longitud de la Fase 2). Nombre del parque, diámetro de rotor y altura de buje llegan
como argumentos: todo depende del proyecto activo.
"""

from __future__ import annotations

import io
import json
import math

import pandas as pd

from .datos_proyecto import fmt_num


def _limpio(value, decimales):
    """Redondea y elimina el '-0' de los flotantes (x = -5.5e-14 → 0.0)."""
    try:
        x = round(float(value), decimales)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return 0.0 if x == 0 else x


def turbinas_xy_a_latlon_simple(df_layout, lat_centro, lon_centro):
    """Conversión x_m/y_m → lat/lon con aproximación plana (válida para parques de pocos km)."""
    lat0 = float(lat_centro)
    lon0 = float(lon_centro)
    m_por_grado_lat = 111000.0
    m_por_grado_lon = 111000.0 * math.cos(math.radians(lat0))
    if m_por_grado_lon <= 0:
        m_por_grado_lon = 111000.0
    out = df_layout.copy()
    x = pd.to_numeric(out.get("x_m", 0), errors="coerce")
    y = pd.to_numeric(out.get("y_m", 0), errors="coerce")
    out["x_m"] = [_limpio(v, 2) for v in x]
    out["y_m"] = [_limpio(v, 2) for v in y]
    out["lat"] = [_limpio(lat0 + (v or 0.0) / m_por_grado_lat, 7) for v in out["y_m"]]
    out["lon"] = [_limpio(lon0 + (v or 0.0) / m_por_grado_lon, 7) for v in out["x_m"]]
    return out


def _kml_escape(s: str) -> str:
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _descripcion(lineas) -> str:
    """Descripción HTML (Google Earth respeta <br/> dentro de CDATA)."""
    cuerpo = "<br/>".join(_kml_escape(linea) for linea in lineas if linea)
    return f"<![CDATA[{cuerpo}]]>"


def exportar_kml_layout(
    df_layout, lat_centro, lon_centro,
    nombre_parque="Parque eólico", diametro_rotor=100, altura_buje=80,
    receptores_flicker=None, receptores_ruido=None,
    polygon_concesion_xy=None,
):
    """KML para Google Earth: centro del sitio, un pin por aerogenerador (con su ficha),
    receptores de parpadeo/ruido y área de concesión opcionales. Devuelve bytes UTF-8."""
    # Colores KML: aabbggrr
    MORADO = "ffff0078"
    AZUL = "ffff0000"
    AMARILLO = "ff00ffff"
    ROJO = "ff0000ff"
    d_txt = f"{fmt_num(diametro_rotor, 1)} m"
    h_txt = f"{fmt_num(altura_buje, 1)} m"

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '<Document>',
        f'  <name>{_kml_escape(nombre_parque)}</name>',
        '  <description>' + _descripcion([
            f"Parque eólico: {nombre_parque}",
            f"Centro del sitio: {fmt_num(lat_centro, 6)}, {fmt_num(lon_centro, 6)}",
            f"Diámetro de rotor: {d_txt}",
            f"Altura de buje: {h_txt}",
            "Generado por SMA 2.0",
        ]) + '</description>',
        '  <Style id="estilo_centro"><IconStyle><color>' + MORADO + '</color><scale>1.1</scale></IconStyle></Style>',
        '  <Style id="estilo_turbina"><IconStyle><color>' + AZUL + '</color><scale>1.0</scale></IconStyle></Style>',
        '  <Style id="estilo_parpadeo"><IconStyle><color>' + AMARILLO + '</color><scale>1.0</scale></IconStyle></Style>',
        '  <Style id="estilo_ruido"><IconStyle><color>' + ROJO + '</color><scale>1.0</scale></IconStyle></Style>',
        '  <Style id="estilo_concesion"><LineStyle><color>' + AMARILLO + '</color><width>2</width></LineStyle>'
        '<PolyStyle><color>3200ffff</color></PolyStyle></Style>',
        '  <Placemark>',
        '    <name>Centro del sitio</name>',
        '    <description>' + _descripcion([
            "Punto de referencia del sitio (Fase 2)",
            f"Latitud: {fmt_num(lat_centro, 6)}",
            f"Longitud: {fmt_num(lon_centro, 6)}",
        ]) + '</description>',
        '    <styleUrl>#estilo_centro</styleUrl>',
        f'    <Point><coordinates>{float(lon_centro):.7f},{float(lat_centro):.7f},0</coordinates></Point>',
        '  </Placemark>',
    ]

    df_ll = turbinas_xy_a_latlon_simple(df_layout, lat_centro, lon_centro)
    lines.append('  <Folder>')
    lines.append('    <name>Aerogeneradores</name>')
    for _, row in df_ll.iterrows():
        tid = str(row.get("turbina_id", "T?"))
        lat_t, lon_t = float(row["lat"]), float(row["lon"])
        lines += [
            '    <Placemark>',
            f'      <name>{_kml_escape(tid)}</name>',
            '      <description>' + _descripcion([
                f"Aerogenerador: {tid}",
                f"Latitud: {fmt_num(lat_t, 6)} · Longitud: {fmt_num(lon_t, 6)}",
                f"Posición en el layout: x = {fmt_num(row.get('x_m'), 1)} m · y = {fmt_num(row.get('y_m'), 1)} m",
                f"Altura de buje: {h_txt} · Diámetro de rotor: {d_txt}",
            ]) + '</description>',
            '      <styleUrl>#estilo_turbina</styleUrl>',
            f'      <Point><coordinates>{lon_t:.7f},{lat_t:.7f},0</coordinates></Point>',
            '    </Placemark>',
        ]
    lines.append('  </Folder>')

    if polygon_concesion_xy and len(polygon_concesion_xy) >= 3:
        df_poly = pd.DataFrame({"turbina_id": ["P"] * len(polygon_concesion_xy),
                                "x_m": [p[0] for p in polygon_concesion_xy],
                                "y_m": [p[1] for p in polygon_concesion_xy]})
        df_poly_ll = turbinas_xy_a_latlon_simple(df_poly, lat_centro, lon_centro)
        coords = [(float(r["lon"]), float(r["lat"])) for _, r in df_poly_ll.iterrows()]
        coords.append(coords[0])
        coord_str = " ".join(f"{lon:.7f},{lat:.7f},0" for lon, lat in coords)
        lines += [
            '  <Placemark>',
            '    <name>Área de concesión</name>',
            '    <styleUrl>#estilo_concesion</styleUrl>',
            '    <Polygon><outerBoundaryIs><LinearRing>',
            f'      <coordinates>{coord_str}</coordinates>',
            '    </LinearRing></outerBoundaryIs></Polygon>',
            '  </Placemark>',
        ]

    def _receptores(titulo, prefijo, estilo, receptores, dato):
        if not receptores:
            return
        lines.append('  <Folder>')
        lines.append(f'    <name>{titulo}</name>')
        for rec in receptores:
            rid = rec.get("receptor_id", "R?")
            df_rec = pd.DataFrame({"turbina_id": [rid], "x_m": [rec.get("x_m", 0)], "y_m": [rec.get("y_m", 0)]})
            fila = turbinas_xy_a_latlon_simple(df_rec, lat_centro, lon_centro).iloc[0]
            nombre = rec.get("nombre", rid)
            lines.extend([  # extend (no «+=»): «lines» es de la función exterior
                '    <Placemark>',
                f'      <name>{prefijo}: {_kml_escape(nombre)}</name>',
                '      <description>' + _descripcion([f"Receptor: {nombre}", dato(rec)]) + '</description>',
                f'      <styleUrl>#{estilo}</styleUrl>',
                f'      <Point><coordinates>{float(fila["lon"]):.7f},{float(fila["lat"]):.7f},0</coordinates></Point>',
                '    </Placemark>',
            ])
        lines.append('  </Folder>')

    _receptores("Receptores de parpadeo de sombra", "Parpadeo", "estilo_parpadeo", receptores_flicker,
                lambda r: f"Horas de parpadeo al año: {fmt_num(r.get('horas_flicker_anuales'), 1)}")
    _receptores("Receptores de ruido", "Ruido", "estilo_ruido", receptores_ruido,
                lambda r: f"Nivel de presión sonora: {fmt_num(r.get('lpA_db'), 1)} dB(A)")

    lines += ['</Document>', '</kml>']
    return "\n".join(lines).encode("utf-8")


def exportar_geojson_layout(df_layout, lat_centro, lon_centro, nombre_parque="WindFarm", metadata=None,
                            diametro_rotor=None, altura_buje=None):
    """GeoJSON FeatureCollection (RFC 7946, lon/lat WGS84) — estándar web/GIS."""
    df_ll = turbinas_xy_a_latlon_simple(df_layout, lat_centro, lon_centro)
    extra = {}
    if diametro_rotor is not None:
        extra["diametro_rotor_m"] = _limpio(diametro_rotor, 2)
    if altura_buje is not None:
        extra["altura_buje_m"] = _limpio(altura_buje, 2)
    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [_limpio(lon_centro, 7), _limpio(lat_centro, 7)]},
        "properties": {"nombre": f"{nombre_parque} · centro del sitio", "tipo": "centro_sitio"},
    }]
    for _, row in df_ll.iterrows():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {"nombre": str(row.get("turbina_id", "T?")), "tipo": "aerogenerador",
                           "x_m": row.get("x_m"), "y_m": row.get("y_m"), **extra},
        })
    payload = {
        "type": "FeatureCollection",
        "name": nombre_parque,
        "metadata": {**(metadata or {}), "centro": [_limpio(lon_centro, 7), _limpio(lat_centro, 7)],
                     "n_aerogeneradores": int(len(df_ll)), **extra},
        "features": features,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


def exportar_csv_coords(df_layout, lat_centro, lon_centro, separador=",", diametro_rotor=None, altura_buje=None):
    """CSV con coordenadas WGS84 (punto decimal: formato estándar para QGIS / GIS)."""
    df_ll = turbinas_xy_a_latlon_simple(df_layout, lat_centro, lon_centro)
    cols = [c for c in ["turbina_id", "lat", "lon", "x_m", "y_m"] if c in df_ll.columns]
    out = df_ll[cols].copy()
    if altura_buje is not None:
        out["altura_buje_m"] = _limpio(altura_buje, 2)
    if diametro_rotor is not None:
        out["diametro_rotor_m"] = _limpio(diametro_rotor, 2)
    return out.to_csv(index=False, sep=separador).encode("utf-8-sig")


_LEEME = """Paquete GIS del parque — {nombre}

Archivos:
- {nombre}.kml          → abrir en Google Earth (pines por aerogenerador con su ficha).
- {nombre}.geojson      → arrastrar a QGIS o a un visor web (WGS84, lon/lat).
- {nombre}_coords.csv   → coordenadas por aerogenerador (punto decimal; en QGIS: Capa > Añadir capa de texto delimitado).

Las coordenadas se calculan desde el layout x/y (m) de la Fase 4 alrededor del centro del
sitio de la Fase 2 (aproximación plana, válida para parques de pocos kilómetros).
Generado por SMA 2.0.
"""


def exportar_zip_paquete_gis(df_layout, lat_centro, lon_centro, nombre_parque="WindFarm", **kwargs):
    """ZIP con KML + GeoJSON + CSV + LEEME — paquete GIS completo para descarga."""
    import zipfile
    diametro = kwargs.get("diametro_rotor")
    altura = kwargs.get("altura_buje")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{nombre_parque}.kml", exportar_kml_layout(df_layout, lat_centro, lon_centro, nombre_parque=nombre_parque, **kwargs))
        zf.writestr(f"{nombre_parque}.geojson", exportar_geojson_layout(df_layout, lat_centro, lon_centro, nombre_parque=nombre_parque,
                                                                        diametro_rotor=diametro, altura_buje=altura))
        zf.writestr(f"{nombre_parque}_coords.csv", exportar_csv_coords(df_layout, lat_centro, lon_centro,
                                                                       diametro_rotor=diametro, altura_buje=altura))
        zf.writestr("LEEME.txt", _LEEME.format(nombre=nombre_parque))
    buffer.seek(0)
    return buffer.read()
