"""Reporte bankable (Word + PDF) con los datos REALES del proyecto activo.

Todo el contenido sale de `reportes.datos_proyecto.construir_datos_exportacion` (la misma fuente que
el informe técnico y el Excel): ubicación, aerogenerador, altura de buje, recurso, cascada de
pérdidas y AEP de la Fase 5, Monte Carlo guardado, idoneidad IEC con el criterio de la Fase 5,
ruido y parpadeo de la Fase 6, flujo de caja y sensibilidad con el modelo económico de la Fase 5.
Nada queda fijo: si cambia el proyecto, cambia el informe. Los textos están en español, inglés,
portugués y francés (`reportes.bankable_i18n`) y los números usan el formato de cada idioma.

Presentación formal común a todos los entregables (`reportes.estilo`, `reportes.graficas`): azul
marino corporativo, letra Calibri, tablas con reglas horizontales y rótulos «Tabla N.» / «Figura N.».

Estructura (IEC 61400-15-2 / prácticas habituales de un EYA):
    Portada · Control del documento · Índice
    1. Resumen ejecutivo  2. Proyecto  3. Recurso eólico  4. Producción  5. Incertidumbre
    6. IEC 61400-1  7. Ambiental  8. Economía (+ marco regulatorio y normas)  9. Riesgos
    10. Conclusiones  11. Apéndices
"""
from __future__ import annotations

import io
import re
from datetime import datetime

from . import estilo, graficas
from .bankable_i18n import nombre_pais, tr, tr_concepto, tr_valor
from .datos_proyecto import (
    construir_datos_exportacion,
    en_moneda,
    fmt_money,
    fmt_num,
    fmt_pct,
    num,
    texto_aviso,
)
from .graficas import estadistica_sectores, sectores_16  # se re-exportan por compatibilidad

try:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor
except ImportError:  # pragma: no cover - python-docx es dependencia de la app
    Document = None

MARINO = estilo.MARINO
MARINO_SUAVE = estilo.MARINO_SUAVE
TEXTO = estilo.TEXTO
GRIS = estilo.GRIS
VERDE, VERDE_FONDO = estilo.VERDE, estilo.VERDE_SUAVE
AMBAR, AMBAR_FONDO = "8A5A12", estilo.AMBAR_SUAVE
ROJO, ROJO_FONDO = estilo.ROJO, estilo.ROJO_SUAVE
FILA_TOTAL = "E4EAF2"
ANCHO_UTIL_IN = 6.5  # carta con márgenes de 1 in

_RE_NUMERO = re.compile(r"^[−\-+]?\s?(?:[A-Z]{3}\s)?[−\-]?\d")
# Orden de los hijos de w:pPr / w:tcPr / w:tblPr según el esquema de Word (para insertar sin romperlo)
_PPR_DESPUES_PBDR = ("w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
                     "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd", "w:snapToGrid",
                     "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
                     "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId",
                     "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange")
_TCPR_DESPUES_BORDES = ("w:shd", "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark")
_TCPR_DESPUES_SHD = ("w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark")
_TCPR_DESPUES_MAR = ("w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark")
_TBLPR_DESPUES_BORDES = ("w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook", "w:tblCaption", "w:tblDescription")
_TBLPR_DESPUES_ESPACIADO = ("w:tblInd", "w:tblBorders", "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook")


# ─────────────────────────────────────────────────────────────
# Utilidades de Word (python-docx)
# ─────────────────────────────────────────────────────────────
def _rgb(hex_color):
    return RGBColor(int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))


def _quitar(padre, etiqueta):
    for previo in padre.findall(qn(etiqueta)):
        padre.remove(previo)


def _sombrear(celda, hex_color):
    tc_pr = celda._tc.get_or_add_tcPr()
    _quitar(tc_pr, "w:shd")
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.insert_element_before(shd, *_TCPR_DESPUES_SHD)


def _linea(nombre, valor):
    elemento = OxmlElement(f"w:{nombre}")
    if valor is None:
        elemento.set(qn("w:val"), "nil")
    else:
        tipo, grosor, color = valor
        elemento.set(qn("w:val"), tipo)
        elemento.set(qn("w:sz"), str(grosor))
        elemento.set(qn("w:space"), "0")
        elemento.set(qn("w:color"), color)
    return elemento


def _bordes_celda(celda, top=None, left=None, bottom=None, right=None):
    tc_pr = celda._tc.get_or_add_tcPr()
    _quitar(tc_pr, "w:tcBorders")
    bordes = OxmlElement("w:tcBorders")
    for nombre, valor in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        bordes.append(_linea(nombre, valor))
    tc_pr.insert_element_before(bordes, *_TCPR_DESPUES_BORDES)


def _margenes_celda(celda, arriba=60, izquierda=110, abajo=60, derecha=110):
    tc_pr = celda._tc.get_or_add_tcPr()
    _quitar(tc_pr, "w:tcMar")
    mar = OxmlElement("w:tcMar")
    for nombre, valor in (("top", arriba), ("left", izquierda), ("bottom", abajo), ("right", derecha)):
        e = OxmlElement(f"w:{nombre}")
        e.set(qn("w:w"), str(valor))
        e.set(qn("w:type"), "dxa")
        mar.append(e)
    tc_pr.insert_element_before(mar, *_TCPR_DESPUES_MAR)


def _bordes_tabla(tabla, top=("single", 8, MARINO), bottom=("single", 8, MARINO), inside_h=("single", 4, estilo.REGLA)):
    """Estilo formal: regla superior e inferior en azul marino, reglas finas entre filas, sin verticales."""
    tbl_pr = tabla._tbl.tblPr
    _quitar(tbl_pr, "w:tblBorders")
    bordes = OxmlElement("w:tblBorders")
    for nombre, valor in (("top", top), ("left", None), ("bottom", bottom), ("right", None), ("insideH", inside_h),
                          ("insideV", None)):
        bordes.append(_linea(nombre, valor))
    tbl_pr.insert_element_before(bordes, *_TBLPR_DESPUES_BORDES)


def _espaciado_celdas(tabla, twips=70):
    tbl_pr = tabla._tbl.tblPr
    _quitar(tbl_pr, "w:tblCellSpacing")
    esp = OxmlElement("w:tblCellSpacing")
    esp.set(qn("w:w"), str(twips))
    esp.set(qn("w:type"), "dxa")
    tbl_pr.insert_element_before(esp, *_TBLPR_DESPUES_ESPACIADO)


def _borde_parrafo(parrafo, lado="bottom", grosor=6, color=estilo.REGLA, espacio=4):
    p_pr = parrafo._p.get_or_add_pPr()
    _quitar(p_pr, "w:pBdr")
    pbdr = OxmlElement("w:pBdr")
    linea = OxmlElement(f"w:{lado}")
    linea.set(qn("w:val"), "single")
    linea.set(qn("w:sz"), str(grosor))
    linea.set(qn("w:space"), str(espacio))
    linea.set(qn("w:color"), color)
    pbdr.append(linea)
    p_pr.insert_element_before(pbdr, *_PPR_DESPUES_PBDR)


def _propiedad_fila(fila, etiqueta):
    tr_pr = fila._tr.get_or_add_trPr()
    elemento = OxmlElement(etiqueta)
    elemento.set(qn("w:val"), "true")
    tr_pr.append(elemento)


def _texto_celda(celda, texto, bold=False, color=None, alinear=None, tam=9, italic=False):
    celda.text = ""
    parrafo = celda.paragraphs[0]
    formato = parrafo.paragraph_format
    formato.space_after = Pt(0)
    formato.space_before = Pt(0)
    formato.line_spacing = 1.0
    if alinear == "centro":
        parrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif alinear == "derecha":
        parrafo.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = parrafo.add_run(str(texto))
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(tam)
    run.font.color.rgb = _rgb(color or TEXTO)


def _espacio(doc, puntos=4):
    parrafo = doc.add_paragraph()
    formato = parrafo.paragraph_format
    formato.space_after = Pt(0)
    formato.space_before = Pt(0)
    formato.line_spacing = 1.0
    parrafo.add_run("").font.size = Pt(puntos)
    return parrafo


def _anchos_por_defecto(n):
    if n == 1:
        return [ANCHO_UTIL_IN]
    if n == 2:
        return [3.2, 3.3]
    primera = min(2.2, ANCHO_UTIL_IN * 0.34) if n <= 4 else ANCHO_UTIL_IN / n * 1.35
    resto = (ANCHO_UTIL_IN - primera) / (n - 1)
    return [primera] + [resto] * (n - 1)


def _tabla(doc, encabezados, filas, anchos=None, tam=None, total=False, alinear_num=True, juntar=None):
    """Tabla formal: encabezado azul marino que se repite en cada página, reglas horizontales finas,
    cebrado suave, filas que no se parten y (hasta 20 filas) toda la tabla en una misma página."""
    n = len(encabezados)
    tam = tam or (9 if n <= 4 else (8.5 if n <= 6 else 8))
    anchos = anchos or _anchos_por_defecto(n)
    escala = ANCHO_UTIL_IN / sum(anchos)
    anchos = [a * escala for a in anchos]
    if doc.paragraphs and doc.paragraphs[-1].text.strip():
        doc.paragraphs[-1].paragraph_format.keep_with_next = True  # el rótulo o texto que presenta la tabla va con ella
    tabla = doc.add_table(rows=1, cols=n)
    tabla.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabla.autofit = False
    _bordes_tabla(tabla)
    fila0 = tabla.rows[0]
    _propiedad_fila(fila0, "w:tblHeader")
    _propiedad_fila(fila0, "w:cantSplit")
    for j, titulo in enumerate(encabezados):
        celda = fila0.cells[j]
        _texto_celda(celda, titulo, bold=True, color="FFFFFF", alinear=None if j == 0 else "centro", tam=tam)
        _sombrear(celda, MARINO)
    for i, valores in enumerate(filas):
        fila = tabla.add_row()
        _propiedad_fila(fila, "w:cantSplit")
        ultima = total and i == len(filas) - 1
        for j in range(n):
            texto = "" if j >= len(valores) or valores[j] is None else str(valores[j])
            alinear = "derecha" if (alinear_num and j > 0 and _RE_NUMERO.match(texto.strip())) else None
            celda = fila.cells[j]
            _texto_celda(celda, texto, bold=ultima, color=MARINO if ultima else None, alinear=alinear, tam=tam)
            if ultima:
                _sombrear(celda, FILA_TOTAL)
                _bordes_celda(celda, top=("single", 6, MARINO))
            elif i % 2 == 1:
                _sombrear(celda, estilo.CEBRA)
    juntar = len(filas) <= 20 if juntar is None else juntar
    ultima_fila = len(tabla.rows) - 1
    for k, fila in enumerate(tabla.rows):
        for j, ancho in enumerate(anchos):
            fila.cells[j].width = Inches(ancho)
            if juntar and k < ultima_fila:
                for parrafo in fila.cells[j].paragraphs:
                    parrafo.paragraph_format.keep_with_next = True
    _espacio(doc)
    return tabla


def _tabla_kv(doc, filas, lang, encabezados=None, anchos=(3.2, 3.3), tam=None):
    """Tabla de dos columnas (indicador | valor); las filas None se omiten."""
    encabezados = encabezados or (tr("indicador", lang), tr("valor", lang))
    return _tabla(doc, encabezados, [f for f in filas if f is not None], anchos=list(anchos), tam=tam,
                  alinear_num=False)


def _callout(doc, titulo, cuerpo, color=MARINO, fondo=MARINO_SUAVE):
    """Caja destacada con filete lateral; `cuerpo` puede ser un texto o una lista (con viñetas)."""
    tabla = doc.add_table(rows=1, cols=1)
    tabla.alignment = WD_TABLE_ALIGNMENT.CENTER
    _bordes_tabla(tabla, top=None, bottom=None, inside_h=None)
    _propiedad_fila(tabla.rows[0], "w:cantSplit")
    celda = tabla.cell(0, 0)
    celda.width = Inches(ANCHO_UTIL_IN)
    _bordes_celda(celda, left=("single", 24, color))
    _sombrear(celda, fondo)
    _margenes_celda(celda, arriba=90, izquierda=160, abajo=90, derecha=140)
    parrafo = celda.paragraphs[0]
    parrafo.paragraph_format.space_after = Pt(3)
    run = parrafo.add_run(titulo)
    run.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = _rgb(color)
    lineas = cuerpo if isinstance(cuerpo, (list, tuple)) else [cuerpo]
    for linea in lineas:
        if not linea:
            continue
        p = celda.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.line_spacing = 1.08
        r = p.add_run(("• " if isinstance(cuerpo, (list, tuple)) else "") + str(linea))
        r.font.size = Pt(9.5)
        r.font.color.rgb = _rgb(TEXTO)
    _espacio(doc, 6)
    return tabla


def _banda(doc, titulo, subtitulo):
    """Banda azul marino a todo el ancho con el título en blanco (portada)."""
    tabla = doc.add_table(rows=1, cols=1)
    tabla.alignment = WD_TABLE_ALIGNMENT.CENTER
    _bordes_tabla(tabla, top=None, bottom=None, inside_h=None)
    celda = tabla.cell(0, 0)
    celda.width = Inches(ANCHO_UTIL_IN)
    _sombrear(celda, MARINO)
    _margenes_celda(celda, arriba=320, izquierda=320, abajo=300, derecha=320)
    p1 = celda.paragraphs[0]
    p1.paragraph_format.space_after = Pt(4)
    r1 = p1.add_run(titulo)
    r1.bold = True
    r1.font.size = Pt(26)
    r1.font.color.rgb = _rgb("FFFFFF")
    p2 = celda.add_paragraph()
    r2 = p2.add_run(subtitulo)
    r2.font.size = Pt(12)
    r2.font.color.rgb = _rgb("D6DEE9")
    return tabla


def _tarjetas(doc, tarjetas, por_fila=4):
    """Rejilla de tarjetas de cifras (sin iconos): [(valor, etiqueta), …]. Una tabla por fila y columnas
    estrechas vacías entre tarjetas: cada tarjeta conserva su filete y la rejilla ocupa justo el ancho útil."""
    if not tarjetas:
        return None
    hueco = 0.09
    ancho = (ANCHO_UTIL_IN - hueco * (por_fila - 1)) / por_fila
    columnas = 2 * por_fila - 1
    for inicio in range(0, len(tarjetas), por_fila):
        grupo = tarjetas[inicio:inicio + por_fila]
        tabla = doc.add_table(rows=1, cols=columnas)
        tabla.alignment = WD_TABLE_ALIGNMENT.CENTER
        tabla.autofit = False
        _bordes_tabla(tabla, top=None, bottom=None, inside_h=None)
        _propiedad_fila(tabla.rows[0], "w:cantSplit")
        for j in range(columnas):
            celda = tabla.cell(0, j)
            celda.width = Inches(ancho if j % 2 == 0 else hueco)
            if j % 2 == 1 or j // 2 >= len(grupo):
                _margenes_celda(celda, 0, 0, 0, 0)
                continue
            valor, etiqueta = grupo[j // 2]
            _sombrear(celda, MARINO_SUAVE)
            _bordes_celda(celda, left=("single", 24, MARINO))
            _margenes_celda(celda, arriba=100, izquierda=150, abajo=100, derecha=90)
            p1 = celda.paragraphs[0]
            p1.paragraph_format.space_after = Pt(1)
            r1 = p1.add_run(str(valor))
            r1.bold = True
            r1.font.size = Pt(13.5)
            r1.font.color.rgb = _rgb(MARINO)
            p2 = celda.add_paragraph()
            p2.paragraph_format.space_after = Pt(0)
            r2 = p2.add_run(str(etiqueta))
            r2.font.size = Pt(8.5)
            r2.font.color.rgb = _rgb(GRIS)
        _espacio(doc, 5)
    _espacio(doc, 4)
    return True


def _p(doc, texto, bold=False, italic=False, tam=None, color=None, alinear=None, estilo_parrafo=None):
    parrafo = doc.add_paragraph(style=estilo_parrafo) if estilo_parrafo else doc.add_paragraph()
    if alinear == "centro":
        parrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif alinear == "justificado":
        parrafo.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = parrafo.add_run(str(texto))
    run.bold = bold
    run.italic = italic
    if tam:
        run.font.size = Pt(tam)
    if color:
        run.font.color.rgb = _rgb(color)
    return parrafo


def _vinetas(doc, items, numerada=False):
    estilo_lista = "List Number" if numerada else "List Bullet"
    for item in items:
        if not item:
            continue
        try:
            _p(doc, item, estilo_parrafo=estilo_lista)
        except KeyError:
            _p(doc, ("– " if not numerada else "") + str(item))


def _campo(parrafo, instruccion, marcador="1", tam=None, bold=None, italic=None, color=None):
    """Campo de Word (PAGE, NUMPAGES, SEQ, TOC…) en runs separados, con un valor provisional."""
    def _run():
        run = parrafo.add_run()
        if tam:
            run.font.size = Pt(tam)
        if bold is not None:
            run.bold = bold
        if italic is not None:
            run.italic = italic
        if color:
            run.font.color.rgb = _rgb(color)
        return run

    def _fld(tipo):
        elemento = OxmlElement("w:fldChar")
        elemento.set(qn("w:fldCharType"), tipo)
        _run()._r.append(elemento)

    _fld("begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruccion} "
    _run()._r.append(instr)
    _fld("separate")
    _run().text = str(marcador)
    _fld("end")


class _Numerador:
    """Numeración real de figuras y tablas (el campo SEQ lleva el número correcto aunque Word no lo actualice)."""

    def __init__(self):
        self.figuras = 0
        self.tablas = 0


def _rotulo(doc, lang, texto, numerador, tipo="figura"):
    """«Figura N. texto» (centrado, bajo la figura) o «Tabla N. texto» (a la izquierda, sobre la tabla)."""
    if tipo == "tabla":
        numerador.tablas += 1
        numero, clave = numerador.tablas, "tabla"
    else:
        numerador.figuras += 1
        numero, clave = numerador.figuras, "figura"
    etiqueta = tr(clave, lang)
    try:
        parrafo = doc.add_paragraph(style="Caption")
    except KeyError:
        parrafo = doc.add_paragraph()
    formato = parrafo.paragraph_format
    formato.space_before = Pt(6 if tipo == "tabla" else 2)
    formato.space_after = Pt(3 if tipo == "tabla" else 8)
    formato.keep_with_next = tipo == "tabla"
    parrafo.alignment = WD_ALIGN_PARAGRAPH.LEFT if tipo == "tabla" else WD_ALIGN_PARAGRAPH.CENTER
    run = parrafo.add_run(f"{etiqueta} ")
    run.bold = True
    run.italic = False
    run.font.size = Pt(9)
    run.font.color.rgb = _rgb(MARINO)
    _campo(parrafo, f"SEQ {etiqueta} \\* ARABIC", numero, tam=9, bold=True, italic=False, color=MARINO)
    cola = parrafo.add_run(f". {texto}")
    cola.italic = False
    cola.font.size = Pt(9)
    cola.font.color.rgb = _rgb(TEXTO)
    return parrafo


def _figura(doc, png, lang, pie, numerador, ancho_in=6.0):
    if not png:
        return False
    parrafo = doc.add_paragraph()
    parrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    parrafo.paragraph_format.keep_with_next = True
    parrafo.paragraph_format.space_before = Pt(4)
    try:
        parrafo.add_run().add_picture(io.BytesIO(png), width=Inches(ancho_in))
    except Exception:
        return False
    _rotulo(doc, lang, pie, numerador, "figura")
    return True


def _indice(doc, lang):
    parrafo = doc.add_paragraph()
    run = parrafo.add_run(tr("toc", lang))
    run.bold = True
    run.font.size = Pt(15)
    run.font.color.rgb = _rgb(MARINO)
    parrafo.paragraph_format.space_after = Pt(10)
    _borde_parrafo(parrafo, grosor=8, color=MARINO)
    campo = doc.add_paragraph()
    _campo(campo, 'TOC \\o "1-2" \\h \\z \\u', tr("toc_placeholder", lang), italic=True)
    ajustes = doc.settings.element
    if ajustes.find(qn("w:updateFields")) is None:
        actualizar = OxmlElement("w:updateFields")
        actualizar.set(qn("w:val"), "true")
        ajustes.insert(0, actualizar)


def _encabezado_y_pie(doc, proyecto, codigo, lang, logo_bytes=None):
    for seccion in doc.sections:
        seccion.different_first_page_header_footer = True  # la portada va sin encabezado ni pie
        cabecera = seccion.header.paragraphs[0]
        cabecera.paragraph_format.tab_stops.add_tab_stop(Inches(ANCHO_UTIL_IN), WD_TAB_ALIGNMENT.RIGHT)
        if logo_bytes:
            try:
                cabecera.add_run().add_picture(io.BytesIO(logo_bytes), height=Inches(0.28))
                cabecera.add_run("   ")
            except Exception:
                pass
        izquierda = cabecera.add_run(f"{proyecto}  ·  {tr('titulo_corto', lang)}")
        izquierda.font.size = Pt(8)
        izquierda.font.color.rgb = _rgb(MARINO)
        izquierda.bold = True
        derecha = cabecera.add_run(f"\t{codigo}  ·  {tr('confidencial', lang)}")
        derecha.font.size = Pt(8)
        derecha.font.color.rgb = _rgb(GRIS)
        _borde_parrafo(cabecera, "bottom", 6, estilo.REGLA, 4)
        pie = seccion.footer.paragraphs[0]
        pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _borde_parrafo(pie, "top", 6, estilo.REGLA, 4)
        for texto, instruccion in ((f"{tr('pagina', lang)} ", "PAGE"), (f" {tr('de', lang)} ", "NUMPAGES")):
            run = pie.add_run(texto)
            run.font.size = Pt(8)
            run.font.color.rgb = _rgb(GRIS)
            _campo(pie, instruccion, "1", tam=8, color=GRIS)


def _documento_base():
    if Document is None:
        raise RuntimeError("python-docx no está instalado (pip install python-docx).")
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = estilo.FUENTE
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = _rgb(TEXTO)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), estilo.FUENTE)
    formato = normal.paragraph_format
    formato.space_after = Pt(6)
    formato.line_spacing = 1.15
    for nombre, tam, antes, despues in (("Heading 1", 15, 16, 8), ("Heading 2", 12, 12, 5), ("Heading 3", 11, 10, 4)):
        try:
            est = doc.styles[nombre]
            est.font.name = estilo.FUENTE
            est.font.size = Pt(tam)
            est.font.bold = True
            est.font.color.rgb = _rgb(MARINO)
            est.element.rPr.rFonts.set(qn("w:eastAsia"), estilo.FUENTE)
            est.paragraph_format.space_before = Pt(antes)
            est.paragraph_format.space_after = Pt(despues)
            est.paragraph_format.keep_with_next = True
            if nombre == "Heading 1":
                est.paragraph_format.page_break_before = True
                p_pr = est.element.get_or_add_pPr()
                pbdr = OxmlElement("w:pBdr")
                abajo = OxmlElement("w:bottom")
                for atributo, valor in (("w:val", "single"), ("w:sz", "8"), ("w:space", "3"), ("w:color", MARINO)):
                    abajo.set(qn(atributo), valor)
                pbdr.append(abajo)
                _quitar(p_pr, "w:pBdr")
                p_pr.insert_element_before(pbdr, *_PPR_DESPUES_PBDR)
        except KeyError:
            pass
    for nombre in ("List Bullet", "List Number"):
        try:
            doc.styles[nombre].paragraph_format.space_after = Pt(3)
            doc.styles[nombre].paragraph_format.line_spacing = 1.1
        except KeyError:
            pass
    from docx.enum.style import WD_STYLE_TYPE

    for nivel, sangria in ((1, 0.0), (2, 0.25)):
        try:
            est = doc.styles.add_style(f"toc {nivel}", WD_STYLE_TYPE.PARAGRAPH, builtin=True)
            est.base_style = normal
            est.paragraph_format.space_before = Pt(0)
            est.paragraph_format.space_after = Pt(3)
            est.paragraph_format.line_spacing = 1.0
            est.paragraph_format.left_indent = Inches(sangria)
            est.font.bold = nivel == 1
        except Exception:
            pass
    for seccion in doc.sections:
        seccion.page_width, seccion.page_height = Inches(8.5), Inches(11)
        seccion.top_margin = seccion.bottom_margin = Inches(1)
        seccion.left_margin = seccion.right_margin = Inches(1)
        seccion.header_distance = seccion.footer_distance = Inches(0.45)
    return doc


def _columna(df, *nombres):
    for nombre in nombres:
        if df is not None and nombre in df.columns:
            return nombre
    return None


# ─────────────────────────────────────────────────────────────
# Contexto del reporte
# ─────────────────────────────────────────────────────────────
def construir_contexto_bankable(config, runtime_context=None, project_metadata=None):
    """Datos del proyecto activo para el reporte bankable (misma fuente que los demás exportables).

    `project_metadata` (formulario de la Fase 7) fija nombre, autor, cliente y país del informe;
    `runtime_context` es el contexto de la Fase 5 en memoria (serie a la altura del buje, energía
    por sector, economía exacta). Sin él se usa lo guardado en la base de datos.
    """
    meta = project_metadata or {}
    config_informe = dict(config or {})
    for clave_meta, clave_cfg in (("country_code", "f7_country_code"), ("autor", "f7_bankable_autor"),
                                  ("cliente", "f7_bankable_cliente")):
        if meta.get(clave_meta) not in (None, ""):
            config_informe[clave_cfg] = meta[clave_meta]
    rc = dict(runtime_context or {})
    if str(meta.get("project_name") or "").strip():
        rc["project_name_default"] = str(meta["project_name"]).strip()
    if rc.get("df_nasa") is None:
        try:
            from db import cargar_nasa_hourly

            rc["df_nasa"] = cargar_nasa_hourly()
        except Exception:
            pass
    datos = construir_datos_exportacion(config_informe, rc)
    ahora = datetime.now()
    proyecto = datos["proyecto"]
    return {
        "datos": datos,
        "fecha_generacion": ahora.isoformat(timespec="seconds"),
        "codigo": f"SMA-BK-{ahora:%Y%m%d}-{proyecto['pais_codigo']}",
        "revision": "A",
        "metadata": {
            "project_name": proyecto["nombre"], "autor": proyecto["autor"], "cliente": proyecto["cliente"],
            "country_code": proyecto["pais_codigo"], "country_nombre": proyecto["pais_nombre"],
        },
    }


def _serie_viento(datos, lang):
    """(velocidad, dirección, etiqueta): serie a la altura del buje de la Fase 5 o, si no, la de referencia a 50 m."""
    recurso = datos["recurso"]
    df_hub = recurso.get("df_analisis")
    if df_hub is not None and {"WS_ANALISIS", "WD_USADA"} <= set(df_hub.columns):
        h = fmt_num(datos["turbina"].get("altura_buje_m"), 0, lang)
        return df_hub["WS_ANALISIS"], df_hub["WD_USADA"], tr("serie_buje", lang, h=h)
    df_ref = recurso.get("df_nasa")
    if df_ref is not None and {"WS50M", "WD50M"} <= set(df_ref.columns):
        return df_ref["WS50M"], df_ref["WD50M"], tr("serie_ref", lang, h="50")
    return None, None, ""


def _tipo_serie(serie_uso, lang):
    s = str(serie_uso or "").lower()
    if "mcp" in s:
        return tr("serie_mcp", lang)
    if "torre" in s or "mast" in s:
        return tr("serie_torre", lang)
    if "nasa" in s or not s:
        return tr("serie_nasa", lang)
    return str(serie_uso)


def _traducir_valores(datos, lang):
    """Copia de los datos con las opciones de la app (modos, modelos, rugosidad, disposición) y los
    nombres de país en el idioma del informe. Los números no cambian."""
    d = dict(datos)
    pr = dict(d["proyecto"])
    pr["pais_nombre"] = nombre_pais(pr.get("pais_codigo"), lang, pr.get("pais_nombre"))
    if pr.get("pais_inferido"):
        pr["pais_inferido_nombre"] = nombre_pais(pr["pais_inferido"], lang, pr.get("pais_inferido_nombre"))
    d["proyecto"] = pr
    d["energia"] = {**d["energia"], "wake_mode": tr_valor(d["energia"].get("wake_mode"), lang),
                    "metodo": tr_valor(d["energia"].get("metodo"), lang)}
    d["recurso"] = {**d["recurso"], "modelo_altura": tr_valor(d["recurso"].get("modelo_altura"), lang),
                    "rugosidad": tr_valor(d["recurso"].get("rugosidad"), lang)}
    d["layout"] = {**d["layout"], "tipo": tr_valor(d["layout"].get("tipo"), lang)}
    d["avisos"] = [{**a, "pais": pr["pais_nombre"], "inferido": pr.get("pais_inferido_nombre")}
                   if a.get("clave") == "pais" else a for a in d.get("avisos", [])]
    return d


# ─────────────────────────────────────────────────────────────
# Construcción del documento
# ─────────────────────────────────────────────────────────────
class _Informe:
    def __init__(self, ctx, lang="es", logo_bytes=None):
        self.ctx = ctx
        self.lang = lang if lang in ("es", "en", "pt", "fr") else "es"
        self.d = _traducir_valores(ctx["datos"], self.lang)
        self.doc = _documento_base()
        self.numerador = _Numerador()
        self.logo = logo_bytes
        eco = self.d["economia"]
        self.moneda = eco.get("moneda") or eco.get("moneda_base") or "USD"

    # ── formato ──
    def t(self, clave, **campos):
        return tr(clave, self.lang, **campos)

    def n(self, valor, dec=2):
        return fmt_num(valor, dec, self.lang)

    def pct(self, valor, dec=2):
        return fmt_pct(valor, dec, self.lang)

    def u(self, valor, unidad, dec=2):
        texto = fmt_num(valor, dec, self.lang)
        return texto if texto == "—" else f"{texto} {unidad}"

    def mwh(self, valor):
        return self.u(valor, self.t("mwh_anio"), 0)

    def dinero(self, valor, dec=None):
        return fmt_money(en_moneda(valor, self.d["economia"]), self.moneda, self.lang, dec)

    def dinero_corto(self, valor):
        """Cifra de tarjeta: «COP 10,60 M» en vez de «COP 10.600.401»."""
        x = en_moneda(valor, self.d["economia"])
        if x is None:
            return "—"
        return f"{self.moneda} {fmt_num(x / 1e6, 2, self.lang)} M" if abs(x) >= 1e6 else fmt_money(x, self.moneda, self.lang)

    def h1(self, clave):
        # Los capítulos empiezan en página nueva: el espaciador vacío que deja una tabla justo antes sobra
        # y, si cae al principio de una página, la deja en blanco.
        cuerpo = self.doc.element.body
        previo = cuerpo[-1] if len(cuerpo) else None
        if previo is not None and previo.tag.endswith("}sectPr"):
            previo = previo.getprevious()
        if (previo is not None and previo.tag.endswith("}p") and not "".join(previo.itertext()).strip()
                and not previo.xpath(".//w:drawing | .//w:br | .//w:fldChar | .//w:fldSimple")):
            cuerpo.remove(previo)
        self.doc.add_heading(self.t(clave), 1)

    def h2(self, clave):
        self.doc.add_heading(self.t(clave), 2)

    def tabla(self, rotulo, encabezados, filas, **kw):
        if rotulo:
            _rotulo(self.doc, self.lang, rotulo, self.numerador, "tabla")
        return _tabla(self.doc, encabezados, filas, **kw)

    def tabla_kv(self, rotulo, filas, encabezados=None, anchos=(3.2, 3.3), tam=None):
        if rotulo:
            _rotulo(self.doc, self.lang, rotulo, self.numerador, "tabla")
        return _tabla_kv(self.doc, filas, self.lang, encabezados=encabezados, anchos=anchos, tam=tam)

    def fig(self, png, pie, ancho=6.0):
        return _figura(self.doc, png, self.lang, pie, self.numerador, ancho)

    def veredicto_iec(self):
        cumple = self.d["iec"].get("cumple")
        return self.t("cumple") if cumple is True else (self.t("no_cumple") if cumple is False else self.t("sin_datos"))

    # ── portada, control e índice ──
    def portada(self):
        doc = self.doc
        pr, tb, inc, eco = self.d["proyecto"], self.d["turbina"], self.d["incertidumbre"], self.d["economia"]
        if self.logo:
            try:
                parrafo = doc.add_paragraph()
                parrafo.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                parrafo.add_run().add_picture(io.BytesIO(self.logo), height=Inches(0.7))
            except Exception:
                pass
        _espacio(doc, 10)
        _banda(doc, self.t("titulo"), self.t("subtitulo"))
        _espacio(doc, 16)
        _p(doc, pr["nombre"], bold=True, tam=22, color=MARINO)
        _p(doc, f"{pr['pais_nombre']}  ·  {self.n(pr['lat'], 5)}, {self.n(pr['lon'], 5)}  ·  {self.ctx['fecha_generacion'][:10]}",
           tam=11, color=GRIS)
        _espacio(doc, 8)
        lcoe = en_moneda(eco.get("lcoe_mwh"), eco)
        _tarjetas(doc, [
            (self.u(tb.get("p_instalada_mw"), "MW", 1), self.t("k_capacidad")),
            (self.n(inc.get("p50"), 0), f"{self.t('k_p50')} ({self.t('mwh_anio')})"),
            (self.n(inc.get("p90"), 0), f"{self.t('k_p90').split(' (')[0]} ({self.t('mwh_anio')})"),
            (self.n(lcoe, 2) if lcoe is not None else "—", f"LCOE ({self.moneda}/MWh)"),
        ])
        self.tabla_kv(None, [
            (self.t("cliente"), pr["cliente"] or "—"),
            (self.t("autor"), pr["autor"] or "—"),
            (self.t("pais"), f"{pr['pais_nombre']} ({pr['pais_codigo']})"),
            (self.t("coordenadas"), f"{self.n(pr['lat'], 6)}, {self.n(pr['lon'], 6)}"),
            (self.t("fecha"), self.ctx["fecha_generacion"][:10]),
            (self.t("codigo_doc"), self.ctx["codigo"]),
            (self.t("revision"), self.ctx["revision"]),
            (self.t("estado_doc"), self.t("borrador")),
            (self.t("version_sma"), "2.0"),
        ], encabezados=(self.t("campo"), self.t("valor")), anchos=(2.4, 4.1))
        _callout(doc, self.t("aviso_t"), self.t("aviso_b"), color=ROJO, fondo=ROJO_FONDO)
        doc.add_page_break()

    def control_e_indice(self):
        doc, pr = self.doc, self.d["proyecto"]
        titulo = _p(doc, self.t("control_doc"), bold=True, tam=15, color=MARINO)
        _borde_parrafo(titulo, grosor=8, color=MARINO)
        _p(doc, self.t("control_intro"), italic=True, color=GRIS)
        self.tabla(self.t("tb_control"), (self.t("rev"), self.t("fecha"), self.t("preparado"), self.t("revisado"),
                                          self.t("notas")),
                   [(self.ctx["revision"], self.ctx["fecha_generacion"][:10], pr["autor"] or "—", "—", self.t("rev_nota"))],
                   anchos=[0.6, 1.1, 1.5, 1.3, 2.0])
        _espacio(doc, 16)
        _indice(doc, self.lang)
        doc.add_page_break()

    # ── 1. Resumen ejecutivo ──
    def resumen(self):
        d, doc = self.d, self.doc
        pr, tb, rec, en, inc, eco = d["proyecto"], d["turbina"], d["recurso"], d["energia"], d["incertidumbre"], d["economia"]
        self.h1("s1")
        irr, npv = num(eco.get("irr_pct")), num(eco.get("npv"))
        wacc = num((pr.get("perfil_pais") or {}).get("wacc_tipico_pct"))
        h = tb.get("altura_buje_m")
        lcoe = en_moneda(eco.get("lcoe_mwh"), eco)
        _tarjetas(doc, [
            (self.u(tb.get("p_instalada_mw"), "MW", 1), self.t("k_capacidad")),
            (self.u(rec.get("v_media_buje"), "m/s", 2), self.t("kc_v", h=self.n(h, 0))),
            (self.n(en.get("aep_neta_mwh"), 0), f"{self.t('c_neta')} ({self.t('mwh_anio')})"),
            (self.n(inc.get("p90"), 0), f"AEP P90 ({self.t('mwh_anio')})"),
            (self.pct(en.get("fp_neto_pct"), 1), self.t("k_fp_neto")),
            (self.n(lcoe, 2) if lcoe is not None else "—", f"LCOE ({self.moneda}/MWh)"),
            (self.dinero_corto(npv), self.t("k_npv")),
            (self.pct(irr, 2), self.t("k_irr")),
        ])
        precio = en_moneda(eco.get("precio_mwh"), eco)
        _p(doc, self.t("concl_pre_t"), bold=True, color=MARINO, tam=11)
        _p(doc, self.t("concl_pre_b", n=self.n(tb.get("n_turbinas"), 0), kw=self.n(tb.get("p_nominal_kw"), 0),
                       mw=self.n(tb.get("p_instalada_mw"), 1), pais=pr["pais_nombre"], aep=self.n(en.get("aep_neta_mwh"), 0),
                       fp=self.pct(en.get("fp_neto_pct"), 1), p90=self.n(inc.get("p90"), 0),
                       precio=f"{self.moneda} {self.n(precio, 2)}/MWh" if precio is not None else "—",
                       npv=self.dinero(npv), irr=self.pct(irr)), alinear="justificado")
        campos = dict(irr=self.pct(irr), wacc=self.pct(wacc), npv=self.dinero(npv), pais=pr["pais_nombre"])
        if irr is None or npv is None:
            clave, color, fondo = "ver_nd", AMBAR, AMBAR_FONDO
        elif any(a["clave"] in ("capex", "precio") for a in d["avisos"]):
            clave, color, fondo = "ver_nc", AMBAR, AMBAR_FONDO
        elif wacc is not None and irr >= wacc and npv > 0:
            clave, color, fondo = "ver_ok", VERDE, VERDE_FONDO
        else:
            clave, color, fondo = "ver_it", AMBAR, AMBAR_FONDO
        _callout(doc, self.t(f"{clave}_t"), self.t(f"{clave}_b", **campos), color=color, fondo=fondo)
        if d["avisos"]:
            _callout(doc, self.t("avisos_t"), [texto_aviso(a, self.lang) for a in d["avisos"]], color=AMBAR,
                     fondo=AMBAR_FONDO)
        self.h2("s1_1")
        _vinetas(doc, self.hallazgos())
        sufijo_p = "" if inc["fuente"] == "monte_carlo" else f" ({self.t('mcold_t' if inc.get('mc_obsoleto') else 'gen_t')})"
        capacidad = self.u(tb.get("p_instalada_mw"), "MW", 2)
        if tb.get("n_turbinas") and tb.get("p_nominal_kw"):
            capacidad += f" ({tb['n_turbinas']} × {self.n(tb['p_nominal_kw'], 0)} kW)"
        self.tabla_kv(self.t("tb_kpis"), [
            (self.t("k_capacidad"), capacidad),
            (self.t("k_turbina"), f"{tb.get('modelo') or self.t('curva_fase1')} · D {self.n(tb.get('diametro_m'), 1)} m"),
            (f"{self.t('k_v_buje')} ({self.n(h, 0)} m)", self.u(rec.get("v_media_buje"), "m/s", 2)),
            (self.t("k_aep_bruta"), self.mwh(en.get("aep_bruta_mwh"))),
            (self.t("k_aep_neta"), self.mwh(en.get("aep_neta_mwh"))),
            (self.t("k_p50"), self.mwh(inc.get("p50")) + sufijo_p),
            (self.t("k_p90"), self.mwh(inc.get("p90")) + sufijo_p),
            (self.t("k_fp_neto"), self.pct(en.get("fp_neto_pct"), 1)),
            (self.t("k_lcoe"), f"{self.moneda} {self.n(lcoe, 2)}/MWh" if lcoe is not None else "—"),
            (self.t("k_npv"), self.dinero(npv)),
            (self.t("k_irr"), self.pct(irr)),
            (self.t("k_wacc"), self.pct(wacc, 1)),
            (self.t("k_payback_d"), self.u(eco.get("payback_desc"), self.t("anios"), 1)),
            (self.t("k_capex"), self.dinero(eco.get("capex_total"))),
            (self.t("k_opex"), self.dinero(eco.get("opex_total"))),
        ], anchos=(3.3, 3.2), tam=8.5)

    def hallazgos(self):
        d = self.d
        pr, tb, rec, en, inc, iec, amb, eco = (d["proyecto"], d["turbina"], d["recurso"], d["energia"], d["incertidumbre"],
                                              d["iec"], d["ambiental"], d["economia"])
        items = [self.t("h_recurso", v=self.n(rec.get("v_media_buje"), 2), h=self.n(tb.get("altura_buje_m"), 0),
                        fuente=pr["fuente"], inicio=pr["inicio"], fin=pr["fin"], modelo=rec.get("modelo_altura") or "—")]
        estela = self.t("h_estela", pct=self.pct(en.get("estela_pct")), mwh=self.n(en.get("perdida_estela_mwh"), 0),
                        modo=en.get("wake_mode") or "—")
        if en.get("peor_sector") and num(en.get("peor_sector_pct")) is not None:
            estela += self.t("h_estela_f4", sector=en["peor_sector"], pct=self.pct(en["peor_sector_pct"]))
        items.append(estela)
        items.append(self.t("h_perdidas", pct=self.pct(en.get("perdida_total_pct")), fp=self.pct(en.get("fp_neto_pct"), 1)))
        if inc["fuente"] == "monte_carlo":
            ratio = (inc.get("ratio_p90_p50") or 0) * 100.0 if inc.get("ratio_p90_p50") else None
            items.append(self.t("h_mc", p90=self.n(inc.get("p90"), 0), ratio=self.pct(ratio, 1),
                                cv=self.pct(inc.get("cv_pct")), n=self.n(inc.get("n"), 0)))
        else:
            items.append(self.t("h_mc_old" if inc.get("mc_obsoleto") else "h_mc_gen", p90=self.n(inc.get("p90"), 0),
                                cv=self.pct(inc.get("cv_pct"))))
        items.append(self.t("h_iec", clase=iec["clase_declarada"], cat=iec["categoria_declarada"],
                            v=self.n(iec.get("v_avg_sitio"), 2), lim=self.n(iec.get("v_avg_clase"), 1),
                            ti=self.n(iec.get("ti_15_sitio"), 3), ti_lim=self.n(iec.get("ti_clase"), 2),
                            res=self.veredicto_iec()))
        if amb.get("ruido_analizado"):
            items.append(self.t("h_ruido", db=self.n(amb.get("ruido_max_db"), 1), dia=self.n(amb.get("ruido_lim_dia"), 0),
                                noche=self.n(amb.get("ruido_lim_noche"), 0)))
        if amb.get("flicker_analizado"):
            items.append(self.t("h_flicker", h=self.n(amb.get("flicker_max_h"), 1), lim=self.n(amb.get("flicker_lim_h"), 0)))
        if not amb.get("ruido_analizado") and not amb.get("flicker_analizado"):
            items.append(self.t("h_amb_no"))
        precio = en_moneda(eco.get("precio_mwh"), eco)
        items.append(self.t("h_eco", npv=self.dinero(eco.get("npv")), irr=self.pct(eco.get("irr_pct")),
                            precio=f"{self.moneda} {self.n(precio, 2)}/MWh" if precio is not None else "—",
                            tasa=self.pct(eco.get("tasa_pct"), 1)))
        return items


    # ── 2. Proyecto ──
    def proyecto(self):
        d, doc = self.d, self.doc
        pr, tb, rec = d["proyecto"], d["turbina"], d["recurso"]
        self.h1("s2")
        self.h2("s2_1")
        self.tabla_kv(self.t("tb_sitio"), [
            (self.t("latitud"), self.n(pr["lat"], 6)),
            (self.t("longitud"), self.n(pr["lon"], 6)),
            (self.t("pais_informe"), f"{pr['pais_nombre']} ({pr['pais_codigo']})"),
            (self.t("pais_coord"), pr["pais_inferido_nombre"]) if pr.get("pais_inferido_nombre") else None,
            (self.t("fuente_datos"), pr["fuente"]),
            (self.t("periodo"), f"{pr['inicio']} → {pr['fin']}"),
            (self.t("altitud"), self.u(rec.get("altitud_m"), "m", 0)),
            (self.t("temperatura"), self.u(rec.get("temperatura_c"), "°C", 1)),
            (self.t("densidad_sitio"), self.u(rec.get("densidad_sitio"), "kg/m³", 3)),
        ])
        self.h2("s2_2")
        _p(doc, self.t("turbina_intro"))
        self.tabla_kv(self.t("tb_turbina"), [
            (self.t("modelo"), tb.get("modelo") or self.t("curva_fase1")),
            (self.t("diametro"), self.u(tb.get("diametro_m"), "m", 1)),
            (self.t("area"), self.u(tb.get("area_m2"), "m²", 0)),
            (self.t("altura_buje"), self.u(tb.get("altura_buje_m"), "m", 1)),
            (self.t("p_nominal"), self.u(tb.get("p_nominal_kw"), "kW", 0)),
            (self.t("n_aero"), self.n(tb.get("n_turbinas"), 0)),
            (self.t("k_capacidad"), self.u(tb.get("p_instalada_mw"), "MW", 2)),
            (self.t("cut_in"), self.u(tb.get("cut_in"), "m/s", 1)),
            (self.t("v_nominal"), self.u(tb.get("v_nominal"), "m/s", 1)),
            (self.t("cut_out"), self.u(tb.get("cut_out"), "m/s", 1)),
            (self.t("ct"), self.n(tb.get("ct"), 3)),
            (self.t("dens_curva"), self.u(tb.get("densidad_curva"), "kg/m³", 3)),
        ])
        self.fig(graficas.curva_potencia(
            tb.get("df_curva"), self.lang, diametro=tb.get("diametro_m"), densidad=tb.get("densidad_curva"),
            marcas=[(self.t("m_arranque"), tb.get("cut_in")), (self.t("m_nominal"), tb.get("v_nominal")),
                    (self.t("m_parada"), tb.get("cut_out"))],
            eje_x=self.t("ax_v"), eje_p=self.t("ax_p_kw"), eje_cp=self.t("ax_cp"), leyenda=(self.t("lg_potencia"), "Cp"),
        ), self.t("cap_curva2"))
        self.h2("s2_3")
        lo = d["layout"]
        turbinas = lo.get("turbinas") or []
        if turbinas:
            texto = self.t("layout_tipo", tipo=lo.get("tipo") or "—")
            if lo.get("dx_D") and lo.get("dy_D"):
                texto += self.t("layout_sep", dx=self.n(lo["dx_D"], 1), dy=self.n(lo["dy_D"], 1))
            _p(doc, texto)
            self.tabla(self.t("tb_layout"), (self.t("turbina_col"), "X (m)", "Y (m)"),
                       [(t["id"], self.n(t["x_m"], 1), self.n(t["y_m"], 1)) for t in turbinas], anchos=[2.1, 2.2, 2.2])
            self.fig(graficas.disposicion(turbinas, tb.get("diametro_m"), self.lang),
                     self.t("cap_layout", n=len(turbinas), d=self.n(tb.get("diametro_m"), 1)))
        else:
            _p(doc, self.t("layout_no"), italic=True)

    # ── 3. Recurso eólico ──
    def recurso(self):
        d, doc = self.d, self.doc
        pr, tb, rec = d["proyecto"], d["turbina"], d["recurso"]
        h = tb.get("altura_buje_m")
        self.h1("s3")
        ws, wd, etiqueta = _serie_viento(d, self.lang)
        stats = estadistica_sectores(ws, wd) if ws is not None and wd is not None else []
        if stats:
            self.fig(graficas.rosa_por_clases(ws, wd, self.lang), self.t("cap_rosa2", serie=etiqueta), ancho=4.5)
        if ws is not None:
            self.fig(graficas.histograma_weibull(ws, self.lang, eje_x=self.t("ax_v"), eje_y=self.t("ax_frec_rel"),
                                                 etiqueta_media=self.t("lg_media")),
                     self.t("cap_hist", serie=etiqueta))
        self.h2("s3_1")
        filas = [
            (self.t("fuente_datos"), pr["fuente"]),
            (self.t("periodo"), f"{pr['inicio']} → {pr['fin']}"),
            (self.t("altura_ref"), self.u(rec.get("altura_referencia_m"), "m", 0)),
            (self.t("altura_buje"), self.u(h, "m", 1)),
            (self.t("serie_usada"), _tipo_serie(rec.get("serie_uso"), self.lang)),
            (self.t("mcp_aplicado"), self.t("si") if rec.get("mcp_aplicado") else self.t("no")),
        ]
        if rec.get("mcp_aplicado"):
            filas += [(self.t("mcp_r2"), self.n(rec.get("mcp_r2"), 3)), (self.t("mcp_rmse"), self.u(rec.get("mcp_rmse"), "m/s", 3))]
        filas.append((self.t("torre"), self.t("disponible") if rec.get("torre_disponible") else self.t("no_disponible")))
        if rec.get("torre_disponible"):
            filas.append((self.t("torre_rec"), self.pct(rec.get("torre_recovery_pct"), 1)))
        self.tabla_kv(self.t("tb_fuente"), filas)
        self.h2("s3_2")
        _p(doc, self.t("perfil_txt", modelo=rec.get("modelo_altura") or "—", href=self.n(rec.get("altura_referencia_m"), 0),
                       h=self.n(h, 0)))
        alpha_med = rec.get("alpha_mediana")
        self.tabla_kv(self.t("tb_perfil"), [
            (self.t("v10"), self.u(rec.get("v10"), "m/s", 2)),
            (self.t("v50"), self.u(rec.get("v50"), "m/s", 2)),
            (f"{self.t('k_v_buje')} ({self.n(h, 0)} m)", self.u(rec.get("v_media_buje"), "m/s", 2)),
            (self.t("alpha"), self.n(rec.get("alpha"), 3)),
            (self.t("alpha_med"), f"{self.n(alpha_med, 3)} ({self.n(rec.get('alpha_p25'), 3)}–{self.n(rec.get('alpha_p75'), 3)}, "
                                  f"n = {self.n(rec.get('alpha_n'), 0)})") if alpha_med is not None else None,
            (self.t("ustar"), self.u(rec.get("u_star"), "m/s", 3)),
            (self.t("z0"), self.u(rec.get("z0"), "m", 4)),
            (self.t("rugosidad"), rec.get("rugosidad") or "—"),
        ])
        self.h2("s3_3")
        self.tabla_kv(self.t("tb_ti"), [
            (self.t("ti_amb"), self.n(rec.get("ti_ambiente"), 3)),
            (self.t("ti15"), self.n(rec.get("ti_15"), 3)),
            (self.t("densidad_sitio"), self.u(rec.get("densidad_sitio"), "kg/m³", 3)),
            (self.t("dens_std"), self.u(1.225, "kg/m³", 3)),
            (self.t("altitud"), self.u(rec.get("altitud_m"), "m", 0)),
            (self.t("temperatura"), self.u(rec.get("temperatura_c"), "°C", 1)),
        ])
        if stats:
            self.h2("s3_4")
            _p(doc, self.t("sector_txt", serie=etiqueta))
            nombres = sectores_16(self.lang)
            self.tabla(self.t("tb_sectores"), (self.t("sector"), self.t("frecuencia"), self.t("v_media_sector")),
                       [(nombres[s], self.n(f, 2), self.n(v, 2)) for s, f, v in stats], anchos=[2.1, 2.2, 2.2])
        if rec.get("torre_disponible"):
            _callout(doc, self.t("rec_torre_t"), self.t("rec_torre_ok_b", rec=self.pct(rec.get("torre_recovery_pct"), 1)))
        else:
            _callout(doc, self.t("rec_torre_t"), self.t("rec_torre_b", fuente=pr["fuente"]))

    # ── 4. Producción ──
    def produccion(self):
        d, doc = self.d, self.doc
        tb, en = d["turbina"], d["energia"]
        self.h1("s4")
        _p(doc, self.t("energia_intro", metodo=en.get("metodo") or "—", h=self.n(tb.get("altura_buje_m"), 0),
                       modo=en.get("wake_mode") or "—"), alinear="justificado")
        self.h2("s4_1")
        pasos = en.get("cascada") or []
        neta = en.get("aep_neta_mwh")
        if pasos:
            filas = [(self.t("c_bruta"), "—", "—", self.n(pasos[0]["acumulada_mwh"], 0))]
            for paso in pasos[1:]:
                filas.append((self.t(f"c_{paso['clave']}"), self.pct(paso["pct"]), self.n(paso["perdida_mwh"], 0),
                              self.n(paso["acumulada_mwh"], 0)))
            bruta = pasos[0]["acumulada_mwh"]
            filas.append((self.t("c_neta"), self.pct(en.get("perdida_total_pct")),
                          self.n((bruta - neta) if (bruta and neta is not None) else None, 0), self.n(neta, 0)))
            self.tabla(self.t("tb_cascada"), (self.t("concepto"), self.t("perdida_pct"), self.t("perdida_mwh"),
                                              self.t("aep_acum")), filas, anchos=[2.6, 1.1, 1.4, 1.4], total=True)
            etiquetas = {"bruta": self.t("c_bruta"), "neta": self.t("c_neta")}
            etiquetas.update({p["clave"]: self.t(f"c_{p['clave']}") for p in pasos[1:]})
            self.fig(graficas.cascada(pasos, neta, self.lang, etiquetas=etiquetas, eje_y=self.t("ax_aep")),
                     self.t("cap_cascada"))
        else:
            _p(doc, self.t("no_calculado"), italic=True)
        self.h2("s4_2")
        self.tabla_kv(self.t("tb_energia"), [
            (self.t("k_aep_bruta"), self.mwh(en.get("aep_bruta_mwh"))),
            (self.t("k_aep_estela"), self.mwh(en.get("aep_con_estela_mwh"))),
            (self.t("k_aep_neta"), self.mwh(neta)),
            (self.t("perdida_total"), self.pct(en.get("perdida_total_pct"))),
            (self.t("k_fp_bruto"), self.pct(en.get("fp_bruto_pct"), 1)),
            (self.t("k_fp_neto"), self.pct(en.get("fp_neto_pct"), 1)),
            (self.t("metodo"), en.get("metodo") or "—"),
            (self.t("modo_estela"), en.get("wake_mode") or "—"),
            (self.t("modelo_estela"), en.get("wake_model") or "—") if en.get("wake_automatica") else None,
            (self.t("perdida_estela"), f"{self.pct(en.get('estela_pct'))} ({self.mwh(en.get('perdida_estela_mwh'))})"),
            (self.t("f4_ponderada"), self.pct(en.get("f4_perdida_ponderada_pct"), 3))
            if en.get("f4_perdida_ponderada_pct") is not None else None,
        ])
        f4, f5 = num(en.get("f4_perdida_ponderada_pct")), num(en.get("estela_pct"))
        if f4 is not None and f5 is not None and abs(f4 - f5) > 0.01:
            _p(doc, self.t("nota_f4_f5", f4=self.pct(f4, 3), f5=self.pct(f5, 3)), italic=True, tam=9.5, color=GRIS)
        self.h2("s4_3")
        df_sector = en.get("df_aep_sector")
        if df_sector is not None and len(df_sector):
            def col(*partes):
                return next((c for c in df_sector.columns if all(p in str(c).lower() for p in partes)), None)

            c_sec = _columna(df_sector, "Sector", "sector")
            c_frec, c_estela = col("frecuencia"), col("estela", "%")
            c_bruta = col("bruta", "parque") or col("bruta")
            c_neta = col("neta", "sector") or col("neta")
            nombres = dict(zip(sectores_16("en"), sectores_16(self.lang), strict=True))
            filas = [(nombres.get(str(r[c_sec]), str(r[c_sec])) if c_sec else "—",
                      self.n(r[c_frec], 2) if c_frec else "—", self.n(r[c_bruta], 0) if c_bruta else "—",
                      self.pct(r[c_estela], 2) if c_estela else "—", self.n(r[c_neta], 0) if c_neta else "—")
                     for _, r in df_sector.iterrows()]

            def suma(columna):
                return self.n(df_sector[columna].sum(), 0) if columna else "—"

            filas.append((self.t("total"), self.n(df_sector[c_frec].sum(), 2) if c_frec else "—", suma(c_bruta),
                          self.pct(en.get("estela_pct")), suma(c_neta)))
            self.tabla(self.t("tb_sector_e"), (self.t("sector"), self.t("frecuencia"), self.t("aep_bruta_col"),
                                               f"{self.t('c_estela')} (%)", self.t("aep_neta_col")), filas,
                       anchos=[1.1, 1.2, 1.5, 1.2, 1.5], total=True)
        else:
            _p(doc, self.t("sector_no"), italic=True)
        self.h2("s4_4")
        _p(doc, self.t("wtg_nota"), italic=True, tam=9.5, color=GRIS)
        turbinas = d["layout"].get("turbinas") or []
        n_t = len(turbinas) or tb.get("n_turbinas") or 0
        if n_t and neta:
            aep_t = neta / n_t
            p_kw = tb.get("p_nominal_kw")
            fp_t = aep_t / (p_kw / 1000.0 * 8760.0) * 100.0 if p_kw else None
            filas = [(t["id"], self.n(t["x_m"], 1), self.n(t["y_m"], 1), self.n(p_kw, 0), self.n(aep_t, 0), self.n(fp_t, 1))
                     for t in turbinas]
            filas.append((self.t("total"), "—", "—", self.n(p_kw * n_t if p_kw else None, 0), self.n(neta, 0),
                          self.n(en.get("fp_neto_pct"), 1)))
            self.tabla(self.t("tb_wtg"), (self.t("turbina_col"), "X (m)", "Y (m)", self.t("p_nom_kw"),
                                          self.t("aep_neta_col"), self.t("fp_col")),
                       filas, anchos=[1.2, 1.0, 1.0, 1.0, 1.3, 0.8], total=True)


    # ── 5. Incertidumbre ──
    def incertidumbre(self):
        doc, inc = self.doc, self.d["incertidumbre"]
        self.h1("s5")
        if inc["fuente"] == "monte_carlo":
            sig = inc.get("sigmas_entrada") or {}
            _p(doc, self.t("mc_intro", n=self.n(inc.get("n"), 0), semilla=self.n(inc.get("semilla"), 0)), alinear="justificado")
            self.h2("s5_1")
            rel = self.t("relativa")
            entradas = {
                "recurso": f"σk {self.pct(sig.get('k'), 1)} · σc {self.pct(sig.get('c'), 1)}",
                "curva": self.pct(sig.get("curva"), 1),
                "estela": f"{self.pct(sig.get('estela'), 1)} ({rel})",
                "perdidas": f"{self.pct(sig.get('perdidas'), 1)} ({rel})",
            }
            filas = [(self.t(f"u_{item['clave']}"), entradas.get(item["clave"], "—"), self.pct(item["sigma_aep"], 2))
                     for item in inc.get("presupuesto") or []]
            filas.append((self.t("u_rss"), "—", self.pct(inc.get("sigma_rss_pct"), 2)))
            self.tabla(self.t("tb_unc"), (self.t("componente"), self.t("sigma_entrada"), self.t("efecto_aep")), filas,
                       anchos=[2.6, 2.1, 1.8], total=True)
            self.h2("s5_2")
            ratio = inc.get("ratio_p90_p50")
            self.tabla_kv(self.t("tb_mc"), [
                (self.t("k_p50"), self.mwh(inc.get("p50"))),
                (self.t("k_p75"), self.mwh(inc.get("p75"))),
                (self.t("k_p90"), self.mwh(inc.get("p90"))),
                (self.t("k_p99"), self.mwh(inc.get("p99"))),
                (self.t("media_mc"), self.mwh(inc.get("media"))),
                (self.t("desv_mc"), self.mwh(inc.get("desv"))),
                (self.t("cv"), self.pct(inc.get("cv_pct"))),
                (self.t("ratio"), self.pct(ratio * 100.0 if ratio else None, 1)),
                (self.t("muestras"), self.n(inc.get("n"), 0)),
            ])
            self.fig(graficas.distribucion_mc(inc.get("media"), inc.get("desv"), inc, self.lang, eje_x=self.t("ax_aep"),
                                              etiqueta_area=self.t("lg_area_p90")), self.t("cap_mc"))
            _callout(doc, self.t("interp_t"), self.t(
                "interp_b", p90=self.n(inc.get("p90"), 0), p50=self.n(inc.get("p50"), 0),
                dif=self.pct((1.0 - ratio) * 100.0 if ratio else None, 1), cv=self.pct(inc.get("cv_pct")),
                rss=self.pct(inc.get("sigma_rss_pct"))))
        else:
            if inc.get("mc_obsoleto"):
                _callout(doc, self.t("mcold_t"), texto_aviso({"clave": "mc_obsoleto", **inc["mc_obsoleto"]}, self.lang),
                         color=AMBAR, fondo=AMBAR_FONDO)
            else:
                _callout(doc, self.t("gen_t"), self.t("gen_b", sigma=self.pct(inc.get("sigma_rss_pct"))), color=AMBAR,
                         fondo=AMBAR_FONDO)
            self.h2("s5_gen")
            filas = [(self.t(f"g_{k}"), self.pct(v, 1)) for k, v in (inc.get("sigmas_entrada") or {}).items()]
            filas.append((self.t("sigma_total"), self.pct(inc.get("sigma_rss_pct"), 2)))
            self.tabla(self.t("tb_unc"), (self.t("categoria"), self.t("sigma_entrada")), filas, anchos=[4.2, 2.3],
                       total=True)
            self.tabla_kv(self.t("tb_mc"), [(self.t(f"k_{p}"), self.mwh(inc.get(p))) for p in ("p50", "p75", "p90", "p99")])

    # ── 6. IEC 61400-1 ──
    def iec(self):
        doc, iec, rec = self.doc, self.d["iec"], self.d["recurso"]
        self.h1("s6")
        _p(doc, self.t("iec_intro", clase=iec["clase_declarada"], cat=iec["categoria_declarada"]), alinear="justificado")

        def resultado(valor):
            return self.t("cumple") if valor is True else (self.t("no_cumple") if valor is False else self.t("sin_datos"))

        self.tabla(self.t("tb_iec"), (self.t("parametro"), self.t("sitio"),
                                      f"{self.t('limite')} {iec['clase_declarada']}/{iec['categoria_declarada']}",
                                      self.t("resultado")), [
            (self.t("iec_vavg"), self.u(iec.get("v_avg_sitio"), "m/s", 2), self.u(iec.get("v_avg_clase"), "m/s", 1),
             resultado(iec.get("cumple_velocidad"))),
            (self.t("iec_vref"), self.t("no_calculado"), self.u(iec.get("v_ref_clase"), "m/s", 1), self.t("no_evaluado")),
            (self.t("iec_ti"), self.n(iec.get("ti_15_sitio"), 3), self.n(iec.get("ti_clase"), 2),
             resultado(iec.get("cumple_turbulencia"))),
            (self.t("iec_dens"), self.u(rec.get("densidad_sitio"), "kg/m³", 3),
             f"{self.u(1.225, 'kg/m³', 3)} ({self.t('referencia')})", self.t("informativo")),
        ], anchos=[2.6, 1.2, 1.6, 1.1])
        cumple = iec.get("cumple")
        if cumple is True:
            _callout(doc, self.t("iec_ver_t"), self.t("iec_ok"), color=VERDE, fondo=VERDE_FONDO)
        elif cumple is False:
            motivos = ([self.t("iec_no_v")] if iec.get("cumple_velocidad") is False else []) + \
                      ([self.t("iec_no_ti")] if iec.get("cumple_turbulencia") is False else [])
            _callout(doc, self.t("iec_ver_t"), self.t("iec_no", motivos="; ".join(motivos)), color=ROJO, fondo=ROJO_FONDO)
        else:
            _callout(doc, self.t("iec_ver_t"), self.t("iec_nd"), color=AMBAR, fondo=AMBAR_FONDO)

    # ── 7. Ambiental ──
    def _ruido_cumple(self):
        amb = self.d["ambiental"]
        maximo, noche = num(amb.get("ruido_max_db")), num(amb.get("ruido_lim_noche"))
        return None if (maximo is None or noche is None) else maximo <= noche

    def _flicker_cumple(self):
        amb = self.d["ambiental"]
        maximo, limite = num(amb.get("flicker_max_h")), num(amb.get("flicker_lim_h"))
        return None if (maximo is None or limite is None) else maximo <= limite

    def ambiental(self):
        doc, amb, pr = self.doc, self.d["ambiental"], self.d["proyecto"]
        perfil = pr.get("perfil_pais") or {}
        self.h1("s7")
        self.h2("s7_1")
        dia, noche = amb.get("ruido_lim_dia"), amb.get("ruido_lim_noche")
        if amb.get("ruido_analizado"):
            de_pais = (dia == perfil.get("limite_ruido_diurno_db") and noche == perfil.get("limite_ruido_nocturno_db"))
            origen = self.t("lim_origen_pais", pais=pr["pais_nombre"]) if de_pais else self.t("lim_origen_f6")
            _p(doc, self.t("ruido_txt", origen=origen))
            maximo = num(amb.get("ruido_max_db"))

            def veredicto(limite):
                limite = num(limite)
                if maximo is None or limite is None:
                    return self.t("sin_datos")
                return self.t("cumple") if maximo <= limite else self.t("no_cumple")

            self.tabla_kv(self.t("tb_ruido"), [
                (self.t("ruido_max"), self.u(maximo, "dB(A)", 1)),
                (self.t("lim_dia"), f"{self.u(dia, 'dB(A)', 0)} → {veredicto(dia)}"),
                (self.t("lim_noche"), f"{self.u(noche, 'dB(A)', 0)} → {veredicto(noche)}"),
                (self.t("lwa"), self.u(amb.get("ruido_lwa_db"), "dB(A)", 1)) if amb.get("ruido_lwa_db") is not None else None,
            ])
        else:
            _p(doc, self.t("ruido_no", pais=pr["pais_nombre"], dia=self.n(dia, 0), noche=self.n(noche, 0)))
        self.h2("s7_2")
        if amb.get("flicker_analizado"):
            _p(doc, self.t("flicker_txt"))
            cumple = self._flicker_cumple()
            res = self.t("cumple") if cumple is True else (self.t("no_cumple") if cumple is False else self.t("sin_datos"))
            self.tabla_kv(self.t("tb_flicker"), [
                (self.t("flicker_max"), self.u(amb.get("flicker_max_h"), self.t("h_anio"), 1)),
                (self.t("flicker_lim"), f"{self.u(amb.get('flicker_lim_h'), self.t('h_anio'), 0)} → {res}"),
            ])
        else:
            _p(doc, self.t("flicker_no", lim=self.n(amb.get("flicker_lim_h"), 0)))
        self.h2("s7_3")
        _vinetas(doc, [self.t(f"otros_{i}") for i in range(1, 5)])

    # ── 8. Economía ──
    def economia(self):
        doc, eco, pr, en = self.doc, self.d["economia"], self.d["proyecto"], self.d["energia"]
        perfil = pr.get("perfil_pais") or {}
        mon = self.moneda
        self.h1("s8")
        _p(doc, self.t("eco_intro"), alinear="justificado")
        self.h2("s8_1")
        precio = en_moneda(eco.get("precio_mwh"), eco)
        usa_cop = "COP" in (eco.get("moneda_base"), eco.get("moneda"))
        self.tabla_kv(self.t("tb_supuestos"), [
            (self.t("moneda_base"), eco.get("moneda_base") or "—"),
            (self.t("moneda_vis"), mon) if mon != eco.get("moneda_base") else None,
            (self.t("fx"), self.n(eco.get("fx_cop_usd"), 2)) if (usa_cop and eco.get("fx_cop_usd")) else None,
            (self.t("precio"), f"{mon} {self.n(precio, 2)}/MWh" if precio is not None else "—"),
            (self.t("tasa"), self.pct(eco.get("tasa_pct"), 2)),
            (self.t("k_wacc"), self.pct(perfil.get("wacc_tipico_pct"), 1)),
            (self.t("vida"), self.u(eco.get("vida_util"), self.t("anios"), 0)),
            (self.t("degr"), self.pct(eco.get("degradacion_pct"), 2)),
            (self.t("residual"), self.dinero(eco.get("valor_residual"))),
            (self.t("impuesto"), self.pct(perfil.get("tax_rate_pct"), 1)),
            (self.t("prima_riesgo"), self.pct(perfil.get("country_risk_premium_pct"), 1)),
        ])

        self.h2("s8_2")
        capex_total = num(eco.get("capex_total"), 0.0) or 0.0
        items = eco.get("capex_items") or []
        filas = [(tr_concepto(i["concepto"], self.lang), self.dinero(i["valor"]),
                  self.pct(i["valor"] / capex_total * 100.0, 1) if capex_total else "—") for i in items]
        filas.append((self.t("k_capex"), self.dinero(capex_total), self.pct(100.0, 1) if capex_total else "—"))
        self.tabla(self.t("tb_capex"), (self.t("concepto"), self.t("valor"), self.t("pct_total")), filas,
                   anchos=[3.0, 2.2, 1.3], total=True)
        p_inst = num(eco.get("potencia_instalada_mw"))
        if p_inst and capex_total:
            por_kw = en_moneda(capex_total, eco) / (p_inst * 1000.0)
            _tabla_kv(doc, [(self.t("capex_kw"), f"{mon} {self.n(por_kw, 2 if abs(por_kw) < 100 else 0)}/kW")], self.lang)
        self.fig(graficas.dona([(tr_concepto(i["concepto"], self.lang), en_moneda(i["valor"], eco)) for i in items], mon,
                               self.lang, etiqueta_total=self.t("total")), self.t("cap_capex"), ancho=5.6)

        self.h2("s8_3")
        opex_total = num(eco.get("opex_total"), 0.0) or 0.0
        items = eco.get("opex_items") or []
        if items:
            filas = [(tr_concepto(i["concepto"], self.lang), self.dinero(i["valor"]),
                      self.pct(i["valor"] / opex_total * 100.0, 1) if opex_total else "—") for i in items]
            filas.append((self.t("k_opex"), self.dinero(opex_total), self.pct(100.0, 1) if opex_total else "—"))
            self.tabla(self.t("tb_opex"), (self.t("concepto"), self.t("valor"), self.t("pct_total")), filas,
                       anchos=[3.0, 2.2, 1.3], total=True)
        energia = num(eco.get("energia_neta_mwh")) or num(en.get("aep_neta_mwh"))
        _tabla_kv(doc, [
            None if items else (self.t("k_opex"), self.dinero(opex_total)),
            (self.t("opex_mwh"), f"{mon} {self.n(en_moneda(opex_total / energia, eco), 2)}/MWh" if energia else "—"),
            (self.t("opex_capex"), self.pct(opex_total / capex_total * 100.0, 2) if capex_total else "—"),
        ], self.lang)

        self.h2("s8_4")
        flujo = eco.get("flujo_anual") or []
        anio1 = flujo[1] if len(flujo) > 1 else None
        margen = ((anio1["ingresos"] - anio1["opex"]) / anio1["ingresos"] * 100.0) if (anio1 and anio1["ingresos"]) else None
        lcoe = en_moneda(eco.get("lcoe_mwh"), eco)
        lcoe_kwh = en_moneda(eco.get("lcoe_kwh"), eco)
        self.tabla_kv(self.t("tb_fin"), [
            (f"{self.t('k_lcoe')} (MWh)", f"{mon} {self.n(lcoe, 2)}/MWh" if lcoe is not None else "—"),
            (f"{self.t('k_lcoe')} (kWh)", f"{mon} {self.n(lcoe_kwh, 4)}/kWh" if lcoe_kwh is not None else "—"),
            (self.t("k_npv"), self.dinero(eco.get("npv"))),
            (self.t("k_irr"), self.pct(eco.get("irr_pct"))),
            (self.t("k_payback_s"), self.u(eco.get("payback_simple"), self.t("anios"), 1)),
            (self.t("k_payback_d"), self.u(eco.get("payback_desc"), self.t("anios"), 1)),
            (self.t("vp_costos"), self.dinero(eco.get("vp_costos"))) if eco.get("vp_costos") is not None else None,
            (self.t("ingresos1"), self.dinero(anio1["ingresos"]) if anio1 else "—"),
            (self.t("margen1"), self.pct(margen, 1)),
        ])

        self.h2("s8_5")
        if flujo:
            def m(valor):
                return self.n(en_moneda(valor, eco), 0)

            filas = [(str(f["anio"]), self.n(f["energia_mwh"], 0) if f["anio"] else "—",
                      m(f["ingresos"]) if f["anio"] else "—", m(f["opex"]) if f["anio"] else "—",
                      m(f["inversion"]) if f["inversion"] else "—", m(f["flujo"]), m(f["flujo_desc"]), m(f["acumulado_desc"]))
                     for f in flujo]
            self.tabla(self.t("tb_flujo", moneda=mon), (self.t("anio"), self.t("energia_col"), self.t("ingresos"),
                                                        self.t("opex_col"), self.t("inversion"), self.t("flujo"),
                                                        self.t("flujo_desc"), self.t("acum_desc")), filas,
                       anchos=[0.45, 0.85, 0.9, 0.8, 0.85, 0.9, 0.9, 0.95], tam=7.5)
            vpn_flujo = sum(f["flujo_desc"] for f in flujo)
            _p(doc, self.t("flujo_nota", moneda=mon, npv=self.dinero(vpn_flujo)), italic=True, tam=9.5, color=GRIS)
            self.fig(graficas.flujo_caja(
                [f["anio"] for f in flujo], [en_moneda(f["flujo"], eco) for f in flujo],
                [en_moneda(f["acumulado_desc"], eco) for f in flujo], mon, self.lang,
                etiquetas={"flujo": self.t("flujo"), "acumulado": self.t("acum_desc"), "anio": self.t("anio"),
                           "eje": self.t("ax_flujo"), "recuperacion": self.t("lg_recuperacion")},
            ), self.t("cap_flujo", moneda=mon))
        else:
            _p(doc, self.t("flujo_no"), italic=True)

        self.h2("s8_6")
        sens, npv = eco.get("sensibilidad") or [], num(eco.get("npv"))
        delta = eco.get("sens_delta_pct") or 15.0
        if sens and npv is not None:
            _p(doc, self.t("sens_intro", d=self.n(delta, 0)))
            d_txt = self.n(delta, 0)
            self.tabla(self.t("tb_sens"), (self.t("variable"), self.t("npv_menos", d=d_txt), self.t("npv_base"),
                                           self.t("npv_mas", d=d_txt), self.t("rango")),
                       [(self.t(f"v_{s['clave']}"), self.dinero(s["npv_menos"]), self.dinero(npv), self.dinero(s["npv_mas"]),
                         self.dinero(s["rango"])) for s in sens], anchos=[1.4, 1.3, 1.3, 1.3, 1.2])
            convertidas = [{**s, "npv_menos": en_moneda(s["npv_menos"], eco), "npv_mas": en_moneda(s["npv_mas"], eco)}
                           for s in sens]
            self.fig(graficas.tornado(convertidas, en_moneda(npv, eco), mon, self.lang,
                                      etiquetas={s["clave"]: self.t(f"v_{s['clave']}") for s in sens}, delta=delta,
                                      eje_x=self.t("ax_delta_npv")), self.t("cap_tornado", d=d_txt))
        else:
            _p(doc, self.t("sens_no"), italic=True)

        self.h2("s8_7")
        _p(doc, self.t("reg_intro", pais=pr["pais_nombre"]))
        cur = perfil.get("currency") or "—"
        self.tabla_kv(self.t("tb_reg"), [
            (self.t("mecanismo"), perfil.get("mecanismo_descripcion") or "—"),
            (self.t("valor_ref_mec"), f"{self.n(perfil.get('mecanismo_valor_default'), 2)} {perfil.get('mecanismo_unidad', '')}"),
            (self.t("moneda_local"), cur),
            (self.t("fx_aprox"), f"{self.n(perfil.get('fx_to_usd_aprox'), 2)} {cur}/USD"),
            (self.t("impuesto"), self.pct(perfil.get("tax_rate_pct"), 1)),
            (self.t("k_wacc"), self.pct(perfil.get("wacc_tipico_pct"), 1)),
            (self.t("limites_ruido"), f"{self.n(perfil.get('limite_ruido_diurno_db'), 0)} / "
                                      f"{self.n(perfil.get('limite_ruido_nocturno_db'), 0)} dB(A)"),
        ], encabezados=(self.t("aspecto"), self.t("detalle")), anchos=(2.6, 3.9))
        _p(doc, self.t("legal_t"), bold=True, color=MARINO)
        _vinetas(doc, [self.t(f"legal_{i}") for i in range(1, 6)])

        self.h2("s8_8")
        _p(doc, self.t("check_intro"))
        amb = self.d["ambiental"]

        def estado_f6(analizado, cumple):
            if not analizado:
                return self.t("no_evaluado")
            res = self.t("cumple") if cumple is True else (self.t("no_cumple") if cumple is False else self.t("sin_datos"))
            return self.t("ck_eval_f6", res=res)

        mc = self.d["incertidumbre"]["fuente"] == "monte_carlo"
        estado_unc = "ck_unc_e_mc" if mc else ("ck_unc_e_old" if self.d["incertidumbre"].get("mc_obsoleto") else "ck_unc_e_gen")
        self.tabla(self.t("tb_normas"), (self.t("norma"), self.t("aspecto"), self.t("estado"), self.t("accion")), [
            ("IEC 61400-1", self.t("ck_iec1_a"), self.t("ck_iec1_e", res=self.veredicto_iec()), self.t("ck_iec1_x")),
            ("IEC 61400-12-1", self.t("ck_pc_a"), self.t("ck_pc_e"), self.t("ck_pc_x")),
            ("IEC 61400-15-2", self.t("ck_unc_a"), self.t(estado_unc), self.t("ck_unc_x")),
            ("ISO 9613-2", self.t("ck_ruido_a"), estado_f6(amb.get("ruido_analizado"), self._ruido_cumple()),
             self.t("ck_ruido_x")),
            ("—", self.t("ck_flicker_a"), estado_f6(amb.get("flicker_analizado"), self._flicker_cumple()),
             self.t("ck_flicker_x")),
            ("IEC 61400-22 / DNV-SE-0073", self.t("ck_cert_a"), self.t("ck_fuera"), self.t("ck_cert_x")),
            ("DNV-ST-0437", self.t("ck_cargas_a"), self.t("ck_fuera"), self.t("ck_cargas_x")),
            ("ISO 14001", self.t("ck_iso14001_a"), self.t("ck_fuera"), self.t("ck_iso14001_x")),
            ("IFC PS / Equator Principles", self.t("ck_ifc_a"), self.t("ck_fuera"), self.t("ck_ifc_x")),
        ], anchos=[1.3, 1.8, 1.7, 1.7], tam=8.5)


    # ── 9. Riesgos ──
    def riesgos(self):
        d, doc = self.d, self.doc
        pr, rec, iec = d["proyecto"], d["recurso"], d["iec"]
        perfil = pr.get("perfil_pais") or {}
        self.h1("s9")
        _p(doc, self.t("riesgos_nota"), italic=True, tam=9.5, color=GRIS)
        baja, media, alta = self.t("baja"), self.t("media"), self.t("alta")
        sin_medicion = not rec.get("torre_disponible") and not rec.get("mcp_aplicado")
        moneda_local = perfil.get("currency") or d["economia"].get("moneda_base") or "USD"
        riesgo_fx = moneda_local != "USD"
        filas = [
            ("cat_tec", self.t("r1"), f"{alta}*" if sin_medicion else media, alta, "critico" if sin_medicion else "alto", "m1"),
            ("cat_tec", self.t("r2"), media, media, "medio", "m2"),
            ("cat_tec", self.t("r3"), media, media, "medio", "m3"),
            ("cat_op", self.t("r4"), media, media, "medio", "m4"),
            ("cat_op", self.t("r5"), baja, media, "bajo", "m5"),
            ("cat_reg", self.t("r6", mec=perfil.get("mecanismo_descripcion") or "—"), media, alta, "alto", "m6"),
            ("cat_fin", self.t("r7", cur=moneda_local), alta if riesgo_fx else baja, alta,
             "critico" if riesgo_fx else "medio", "m7"),
            ("cat_fin", self.t("r8"), media, alta, "alto", "m8"),
            ("cat_soc", self.t("r9"), media, alta, "alto", "m9"),
            ("cat_amb", self.t("r10"), media, alta, "alto", "m10"),
            ("cat_red", self.t("r11"), media, alta, "alto", "m11"),
            ("cat_con", self.t("r12"), media, media, "medio", "m12"),
        ]
        if iec.get("cumple") is False:
            filas.append(("cat_tec", self.t("r_iec"), alta, alta, "critico", "m_iec"))
        if self._ruido_cumple() is False:
            filas.append(("cat_amb", self.t("r_ruido"), alta, alta, "alto", "m_ruido"))
        if self._flicker_cumple() is False:
            filas.append(("cat_amb", self.t("r_flicker"), alta, media, "alto", "m_flicker"))
        if any(a["clave"] in ("capex", "precio") for a in d["avisos"]):
            filas.append(("cat_fin", self.t("r_datos"), alta, alta, "critico", "m_datos"))
        self.tabla(self.t("tb_riesgos"), (self.t("r_cat"), self.t("r_riesgo"), self.t("r_prob"), self.t("r_imp"),
                                          self.t("r_nivel"), self.t("r_mit")),
                   [(self.t(c), r, p, i, self.t(nv), self.t(m)) for c, r, p, i, nv, m in filas],
                   anchos=[1.1, 1.75, 1.0, 0.75, 0.7, 1.7], tam=8)  # «Environnemental» / «Probabilidade» caben enteras

    # ── 10. Conclusiones ──
    def conclusiones(self):
        d, doc = self.d, self.doc
        pr, rec, iec, amb, eco = d["proyecto"], d["recurso"], d["iec"], d["ambiental"], d["economia"]
        self.h1("s10")
        _p(doc, self.t("concl_intro", nombre=pr["nombre"], pais=pr["pais_nombre"]))
        items = [self.t("rc_validar")]
        items.append(self.t("rc_torre_ok") if rec.get("torre_disponible") else self.t("rc_medicion", fuente=pr["fuente"]))
        if iec.get("cumple") is False:
            items.append(self.t("rc_iec_no", clase=iec["clase_declarada"], cat=iec["categoria_declarada"]))
        if rec.get("ti_15") is not None:
            items.append(self.t("rc_ti"))
        if self._ruido_cumple() is False:
            items.append(self.t("rc_ruido", db=self.n(amb.get("ruido_max_db"), 1), lim=self.n(amb.get("ruido_lim_noche"), 0)))
        if self._flicker_cumple() is False:
            items.append(self.t("rc_flicker", h=self.n(amb.get("flicker_max_h"), 1), lim=self.n(amb.get("flicker_lim_h"), 0)))
        if not amb.get("ruido_analizado") or not amb.get("flicker_analizado"):
            items.append(self.t("rc_amb_no"))
        irr = num(eco.get("irr_pct"))
        wacc = num((pr.get("perfil_pais") or {}).get("wacc_tipico_pct"))
        if any(a["clave"] in ("capex", "precio") for a in d["avisos"]):
            items.append(self.t("rc_datos"))
        elif irr is not None and wacc is not None and irr < wacc:
            items.append(self.t("rc_iterar", irr=self.pct(irr), wacc=self.pct(wacc, 1)))
        items += [self.t("rc_contingencia"), self.t("rc_red"), self.t("rc_suelo")]
        _vinetas(doc, items, numerada=True)

    # ── 11. Apéndices ──
    def _pasos_metodologia(self):
        d = self.d
        pr, tb, rec, en, inc = d["proyecto"], d["turbina"], d["recurso"], d["energia"], d["incertidumbre"]
        return [
            (self.t("dg_datos"), f"{pr['fuente']}\n{pr['inicio']} → {pr['fin']}"),
            (self.t("dg_perfil"), f"{rec.get('modelo_altura') or '—'}\n{self.n(rec.get('altura_referencia_m'), 0)} → "
                                  f"{self.n(tb.get('altura_buje_m'), 0)} m"),
            (self.t("dg_dist"), self.t("dg_sectores", metodo=en.get("metodo") or "Weibull")),
            (self.t("dg_curva"), f"{self.n(tb.get('n_turbinas'), 0)} × {self.n(tb.get('p_nominal_kw'), 0)} kW\n"
                                 f"D {self.n(tb.get('diametro_m'), 1)} m"),
            (self.t("dg_estelas"), f"{en.get('wake_mode') or '—'}\n{self.pct(en.get('estela_pct'))}"),
            (self.t("dg_perdidas"), self.t("dg_cascada", pct=self.pct(en.get("perdida_total_pct")))),
            (self.t("dg_aep"), self.mwh(en.get("aep_neta_mwh"))),
            (self.t("dg_incert"), self.t("dg_mc", n=self.n(inc.get("n"), 0)) if inc["fuente"] == "monte_carlo"
             else self.t("dg_mc_gen")),
            (self.t("dg_eco"), f"{self.t('k_npv')} · {self.t('k_irr')} · LCOE"),
        ]

    def apendices(self):
        d, doc = self.d, self.doc
        pr, tb, rec, en, inc, eco = d["proyecto"], d["turbina"], d["recurso"], d["energia"], d["incertidumbre"], d["economia"]
        self.h1("s11")
        self.h2("s11_a")
        self.fig(estilo.diagrama_metodologia_png(self._pasos_metodologia(), por_fila=3, destacados=(6,)),
                 self.t("cap_diagrama"), ancho=6.2)
        _vinetas(doc, [
            self.t("ma_datos", fuente=pr["fuente"], inicio=pr["inicio"], fin=pr["fin"],
                   href=self.n(rec.get("altura_referencia_m"), 0), serie=_tipo_serie(rec.get("serie_uso"), self.lang)),
            self.t("ma_perfil", modelo=rec.get("modelo_altura") or "—", h=self.n(tb.get("altura_buje_m"), 0),
                   alpha=self.n(rec.get("alpha"), 3), z0=self.n(rec.get("z0"), 4)),
            self.t("ma_energia", metodo=en.get("metodo") or "—", modo=en.get("wake_mode") or "—",
                   modelo=en.get("wake_model") or "—"),
            self.t("ma_incert", n=self.n(inc.get("n"), 0)) if inc["fuente"] == "monte_carlo" else self.t("ma_incert_gen"),
            self.t("ma_iec"),
            self.t("ma_eco", d=self.n(eco.get("sens_delta_pct"), 0)),
        ])
        self.h2("s11_b")
        _p(doc, self.t("valid_txt"), alinear="justificado")
        self.h2("s11_c")
        _vinetas(doc, [self.t(f"gl_{i}") for i in range(1, 13)])
        self.h2("s11_d")
        _p(doc, self.t("refs_intro"), italic=True, color=GRIS)
        sin_fecha = {"es": "s. f.", "en": "n.d.", "pt": "s.d.", "fr": "s.d."}[self.lang]
        for referencia in REFERENCIAS:
            parrafo = _p(doc, referencia.format(sf=sin_fecha), tam=9.5)
            parrafo.paragraph_format.left_indent = Inches(0.4)
            parrafo.paragraph_format.first_line_indent = Inches(-0.4)
            parrafo.paragraph_format.space_after = Pt(4)
        self.h2("s11_e")
        _p(doc, self.t("limit_txt", fuente=pr["fuente"]), italic=True, alinear="justificado")

    def construir(self):
        pr = self.d["proyecto"]
        _encabezado_y_pie(self.doc, pr["nombre"], self.ctx["codigo"], self.lang, self.logo)
        for seccion in (self.portada, self.control_e_indice, self.resumen, self.proyecto, self.recurso, self.produccion,
                        self.incertidumbre, self.iec, self.ambiental, self.economia, self.riesgos, self.conclusiones,
                        self.apendices):
            seccion()
        buf = io.BytesIO()
        self.doc.save(buf)
        return buf.getvalue()


REFERENCIAS = [
    "Bastankhah, M., & Porté-Agel, F. (2014). A new analytical model for wind-turbine wakes. Renewable Energy, 70, "
    "116–123. https://doi.org/10.1016/j.renene.2014.01.002",
    "DNV GL. (2016). DNVGL-ST-0437: Loads and site conditions for wind turbines. DNV GL.",
    "Frandsen, S. T. (2007). Turbulence and turbulence-generated structural loading in wind turbine clusters "
    "(Risø-R-1188(EN)). Risø National Laboratory.",
    "Hersbach, H., Bell, B., Berrisford, P., Hirahara, S., Horányi, A., Muñoz-Sabater, J., … Thépaut, J.-N. (2020). "
    "The ERA5 global reanalysis. Quarterly Journal of the Royal Meteorological Society, 146(730), 1999–2049. "
    "https://doi.org/10.1002/qj.3803",
    "International Electrotechnical Commission. (2010). IEC 61400-22: Wind turbines — Part 22: Conformity testing and "
    "certification. IEC.",
    "International Electrotechnical Commission. (2019). IEC 61400-1: Wind energy generation systems — Part 1: Design "
    "requirements (4th ed.). IEC.",
    "International Electrotechnical Commission. (2022). IEC 61400-12-1: Wind energy generation systems — Part 12-1: "
    "Power performance measurements of electricity producing wind turbines (3rd ed.). IEC.",
    "International Organization for Standardization. (1996). ISO 9613-2: Acoustics — Attenuation of sound during "
    "propagation outdoors — Part 2: General method of calculation. ISO.",
    "International Renewable Energy Agency. (2024). Renewable power generation costs in 2023. IRENA.",
    "Jensen, N. O. (1983). A note on wind generator interaction (Risø-M-2411). Risø National Laboratory.",
    "Katić, I., Højstrup, J., & Jensen, N. O. (1986). A simple model for cluster efficiency. In Proceedings of the "
    "European Wind Energy Association Conference and Exhibition (pp. 407–410).",
    "NASA Langley Research Center. ({sf}). POWER: Prediction Of Worldwide Energy Resources. https://power.larc.nasa.gov/",
]


# ─────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────
def nombre_base_bankable(ctx, lang="es"):
    """Nombre de archivo sin extensión: <proyecto>_bankable_<idioma> (sin tildes ni espacios)."""
    import unicodedata

    nombre = unicodedata.normalize("NFKD", str(ctx["datos"]["proyecto"]["nombre"])).encode("ascii", "ignore").decode()
    nombre = re.sub(r"[^A-Za-z0-9_-]+", "_", nombre).strip("_") or "proyecto"
    return f"{nombre}_bankable_{lang}"


def generar_reporte_bankable(ctx, lang="es", logo_bytes=None, exportar_pdf=True):
    """Word del reporte (índice, numeración y campos ya actualizados con Microsoft Word si está instalado) + PDF.

    Devuelve {"docx_bytes", "pdf_bytes", "mensaje", "con_word", "log", "nombre_base"}.
    """
    from .pdf_tecnico import finalizar_docx_con_word

    base = nombre_base_bankable(ctx, lang)
    resultado = finalizar_docx_con_word(_Informe(ctx, lang, logo_bytes).construir(), base, exportar_pdf=exportar_pdf)
    resultado["nombre_base"] = base
    return resultado


def generar_reporte_bankable_bytes(ctx, lang="es", logo_bytes=None):
    """Solo el DOCX (compatibilidad con versiones anteriores)."""
    return generar_reporte_bankable(ctx, lang, logo_bytes, exportar_pdf=False)["docx_bytes"]


def generar_reporte_bankable_docx(ctx, output_path, lang="es", logo_path=None):
    """Guarda el DOCX en `output_path` y devuelve la ruta."""
    from pathlib import Path

    logo = Path(logo_path).read_bytes() if logo_path else None
    destino = Path(output_path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(generar_reporte_bankable_bytes(ctx, lang, logo))
    return str(destino)


__all__ = [
    "construir_contexto_bankable", "estadistica_sectores", "generar_reporte_bankable", "generar_reporte_bankable_bytes",
    "generar_reporte_bankable_docx", "nombre_base_bankable", "sectores_16",
]
