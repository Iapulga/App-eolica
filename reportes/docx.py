import io
import math
import os
import re
import unicodedata
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from .texto import normalize_headers, normalize_spanish_text

DOCX_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "rels": "http://schemas.openxmlformats.org/package/2006/relationships",
}

EMU_PER_PIXEL = 9525
MAX_IMAGE_WIDTH_EMU = int(6.2 * 914400)
MAX_IMAGE_HEIGHT_EMU = int(4.8 * 914400)


def _xml(text):
    return escape(str(text or ""), {'"': "&quot;"})


def _clean_text(text):
    return normalize_spanish_text(text).replace("\r\n", "\n").replace("\r", "\n")


def _safe_media_name(file_name, default_stem="figure", default_ext=".png"):
    raw_name = str(file_name or "").strip()
    if not raw_name:
        raw_name = f"{default_stem}{default_ext}"

    base_name = raw_name.replace("\\", "/").split("/")[-1]
    stem, ext = os.path.splitext(base_name)
    ext = (ext or default_ext or ".png").lower()
    if not re.fullmatch(r"\.[a-z0-9]+", ext):
        ext = default_ext or ".png"

    stem = unicodedata.normalize("NFKD", stem)
    stem = stem.encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("._-") or default_stem
    return f"{stem}{ext}"


def _paragraph(text, style=None, spacing_before=0, spacing_after=120, jc=None, bold=False, keep_next=False):
    text = _clean_text(text)
    runs = []
    for line in text.split("\n") if text else [""]:
        run_props = "<w:rPr>"
        if bold:
            run_props += "<w:b/>"
        run_props += "</w:rPr>"
        runs.append(f"<w:r>{run_props}<w:t xml:space=\"preserve\">{_xml(line)}</w:t></w:r>")
        runs.append("<w:r><w:br/></w:r>")
    if runs:
        runs = runs[:-1]
    ppr = []
    if style:
        ppr.append(f"<w:pStyle w:val=\"{style}\"/>")
    if keep_next:
        ppr.append("<w:keepNext/>")
    ppr.append(f"<w:spacing w:before=\"{int(spacing_before)}\" w:after=\"{int(spacing_after)}\"/>")
    if jc:
        ppr.append(f"<w:jc w:val=\"{jc}\"/>")
    return f"<w:p><w:pPr>{''.join(ppr)}</w:pPr>{''.join(runs)}</w:p>"


_RE_NUMERO_CELDA = re.compile(r"^[−\-+]?\d[\d.,]*(\s?%)?$")
_CELDAS_VACIAS = {"", "—", "–", "-", "n/d", "N/D"}


def _columnas_numericas(rows, ncols):
    """Columnas cuyas celdas son todas cifras (o guiones): se alinean enteras a la derecha."""
    derecha = []
    for j in range(ncols):
        valores = [_clean_text(fila[j]).strip() for fila in rows if j < len(fila)]
        valores = [v for v in valores if v not in _CELDAS_VACIAS]
        derecha.append(bool(valores) and all(_RE_NUMERO_CELDA.match(v) for v in valores))
    return derecha


def _table_cell(text, header=False, banded=False, size=20, width=None, sep=False, keep=False, derecha=False):
    """Celda DOCX con estilo profesional.

    header=True: fondo navy #1F4E79 + texto blanco bold + centro
    banded=True: fondo gris claro #F2F6FB (filas alternas)
    """
    text_value = _xml(_clean_text(text))
    if header:
        shading = '<w:shd w:val="clear" w:color="auto" w:fill="1B365D"/>'
        run_pr = f'<w:rPr><w:b/><w:color w:val="FFFFFF"/><w:sz w:val="{int(size)}"/></w:rPr>'
        para_pr = '<w:pPr><w:keepNext/><w:spacing w:before="40" w:after="40" w:line="240" w:lineRule="auto"/><w:jc w:val="center"/></w:pPr>'
    else:
        shading = '<w:shd w:val="clear" w:color="auto" w:fill="F3F6F9"/>' if banded else ""
        run_pr = f'<w:rPr><w:color w:val="2B3645"/><w:sz w:val="{int(size)}"/></w:rPr>'
        para_pr = ('<w:pPr>' + ('<w:keepNext/>' if keep else '') + '<w:spacing w:before="0" w:after="30" w:line="240" w:lineRule="auto"/>'
                   + ('<w:jc w:val="right"/>' if derecha else "") + "</w:pPr>")
    tc_w = f'<w:tcW w:w="{int(width)}" w:type="dxa"/>' if width else '<w:tcW w:w="0" w:type="auto"/>'
    borde = '<w:tcBorders><w:left w:val="single" w:sz="12" w:space="0" w:color="1F4E79"/></w:tcBorders>' if sep else ""
    tc_pr = (
        "<w:tcPr>"
        f"{tc_w}"
        f"{borde}"
        f"{shading}"
        '<w:tcMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
        '<w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar>'
        '<w:vAlign w:val="center"/>'
        "</w:tcPr>"
    )
    return (
        "<w:tc>"
        f"{tc_pr}"
        f"<w:p>{para_pr}"
        f"<w:r>{run_pr}<w:t xml:space=\"preserve\">{text_value}</w:t></w:r>"
        "</w:p>"
        "</w:tc>"
    )


def _table_chunk_size(block):
    headers = list((block or {}).get("headers", []) or [])
    family = str((block or {}).get("table_family") or "").strip().lower()
    num_cols = len(headers)
    if family in ["wide_sector_table", "phase4_detail_table", "phase5_sector_table"]:
        return 10
    if family == "split_horizontal":
        # 3 columnas lado a lado → chunk size 11 (33 rows total fit en 1 pagina)
        return 11
    if num_cols >= 8:
        return 8
    if num_cols >= 6:
        return 11
    if num_cols >= 4:
        return 16
    return 22


_BORDES_TABLA = (  # estilo formal: reglas horizontales, sin líneas verticales
    '<w:tblBorders>'
    '<w:top w:val="single" w:sz="8" w:space="0" w:color="1B365D"/>'
    '<w:left w:val="nil"/>'
    '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="1B365D"/>'
    '<w:right w:val="nil"/>'
    '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="C9D2DC"/>'
    '<w:insideV w:val="nil"/>'
    "</w:tblBorders>"
)
_TBL_LOOK = '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1" w:lastColumn="0" w:noHBand="0" w:noVBand="1"/>'
_ANCHO_UTIL_TWIPS = 9360  # 6,5 in de texto (carta con márgenes de 1 in)


def _table_side_by_side(block, max_cols=8):
    """Tabla larga y estrecha (p. ej. curva de potencia) repartida en grupos lado a lado dentro
    de UNA sola tabla de ancho fijo = ancho útil de la página: nunca se sale del margen."""
    headers = list(normalize_headers((block or {}).get("headers", []) or []))
    rows = list((block or {}).get("rows", []) or [])
    ncols = len(headers)
    if not headers or not rows:
        return _table_block({**(block or {}), "headers": headers})
    grupos = max(1, min(4, max_cols // max(1, ncols)))
    por_grupo = math.ceil(len(rows) / grupos)
    grupos = math.ceil(len(rows) / por_grupo)
    total = grupos * ncols
    size = 16 if total >= 9 else 18
    ancho = _ANCHO_UTIL_TWIPS // total
    grid = "".join(f'<w:gridCol w:w="{ancho}"/>' for _ in range(total))
    celdas = [_table_cell(h, header=True, size=size, width=ancho, sep=(g > 0 and j == 0))
              for g in range(grupos) for j, h in enumerate(headers)]
    filas = ['<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>' + "".join(celdas) + "</w:tr>"]
    derecha = _columnas_numericas(rows, ncols)
    for r in range(por_grupo):
        celdas = []
        for g in range(grupos):
            idx = g * por_grupo + r
            fila = list(rows[idx]) if idx < len(rows) else [""] * ncols
            fila += [""] * max(0, ncols - len(fila))
            celdas += [_table_cell(fila[j], banded=(r % 2 == 1), size=size, width=ancho, sep=(g > 0 and j == 0),
                                   derecha=derecha[j]) for j in range(ncols)]
        filas.append("<w:tr><w:trPr><w:cantSplit/></w:trPr>" + "".join(celdas) + "</w:tr>")
    return (
        "<w:tbl><w:tblPr>"
        '<w:tblStyle w:val="TableGrid"/>'
        '<w:tblW w:w="5000" w:type="pct"/>'
        f"{_BORDES_TABLA}"
        '<w:tblLayout w:type="fixed"/>'
        f"{_TBL_LOOK}"
        f"</w:tblPr><w:tblGrid>{grid}</w:tblGrid>"
        + "".join(filas)
        + "</w:tbl>"
    )


def _table_split_blocks(block):
    headers = list(normalize_headers((block or {}).get("headers", []) or []))
    rows = list((block or {}).get("rows", []) or [])
    if not headers:
        return []
    chunk_size = _table_chunk_size(block)
    if len(rows) <= chunk_size:
        chunk = dict(block)
        chunk["headers"] = headers
        return [chunk]

    chunks = []
    for start in range(0, len(rows), chunk_size):
        chunk = dict(block)
        chunk["headers"] = headers
        chunk["rows"] = rows[start:start + chunk_size]
        if start > 0:
            chunk["title"] = f"{block.get('title', 'Tabla')} (continuación)"
            chunk["description"] = "Continuación de la tabla anterior."
        chunks.append(chunk)
    return chunks


def _table_block(block):
    """Tabla con cabecera que se repite en cada página y filas que no se parten entre páginas.
    Las tablas anchas ocupan todo el ancho útil y usan letra más pequeña."""
    headers = list(block.get("headers", []) or [])
    rows = list(block.get("rows", []) or [])
    if not headers:
        return ""
    ncols = len(headers)
    size = 16 if ncols >= 9 else (18 if ncols >= 6 else 20)
    ancho = '<w:tblW w:w="5000" w:type="pct"/>' if ncols >= 5 else '<w:tblW w:w="0" w:type="auto"/>'
    tbl_rows = [
        '<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>'
        + "".join(_table_cell(h, header=True, size=size) for h in headers)
        + "</w:tr>"
    ]
    juntar = len(rows) <= 20  # las tablas cortas no se parten entre páginas (ni dejan el encabezado solo)
    derecha = _columnas_numericas(rows, ncols)
    for idx, row in enumerate(rows):
        padded = list(row) + [""] * max(0, ncols - len(row))
        mantener = juntar and idx < len(rows) - 1
        tbl_rows.append(
            "<w:tr><w:trPr><w:cantSplit/></w:trPr>"
            + "".join(_table_cell(cell, header=False, banded=(idx % 2 == 1), size=size, keep=mantener, derecha=derecha[j])
                      for j, cell in enumerate(padded[:ncols]))
            + "</w:tr>"
        )
    return (
        "<w:tbl><w:tblPr>"
        '<w:tblStyle w:val="TableGrid"/>'
        f"{ancho}"
        f"{_BORDES_TABLA}"
        f"{_TBL_LOOK}"
        "</w:tblPr><w:tblGrid/>"
        + "".join(tbl_rows)
        + "</w:tbl>"
    )


_TAMANOS_FIGURA_IN = {
    "phase2_time_series": (6.5, 3.4),
    "phase2_profile": (4.4, 3.1),  # dos perfiles por página
    "phase2_comparison": (6.0, 3.4),
    "phase3_wind_rose": (5.0, 4.5),
    "phase4_polar": (4.8, 4.4),
    "phase5_loss_distribution": (4.8, 4.1),
    "phase3_histogram": (6.4, 4.2),
    "phase35_probability_curve": (6.4, 4.2),
    "phase4_comparison": (6.4, 3.9),
    "phase4_energy": (6.4, 3.9),
    "phase5_sector_chart": (6.4, 3.9),
    "phase35_heatmap": (6.4, 4.6),
    "phase4_layout": (5.4, 4.3),
    "phase4_direction_detail": (5.2, 4.2),
    "diagrama": (6.3, 3.6),
    "phase3_histogram_grid": (6.5, 5.9),
    "phase35_probability_grid": (6.5, 5.9),
}


def _image_constraints_for_block(block):
    family = str((block or {}).get("figure_family") or "").strip().lower()
    ancho, alto = _TAMANOS_FIGURA_IN.get(family, (6.2, 4.4))
    return int(ancho * 914400), int(alto * 914400)


def _image_dimensions(image_bytes, block=None):
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        image = Image.open(io.BytesIO(image_bytes))
        width_px, height_px = image.size
        width_emu = width_px * EMU_PER_PIXEL
        height_emu = height_px * EMU_PER_PIXEL
        max_width_emu, max_height_emu = _image_constraints_for_block(block)
        scale = min(max_width_emu / width_emu, max_height_emu / height_emu, 1.0)
        return int(width_emu * scale), int(height_emu * scale)
    except Exception:
        return None


def _image_paragraph(rel_id, image_name, cx, cy, doc_pr_id):
    return f"""
<w:p>
  <w:pPr><w:keepNext/><w:jc w:val="center"/><w:spacing w:before="80" w:after="40"/></w:pPr>
  <w:r>
    <w:drawing>
      <wp:inline distT="0" distB="0" distL="0" distR="0">
        <wp:extent cx="{cx}" cy="{cy}"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:docPr id="{doc_pr_id}" name="{_xml(image_name)}"/>
        <wp:cNvGraphicFramePr/>
        <a:graphic xmlns:a="{DOCX_NS['a']}">
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
            <pic:pic xmlns:pic="{DOCX_NS['pic']}">
              <pic:nvPicPr>
                <pic:cNvPr id="{doc_pr_id}" name="{_xml(image_name)}"/>
                <pic:cNvPicPr/>
              </pic:nvPicPr>
              <pic:blipFill>
                <a:blip r:embed="{rel_id}"/>
                <a:stretch><a:fillRect/></a:stretch>
              </pic:blipFill>
              <pic:spPr>
                <a:xfrm>
                  <a:off x="0" y="0"/>
                  <a:ext cx="{cx}" cy="{cy}"/>
                </a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
              </pic:spPr>
            </pic:pic>
          </a:graphicData>
        </a:graphic>
      </wp:inline>
    </w:drawing>
  </w:r>
</w:p>
"""


def _styles_xml():
    """Estilo formal común de los entregables (ver reportes/estilo.py): Calibri 10,5 pt, interlineado 1,15,
    títulos en azul marino con filete, rótulos de tabla y figura, índice compacto."""
    marino, texto, gris = "1B365D", "2B3645", "6B7785"
    fuente = '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/>'

    def titulo(style_id, nombre, tam, antes, despues, nivel, color=marino, filete=False):
        borde = f'<w:pBdr><w:bottom w:val="single" w:sz="8" w:space="3" w:color="{marino}"/></w:pBdr>' if filete else ""
        salto = "<w:pageBreakBefore/>" if style_id == "Heading1" else ""  # cada capítulo empieza en página nueva
        return (f'<w:style w:type="paragraph" w:styleId="{style_id}"><w:name w:val="{nombre}"/><w:basedOn w:val="Normal"/>'
                f'<w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:keepLines/>{salto}{borde}'
                f'<w:spacing w:before="{antes}" w:after="{despues}" w:line="259" w:lineRule="auto"/>'
                f'<w:outlineLvl w:val="{nivel}"/></w:pPr><w:rPr>{fuente}<w:b/><w:color w:val="{color}"/>'
                f'<w:sz w:val="{tam}"/><w:szCs w:val="{tam}"/></w:rPr></w:style>')

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{DOCX_NS['w']}">
  <w:docDefaults>
    <w:rPrDefault><w:rPr>{fuente}<w:color w:val="{texto}"/><w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="es-ES"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/><w:qFormat/>
    <w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr>
    <w:rPr>{fuente}<w:color w:val="{texto}"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:spacing w:before="120" w:after="240"/></w:pPr>
    <w:rPr>{fuente}<w:b/><w:color w:val="{marino}"/><w:sz w:val="52"/></w:rPr>
  </w:style>
  {titulo("Heading1", "heading 1", 30, 360, 160, 0, filete=True)}
  {titulo("Heading2", "heading 2", 24, 240, 100, 1)}
  {titulo("Heading3", "heading 3", 22, 180, 80, 2, color="2F5F8F")}
  <w:style w:type="paragraph" w:styleId="TOCTitulo">
    <w:name w:val="Titulo del indice"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
    <w:pPr><w:keepNext/><w:pBdr><w:bottom w:val="single" w:sz="8" w:space="3" w:color="{marino}"/></w:pBdr>
      <w:spacing w:before="120" w:after="200"/></w:pPr>
    <w:rPr>{fuente}<w:b/><w:color w:val="{marino}"/><w:sz w:val="30"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Caption">
    <w:name w:val="caption"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:pPr><w:spacing w:before="60" w:after="120" w:line="240" w:lineRule="auto"/></w:pPr>
    <w:rPr>{fuente}<w:color w:val="{texto}"/><w:sz w:val="18"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="TOC1">
    <w:name w:val="toc 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
    <w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9350"/></w:tabs><w:spacing w:before="80" w:after="40"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="{marino}"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="TOC2">
    <w:name w:val="toc 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
    <w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9350"/></w:tabs><w:spacing w:before="0" w:after="30"/><w:ind w:left="300"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="TOC3">
    <w:name w:val="toc 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
    <w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9350"/></w:tabs><w:spacing w:before="0" w:after="20"/><w:ind w:left="600"/></w:pPr>
    <w:rPr><w:sz w:val="19"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Header">
    <w:name w:val="header"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>
    <w:rPr>{fuente}<w:sz w:val="16"/><w:color w:val="{gris}"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Footer">
    <w:name w:val="footer"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>
    <w:rPr>{fuente}<w:sz w:val="16"/><w:color w:val="{gris}"/></w:rPr>
  </w:style>
</w:styles>
"""


def _content_types_xml(has_images):
    image_default = '<Default Extension="png" ContentType="image/png"/>' if has_images else ""
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  {image_default}
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
</Types>
"""


def _content_types_xml_with_header_footer(has_images):
    image_default = '<Default Extension="png" ContentType="image/png"/>' if has_images else ""
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  {image_default}
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
</Types>
"""


def _root_rels_xml():
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{DOCX_NS['rels']}">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""


def _settings_xml():
    """Settings con updateFields=true para auto-refresh TOC al abrir Word."""
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="{DOCX_NS['w']}">
  <w:zoom w:percent="100"/>
  <w:updateFields w:val="true"/>
  <w:defaultTabStop w:val="708"/>
  <w:characterSpacingControl w:val="doNotCompress"/>
</w:settings>
"""


def _header_xml(project_name):
    """Encabezado: proyecto e «INFORME TÉCNICO» a la izquierda, SMA 2.0 a la derecha, con filete inferior."""
    safe_name = _xml(_clean_text(project_name or "Proyecto eólico"))
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="{DOCX_NS['w']}">
  <w:p>
    <w:pPr>
      <w:pStyle w:val="Header"/>
      <w:pBdr><w:bottom w:val="single" w:sz="6" w:space="4" w:color="C9D2DC"/></w:pBdr>
      <w:tabs><w:tab w:val="right" w:pos="9360"/></w:tabs>
    </w:pPr>
    <w:r><w:rPr><w:b/><w:color w:val="1B365D"/><w:sz w:val="16"/></w:rPr><w:t xml:space="preserve">{safe_name}  ·  INFORME TÉCNICO</w:t></w:r>
    <w:r><w:rPr><w:color w:val="6B7785"/><w:sz w:val="16"/></w:rPr><w:tab/><w:t xml:space="preserve">SMA 2.0</w:t></w:r>
  </w:p>
</w:hdr>
"""


def _footer_xml():
    """Pie: «Página X de Y» (campos PAGE y NUMPAGES) con filete superior."""
    corrida = '<w:r><w:rPr><w:color w:val="6B7785"/><w:sz w:val="16"/></w:rPr>{}</w:r>'
    campo = lambda nombre: "".join((  # noqa: E731
        corrida.format('<w:fldChar w:fldCharType="begin"/>'),
        corrida.format(f'<w:instrText xml:space="preserve"> {nombre} </w:instrText>'),
        corrida.format('<w:fldChar w:fldCharType="separate"/>'),
        corrida.format("<w:t>1</w:t>"),
        corrida.format('<w:fldChar w:fldCharType="end"/>'),
    ))
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{DOCX_NS['w']}">
  <w:p>
    <w:pPr>
      <w:pStyle w:val="Footer"/>
      <w:pBdr><w:top w:val="single" w:sz="6" w:space="4" w:color="C9D2DC"/></w:pBdr>
      <w:jc w:val="center"/>
    </w:pPr>
    {corrida.format('<w:t xml:space="preserve">Página </w:t>')}{campo("PAGE")}{corrida.format('<w:t xml:space="preserve"> de </w:t>')}{campo("NUMPAGES")}
  </w:p>
</w:ftr>
"""


def _rotulo_xml(etiqueta, numero, texto, centrado=False):
    """Rótulo «Tabla N. …» (encima de la tabla) o «Figura N. …» (debajo de la figura) con campo SEQ."""
    ppr = ('<w:pPr><w:pStyle w:val="Caption"/>' + ("" if centrado else "<w:keepNext/>")
           + f'<w:spacing w:before="{40 if centrado else 140}" w:after="{180 if centrado else 60}"/>'
           + ('<w:jc w:val="center"/>' if centrado else "") + "</w:pPr>")
    negrita = '<w:rPr><w:b/><w:color w:val="1B365D"/></w:rPr>'
    return (f"<w:p>{ppr}"
            f'<w:r>{negrita}<w:t xml:space="preserve">{etiqueta} </w:t></w:r>'
            f'<w:fldSimple w:instr=" SEQ {etiqueta} \\* ARABIC "><w:r>{negrita}<w:t>{numero}</w:t></w:r></w:fldSimple>'
            f'<w:r>{negrita}<w:t xml:space="preserve">. </w:t></w:r>'
            f'<w:r><w:t xml:space="preserve">{_xml(_clean_text(texto))}</w:t></w:r></w:p>')


def _portada_xml(model):
    """Portada formal: banda azul marino con el título, proyecto, ubicación, datos clave y aviso."""
    titulo = _xml(_clean_text(model.get("cover_title") or "INFORME TÉCNICO"))
    subtitulo = _xml(_clean_text(model.get("cover_subtitle") or model.get("title") or ""))
    proyecto = _xml(_clean_text(model.get("project_name") or ""))
    banda = (
        '<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/><w:jc w:val="center"/>'
        '<w:tblBorders><w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/>'
        '<w:insideH w:val="nil"/><w:insideV w:val="nil"/></w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr>'
        '<w:tblGrid><w:gridCol w:w="9360"/></w:tblGrid><w:tr><w:tc><w:tcPr><w:tcW w:w="9360" w:type="dxa"/>'
        '<w:shd w:val="clear" w:color="auto" w:fill="1B365D"/><w:tcMar><w:top w:w="380" w:type="dxa"/>'
        '<w:left w:w="380" w:type="dxa"/><w:bottom w:w="340" w:type="dxa"/><w:right w:w="380" w:type="dxa"/></w:tcMar></w:tcPr>'
        f'<w:p><w:pPr><w:spacing w:before="0" w:after="80"/></w:pPr><w:r><w:rPr><w:b/><w:color w:val="FFFFFF"/>'
        f'<w:sz w:val="52"/></w:rPr><w:t xml:space="preserve">{titulo}</w:t></w:r></w:p>'
        f'<w:p><w:pPr><w:spacing w:before="0" w:after="0"/></w:pPr><w:r><w:rPr><w:color w:val="D6DEE9"/>'
        f'<w:sz w:val="24"/></w:rPr><w:t xml:space="preserve">{subtitulo}</w:t></w:r></w:p>'
        "</w:tc></w:tr></w:tbl>"
    )
    partes = ['<w:p><w:pPr><w:spacing w:before="0" w:after="360"/></w:pPr></w:p>', banda,
              f'<w:p><w:pPr><w:spacing w:before="420" w:after="60"/></w:pPr><w:r><w:rPr><w:b/><w:color w:val="1B365D"/>'
              f'<w:sz w:val="44"/></w:rPr><w:t xml:space="preserve">{proyecto}</w:t></w:r></w:p>']
    if model.get("cover_line"):
        partes.append(f'<w:p><w:pPr><w:spacing w:before="0" w:after="360"/></w:pPr><w:r><w:rPr><w:color w:val="6B7785"/>'
                      f'<w:sz w:val="22"/></w:rPr><w:t xml:space="preserve">{_xml(_clean_text(model["cover_line"]))}</w:t></w:r></w:p>')
    if model.get("cover_rows"):
        partes.append(_table_block({"headers": ["Campo", "Valor"], "rows": model["cover_rows"], "table_family": "compact_summary"}))
    for parrafo in model.get("intro_paragraphs") or []:
        partes.append(_paragraph(parrafo, spacing_before=160, spacing_after=100, jc="both"))
    partes.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
    return "".join(partes)


def _toc_paragraph_xml():
    """Campo TOC auto-actualizable. Word lo llena al abrir + F9."""
    return (
        "<w:p>"
        "<w:pPr><w:pStyle w:val=\"TOCTitulo\"/></w:pPr>"
        "<w:r><w:t xml:space=\"preserve\">Tabla de contenido</w:t></w:r>"
        "</w:p>"
        "<w:p>"
        "<w:r><w:fldChar w:fldCharType=\"begin\" w:dirty=\"true\"/></w:r>"
        "<w:r><w:instrText xml:space=\"preserve\"> TOC \\o &quot;1-3&quot; \\h \\z \\u </w:instrText></w:r>"
        "<w:r><w:fldChar w:fldCharType=\"separate\"/></w:r>"
        "<w:r><w:t>El índice se completa automáticamente al abrir el documento en Word.</w:t></w:r>"
        "<w:r><w:fldChar w:fldCharType=\"end\"/></w:r>"
        "</w:p>"
        "<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>"
    )


def build_informe_tecnico_docx(report_model, file_name="informe_tecnico.docx"):
    result = {
        "success": False,
        "docx_bytes": None,
        "file_name": file_name,
        "message": "",
    }
    try:
        body_parts = []
        relationships = [
            (
                "rIdStyles",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
                "styles.xml",
            ),
            (
                "rIdSettings",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings",
                "settings.xml",
            ),
            (
                "rIdHeader1",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header",
                "header1.xml",
            ),
            (
                "rIdFooter1",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer",
                "footer1.xml",
            ),
        ]
        media_files = []
        doc_pr_id = 1

        project_name = report_model.get("project_name")
        body_parts.append(_portada_xml(report_model))
        numeros = {"tabla": 0, "figura": 0}

        # TOC auto despues de intro
        body_parts.append(_toc_paragraph_xml())

        for section in report_model.get("sections", []) or []:
            body_parts.append(_paragraph(section.get("title", "Sección"), style="Heading1"))
            if section.get("description"):
                body_parts.append(_paragraph(section.get("description"), jc="both"))
            for subsection in section.get("subsections", []) or []:
                if str(subsection.get("title") or "").strip():
                    body_parts.append(_paragraph(subsection.get("title"), style="Heading2"))
                for block in subsection.get("blocks", []) or []:
                    if not block:
                        continue
                    block_title = block.get("title")
                    block_desc = block.get("description")
                    if block.get("type") == "paragraph":
                        body_parts.append(_paragraph(block.get("text", ""), spacing_after=100, jc="both"))
                        continue
                    tiene_imagen = block.get("type") == "figure" and block.get("image_bytes")
                    if block.get("type") != "table" and block_title and not tiene_imagen:
                        body_parts.append(_paragraph(block_title, bold=True, spacing_after=80, keep_next=True))
                    if block.get("type") != "table" and block_desc:
                        body_parts.append(_paragraph(block_desc, spacing_after=90, jc="both", keep_next=True))
                    if block.get("type") == "table":
                        family = str(block.get("table_family") or "").strip().lower()
                        if block.get("description"):
                            body_parts.append(_paragraph(block.get("description", ""), spacing_after=70, jc="both", keep_next=True))
                        if block.get("title"):
                            numeros["tabla"] += 1
                            body_parts.append(_rotulo_xml("Tabla", numeros["tabla"], block.get("title", "")))
                        if family == "split_horizontal":
                            body_parts.append(_table_side_by_side(block))
                        else:
                            body_parts.append(_table_block({**block, "headers": normalize_headers(block.get("headers", []) or [])}))
                        if block.get("note"):
                            body_parts.append(_paragraph(block.get("note", ""), spacing_before=120, spacing_after=60, jc="both"))
                    elif block.get("type") == "figure" and block.get("image_bytes"):
                        image_bytes = block.get("image_bytes")
                        dimensions = _image_dimensions(image_bytes, block=block)
                        if dimensions:
                            rel_id = f"rIdImage{len(media_files) + 1}"
                            image_name = _safe_media_name(block.get("file_name"), default_stem=f"figure_{len(media_files) + 1}", default_ext=".png")
                            media_target = f"media/{image_name}"
                            relationships.append(
                                (
                                    rel_id,
                                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                                    media_target,
                                )
                            )
                            media_files.append((f"word/{media_target}", image_bytes))
                            body_parts.append(_image_paragraph(rel_id, image_name, dimensions[0], dimensions[1], doc_pr_id))
                            doc_pr_id += 1
                            if block_title:
                                numeros["figura"] += 1
                                body_parts.append(_rotulo_xml("Figura", numeros["figura"], block_title, centrado=True))
                        else:
                            body_parts.append(_paragraph("La figura no pudo insertarse automáticamente en Word."))
                    body_parts.append(_paragraph("", spacing_after=40))

        document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{DOCX_NS['w']}" xmlns:r="{DOCX_NS['r']}" xmlns:wp="{DOCX_NS['wp']}" xmlns:a="{DOCX_NS['a']}" xmlns:pic="{DOCX_NS['pic']}">
  <w:body>
    {''.join(body_parts)}
    <w:sectPr>
      <w:headerReference w:type="default" r:id="rIdHeader1"/>
      <w:footerReference w:type="default" r:id="rIdFooter1"/>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="650" w:footer="650" w:gutter="0"/>
      <w:titlePg/>
    </w:sectPr>
  </w:body>
</w:document>
"""

        rels_xml = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', f'<Relationships xmlns="{DOCX_NS["rels"]}">']
        for rel_id, rel_type, target in relationships:
            rels_xml.append(f'<Relationship Id="{rel_id}" Type="{rel_type}" Target="{target}"/>')
        rels_xml.append("</Relationships>")

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _content_types_xml_with_header_footer(bool(media_files)))
            zf.writestr("_rels/.rels", _root_rels_xml())
            zf.writestr("word/document.xml", document_xml)
            zf.writestr("word/_rels/document.xml.rels", "".join(rels_xml))
            zf.writestr("word/styles.xml", _styles_xml())
            zf.writestr("word/settings.xml", _settings_xml())
            zf.writestr("word/header1.xml", _header_xml(project_name))
            zf.writestr("word/footer1.xml", _footer_xml())
            for path, media_bytes in media_files:
                zf.writestr(path, media_bytes)

        result["success"] = True
        result["docx_bytes"] = output.getvalue()
        result["message"] = "Documento Word del informe técnico generado correctamente."
        return result
    except Exception as exc:
        result["message"] = f"No fue posible generar el documento Word del informe técnico: {exc}."
        return result


_build_informe_tecnico_docx_basic = build_informe_tecnico_docx


def _w_tag(name):
    return f"{{{DOCX_NS['w']}}}{name}"


def _a_tag(name):
    return f"{{{DOCX_NS['a']}}}{name}"


def _r_tag(name):
    return f"{{{DOCX_NS['r']}}}{name}"


def _read_docx_relationships(zf):
    rels = {}
    try:
        rels_root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
        for rel in rels_root.findall(f"{{{DOCX_NS['rels']}}}Relationship"):
            rels[str(rel.attrib.get("Id") or "")] = str(rel.attrib.get("Target") or "")
    except Exception:
        return {}
    return rels


def _paragraph_text(paragraph):
    texts = []
    for node in paragraph.iter(_w_tag("t")):
        if node.text:
            texts.append(node.text)
    return "".join(texts).strip()


def _paragraph_style(paragraph):
    ppr = paragraph.find(_w_tag("pPr"))
    if ppr is None:
        return "Normal"
    pstyle = ppr.find(_w_tag("pStyle"))
    if pstyle is None:
        return "Normal"
    return str(pstyle.attrib.get(_w_tag("val")) or pstyle.attrib.get("w:val") or pstyle.attrib.get("val") or "Normal")


def _table_to_block(table):
    rows = []
    for tr in table.findall(_w_tag("tr")):
        row = []
        for tc in tr.findall(_w_tag("tc")):
            cell_text = []
            for node in tc.iter(_w_tag("t")):
                if node.text:
                    cell_text.append(node.text)
            row.append("".join(cell_text).strip())
        if row:
            rows.append(row)
    if not rows:
        return None
    return {
        "type": "table",
        "title": "",
        "description": "",
        "headers": rows[0],
        "rows": rows[1:] if len(rows) > 1 else [],
    }


def load_informe_tecnico_master_docx(docx_bytes, file_name="informe_tecnico editado por mi.docx"):
    result = {
        "available": False,
        "file_name": file_name,
        "docx_bytes": docx_bytes,
        "title": "",
        "project_name": "",
        "intro_paragraphs": [],
        "sections": [],
        "base_blocks": [],
    }
    if not docx_bytes:
        return result

    try:
        zf = zipfile.ZipFile(io.BytesIO(docx_bytes))
        document_root = ET.fromstring(zf.read("word/document.xml"))
        relationships = _read_docx_relationships(zf)
        media_cache = {}
        body = document_root.find(_w_tag("body"))
        if body is None:
            return result

        intro_paragraphs = []
        current_section = None
        current_subsection = None

        for child in list(body):
            if child.tag == _w_tag("sectPr"):
                continue
            if child.tag == _w_tag("p"):
                style = _paragraph_style(child)
                text = _paragraph_text(child)
                blip = child.find(f".//{_a_tag('blip')}")
                embed_rel = None
                if blip is not None:
                    embed_rel = blip.attrib.get(_r_tag("embed")) or blip.attrib.get("embed")

                if style == "Title" and text:
                    result["title"] = text
                    result["base_blocks"].append({"type": "paragraph", "style": "Title", "text": text})
                    continue
                if style == "Heading1" and text:
                    current_section = {"id": f"master_{len(result['sections']) + 1}", "title": text, "description": "", "subsections": []}
                    result["sections"].append(current_section)
                    current_subsection = None
                    result["base_blocks"].append({"type": "paragraph", "style": "Heading1", "text": text})
                    continue
                if style == "Heading2" and text:
                    if current_section is None:
                        current_section = {"id": "master_phase1", "title": "Fase 1", "description": "", "subsections": []}
                        result["sections"].append(current_section)
                    current_subsection = {"id": f"{current_section['id']}_{len(current_section['subsections']) + 1}", "title": text, "blocks": []}
                    current_section["subsections"].append(current_subsection)
                    result["base_blocks"].append({"type": "paragraph", "style": "Heading2", "text": text})
                    continue
                if embed_rel:
                    target = relationships.get(embed_rel, "")
                    if target:
                        media_path = target if target.startswith("word/") else f"word/{target.replace('../', '')}"
                        if media_path not in media_cache:
                            try:
                                media_cache[media_path] = zf.read(media_path)
                            except Exception:
                                media_cache[media_path] = None
                        image_bytes = media_cache.get(media_path)
                        figure_block = {
                            "type": "figure",
                            "title": text or "",
                            "description": "",
                            "image_bytes": image_bytes,
                            "image_format": "png" if str(target).lower().endswith(".png") else None,
                            "file_name": target.split("/")[-1] if target else "imagen.png",
                        }
                        if current_subsection is not None:
                            current_subsection["blocks"].append(figure_block)
                        result["base_blocks"].append({"type": "figure", "style": "Figure", **figure_block})
                    continue
                if not text:
                    continue
                paragraph_block = {"type": "paragraph", "style": style or "Normal", "text": text}
                if not result["project_name"] and not result["sections"]:
                    result["project_name"] = text
                elif current_subsection is not None:
                    current_subsection["blocks"].append(paragraph_block)
                elif current_section is not None:
                    if not current_section.get("description"):
                        current_section["description"] = text
                    else:
                        intro_paragraphs.append(text)
                else:
                    intro_paragraphs.append(text)
                result["base_blocks"].append(paragraph_block)
            elif child.tag == _w_tag("tbl"):
                table_block = _table_to_block(child)
                if table_block:
                    if current_subsection is not None:
                        current_subsection["blocks"].append(table_block)
                    result["base_blocks"].append(table_block)

        if not result["title"]:
            result["title"] = "Informe técnico"
        result["intro_paragraphs"] = intro_paragraphs
        result["available"] = True
        return result
    except Exception:
        return result


def _xml_fragment(fragment):
    wrapper = (
        f'<root xmlns:w="{DOCX_NS["w"]}" xmlns:r="{DOCX_NS["r"]}" '
        f'xmlns:wp="{DOCX_NS["wp"]}" xmlns:a="{DOCX_NS["a"]}" xmlns:pic="{DOCX_NS["pic"]}">'
        f"{fragment}</root>"
    )
    root = ET.fromstring(wrapper)
    return list(root)[0]


def _next_rel_index(rels_root):
    current = 0
    for rel in rels_root.findall(f"{{{DOCX_NS['rels']}}}Relationship"):
        rel_id = str(rel.attrib.get("Id") or "")
        if rel_id.startswith("rId"):
            try:
                current = max(current, int(rel_id[3:]))
            except Exception:
                pass
    return current + 1


def _append_structured_sections_to_master_docx(master_docx_bytes, appended_sections, file_name):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(master_docx_bytes), "r") as source_zip:
        document_root = ET.fromstring(source_zip.read("word/document.xml"))
        rels_root = ET.fromstring(source_zip.read("word/_rels/document.xml.rels"))
        body = document_root.find(_w_tag("body"))
        if body is None:
            raise ValueError("El documento maestro no contiene un cuerpo de Word válido.")
        sect_pr = body.find(_w_tag("sectPr"))
        if sect_pr is not None:
            body.remove(sect_pr)

        next_rel = _next_rel_index(rels_root)
        media_files = []
        doc_pr_id = 2000

        for section in appended_sections or []:
            body.append(_xml_fragment(_paragraph(section.get("title", "Sección"), style="Heading1")))
            if section.get("description"):
                body.append(_xml_fragment(_paragraph(section.get("description", ""), spacing_after=120, jc="both")))
            for subsection in section.get("subsections", []) or []:
                body.append(_xml_fragment(_paragraph(subsection.get("title", "Subsección"), style="Heading2")))
                for block in subsection.get("blocks", []) or []:
                    if block.get("type") == "paragraph":
                        body.append(_xml_fragment(_paragraph(block.get("text", ""), spacing_after=90, jc="both")))
                    elif block.get("type") == "table":
                        for table_block in _table_split_blocks(block):
                            if table_block.get("title"):
                                body.append(_xml_fragment(_paragraph(table_block.get("title", ""), bold=True, spacing_after=60)))
                            if table_block.get("description"):
                                body.append(_xml_fragment(_paragraph(table_block.get("description", ""), spacing_after=70, jc="both")))
                            body.append(_xml_fragment(_table_block(table_block)))
                    elif block.get("type") == "figure":
                        if block.get("title"):
                            body.append(_xml_fragment(_paragraph(block.get("title", ""), bold=True, spacing_after=60)))
                        if block.get("description"):
                            body.append(_xml_fragment(_paragraph(block.get("description", ""), spacing_after=70, jc="both")))
                        image_bytes = block.get("image_bytes")
                        dimensions = _image_dimensions(image_bytes, block=block) if image_bytes else None
                        if dimensions:
                            rel_id = f"rId{next_rel}"
                            next_rel += 1
                            image_name = _safe_media_name(block.get("file_name"), default_stem=f"figure_{doc_pr_id}", default_ext=".png")
                            media_target = f"media/{image_name}"
                            rels_root.append(
                                ET.fromstring(
                                    f'<Relationship xmlns="{DOCX_NS["rels"]}" Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{media_target}"/>'
                                )
                            )
                            media_files.append((f"word/{media_target}", image_bytes))
                            body.append(_xml_fragment(_image_paragraph(rel_id, image_name, dimensions[0], dimensions[1], doc_pr_id)))
                            doc_pr_id += 1
                        else:
                            body.append(_xml_fragment(_paragraph("La figura no pudo anexarse automáticamente en Word.")))
                    body.append(_xml_fragment(_paragraph("", spacing_after=20)))

        if sect_pr is not None:
            body.append(sect_pr)

        content_types = source_zip.read("[Content_Types].xml").decode("utf-8")
        if media_files and 'Extension="png"' not in content_types:
            content_types = content_types.replace(
                '<Default Extension="xml" ContentType="application/xml"/>',
                '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>',
            )

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target_zip:
            for item in source_zip.infolist():
                if item.filename in ["word/document.xml", "word/_rels/document.xml.rels", "[Content_Types].xml"]:
                    continue
                target_zip.writestr(item, source_zip.read(item.filename))
            target_zip.writestr("[Content_Types].xml", content_types)
            target_zip.writestr("word/document.xml", ET.tostring(document_root, encoding="utf-8", xml_declaration=True))
            target_zip.writestr("word/_rels/document.xml.rels", ET.tostring(rels_root, encoding="utf-8", xml_declaration=True))
            for path, content in media_files:
                target_zip.writestr(path, content)

    return {
        "success": True,
        "docx_bytes": output.getvalue(),
        "file_name": file_name,
        "message": "Documento Word del informe técnico generado correctamente a partir del DOCX maestro.",
    }


def build_informe_tecnico_docx(report_model, file_name="informe_tecnico.docx"):
    master_docx = report_model.get("word_master") or {}
    if master_docx.get("available") and master_docx.get("docx_bytes"):
        try:
            return _append_structured_sections_to_master_docx(
                master_docx_bytes=master_docx.get("docx_bytes"),
                appended_sections=report_model.get("appended_sections") or [],
                file_name=file_name,
            )
        except Exception as exc:
            return {
                "success": False,
                "docx_bytes": None,
                "file_name": file_name,
                "message": f"No fue posible anexar las fases adicionales al DOCX maestro: {exc}.",
            }

    return _build_informe_tecnico_docx_basic(report_model, file_name=file_name)
