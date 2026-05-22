import io
import os
import re
import unicodedata
import zipfile
from copy import deepcopy
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


def _paragraph(text, style=None, spacing_before=0, spacing_after=120, jc=None, bold=False):
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
    ppr.append(f"<w:spacing w:before=\"{int(spacing_before)}\" w:after=\"{int(spacing_after)}\"/>")
    if jc:
        ppr.append(f"<w:jc w:val=\"{jc}\"/>")
    return f"<w:p><w:pPr>{''.join(ppr)}</w:pPr>{''.join(runs)}</w:p>"


def _table_cell(text, header=False):
    text_value = _xml(_clean_text(text))
    run_pr = "<w:rPr><w:b/></w:rPr>" if header else "<w:rPr/>"
    return (
        "<w:tc>"
        "<w:tcPr><w:tcW w:w=\"0\" w:type=\"auto\"/></w:tcPr>"
        "<w:p><w:pPr><w:spacing w:before=\"0\" w:after=\"60\"/></w:pPr>"
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
    if num_cols >= 8:
        return 8
    if num_cols >= 6:
        return 11
    if num_cols >= 4:
        return 16
    return 22


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
    headers = list(block.get("headers", []) or [])
    rows = list(block.get("rows", []) or [])
    if not headers:
        return ""
    tbl_rows = []
    tbl_rows.append("<w:tr>" + "".join(_table_cell(h, header=True) for h in headers) + "</w:tr>")
    for row in rows:
        padded = list(row) + [""] * max(0, len(headers) - len(row))
        tbl_rows.append("<w:tr>" + "".join(_table_cell(cell) for cell in padded[: len(headers)]) + "</w:tr>")
    return (
        "<w:tbl>"
        "<w:tblPr>"
        "<w:tblStyle w:val=\"TableGrid\"/>"
        "<w:tblW w:w=\"0\" w:type=\"auto\"/>"
        "<w:tblBorders>"
        "<w:top w:val=\"single\" w:sz=\"6\" w:space=\"0\" w:color=\"B7C0C7\"/>"
        "<w:left w:val=\"single\" w:sz=\"6\" w:space=\"0\" w:color=\"B7C0C7\"/>"
        "<w:bottom w:val=\"single\" w:sz=\"6\" w:space=\"0\" w:color=\"B7C0C7\"/>"
        "<w:right w:val=\"single\" w:sz=\"6\" w:space=\"0\" w:color=\"B7C0C7\"/>"
        "<w:insideH w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"D9DEE3\"/>"
        "<w:insideV w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"D9DEE3\"/>"
        "</w:tblBorders>"
        "</w:tblPr>"
        "<w:tblGrid/>"
        + "".join(tbl_rows) +
        "</w:tbl>"
    )


def _image_constraints_for_block(block):
    family = str((block or {}).get("figure_family") or "").strip().lower()
    if family == "phase2_time_series":
        return int(6.6 * 914400), int(3.9 * 914400)
    if family == "phase2_profile":
        return int(4.9 * 914400), int(6.0 * 914400)
    if family == "phase2_comparison":
        return int(6.2 * 914400), int(5.2 * 914400)
    if family in ["phase3_wind_rose", "phase4_polar", "phase5_loss_distribution"]:
        return int(5.7 * 914400), int(5.6 * 914400)
    if family in ["phase3_histogram", "phase35_probability_curve", "phase4_comparison", "phase4_energy", "phase5_sector_chart"]:
        return int(6.5 * 914400), int(4.7 * 914400)
    if family in ["phase35_heatmap", "phase4_layout", "phase4_direction_detail"]:
        return int(6.2 * 914400), int(5.4 * 914400)
    return MAX_IMAGE_WIDTH_EMU, MAX_IMAGE_HEIGHT_EMU


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
  <w:pPr><w:jc w:val="center"/><w:spacing w:before="80" w:after="120"/></w:pPr>
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
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{DOCX_NS['w']}">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="120"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:jc w:val="center"/><w:spacing w:before="120" w:after="240"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:b/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:before="180" w:after="80"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:b/><w:sz w:val="24"/></w:rPr>
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


def _root_rels_xml():
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{DOCX_NS['rels']}">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""


def _settings_xml():
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="{DOCX_NS['w']}">
  <w:zoom w:percent="100"/>
</w:settings>
"""


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
        ]
        media_files = []
        doc_pr_id = 1

        body_parts.append(_paragraph(report_model.get("title", "Informe técnico"), style="Title", spacing_after=220))
        project_name = report_model.get("project_name")
        if project_name:
            body_parts.append(_paragraph(project_name, spacing_after=120, jc="center"))
        for paragraph in report_model.get("intro_paragraphs", []) or []:
            body_parts.append(_paragraph(paragraph, spacing_after=140, jc="both"))

        for section in report_model.get("sections", []) or []:
            body_parts.append(_paragraph(section.get("title", "Sección"), style="Heading1"))
            if section.get("description"):
                body_parts.append(_paragraph(section.get("description"), jc="both"))
            for subsection in section.get("subsections", []) or []:
                body_parts.append(_paragraph(subsection.get("title", "Subsección"), style="Heading2"))
                for block in subsection.get("blocks", []) or []:
                    block_title = block.get("title")
                    block_desc = block.get("description")
                    if block.get("type") != "table" and block_title:
                        body_parts.append(_paragraph(block_title, bold=True, spacing_after=80))
                    if block.get("type") != "table" and block_desc:
                        body_parts.append(_paragraph(block_desc, spacing_after=90, jc="both"))
                    if block.get("type") == "table":
                        for table_block in _table_split_blocks(block):
                            if table_block.get("title"):
                                body_parts.append(_paragraph(table_block.get("title", ""), bold=True, spacing_after=60))
                            if table_block.get("description"):
                                body_parts.append(_paragraph(table_block.get("description", ""), spacing_after=70, jc="both"))
                            body_parts.append(_table_block(table_block))
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
                        else:
                            body_parts.append(_paragraph("La figura no pudo insertarse automáticamente en Word."))
                    body_parts.append(_paragraph("", spacing_after=40))

        document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{DOCX_NS['w']}" xmlns:r="{DOCX_NS['r']}" xmlns:wp="{DOCX_NS['wp']}" xmlns:a="{DOCX_NS['a']}" xmlns:pic="{DOCX_NS['pic']}">
  <w:body>
    {''.join(body_parts)}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1224" w:bottom="1440" w:left="1224" w:header="708" w:footer="708" w:gutter="0"/>
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
            zf.writestr("[Content_Types].xml", _content_types_xml(bool(media_files)))
            zf.writestr("_rels/.rels", _root_rels_xml())
            zf.writestr("word/document.xml", document_xml)
            zf.writestr("word/_rels/document.xml.rels", "".join(rels_xml))
            zf.writestr("word/styles.xml", _styles_xml())
            zf.writestr("word/settings.xml", _settings_xml())
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
