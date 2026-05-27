import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from .texto import normalize_spanish_text

LATEX_COMPILERS = ["pdflatex", "xelatex", "lualatex"]
PDF_PAGE_SIZE = (8.5, 11.0)
PDF_FAMILY = "DejaVu Serif"
PDF_COLOR_PRIMARY = "#18324a"
PDF_COLOR_SECONDARY = "#4a5a6a"
PDF_COLOR_BORDER = "#c8d2dc"
PDF_COLOR_PANEL = "#f5f7fa"
PDF_MARGIN_LEFT = 0.08
PDF_MARGIN_RIGHT = 0.92
PDF_CONTENT_TOP = 0.90
PDF_CONTENT_BOTTOM = 0.08
PDF_BODY_FONT = 10.5
PDF_CAPTION_FONT = 9.2
PDF_SMALL_FONT = 8.4


def get_latex_compiler_info(preferred=None):
    candidates = [preferred] if preferred else []
    candidates.extend(name for name in LATEX_COMPILERS if name != preferred)

    for name in candidates:
        if not name:
            continue
        path = shutil.which(name)
        if path:
            return {
                "available": True,
                "compiler": name,
                "path": path,
                "message": f"Compilador LaTeX disponible: {name}.",
            }

    return {
        "available": False,
        "compiler": None,
        "path": None,
        "message": "No se detecto un compilador LaTeX (pdflatex/xelatex/lualatex) en el entorno actual.",
    }


def compile_latex_to_pdf(latex_source, job_name="reporte", preferred_compiler=None, timeout_seconds=90):
    info = get_latex_compiler_info(preferred=preferred_compiler)
    latex_text = str(latex_source or "")

    result = {
        "success": False,
        "pdf_bytes": None,
        "compiler": info.get("compiler"),
        "file_name": f"{job_name}.pdf",
        "message": info.get("message", ""),
        "log_excerpt": "",
    }

    if not info.get("available"):
        return result

    compiler = info["compiler"]
    try:
        with tempfile.TemporaryDirectory(prefix="alfa_pdf_") as tmpdir:
            workdir = Path(tmpdir)
            tex_path = workdir / f"{job_name}.tex"
            tex_path.write_text(latex_text, encoding="utf-8")

            commands = [
                [
                    compiler,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    tex_path.name,
                ],
                [
                    compiler,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    tex_path.name,
                ],
            ]

            last_output = ""
            for command in commands:
                completed = subprocess.run(
                    command,
                    cwd=str(workdir),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                last_output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
                if completed.returncode != 0:
                    result["message"] = (
                        f"La compilacion con {compiler} no termino correctamente. "
                        "Se mantiene el exporte .tex como alternativa."
                    )
                    result["log_excerpt"] = last_output[-4000:]
                    return result

            pdf_path = workdir / f"{job_name}.pdf"
            if not pdf_path.exists():
                result["message"] = (
                    f"El compilador {compiler} termino sin producir {job_name}.pdf. "
                    "Se mantiene el exporte .tex como alternativa."
                )
                result["log_excerpt"] = last_output[-4000:]
                return result

            result["success"] = True
            result["pdf_bytes"] = pdf_path.read_bytes()
            result["message"] = f"PDF generado correctamente con {compiler}."
            result["log_excerpt"] = last_output[-4000:]
            return result
    except subprocess.TimeoutExpired:
        result["message"] = (
            f"La compilacion PDF excedio el tiempo limite usando {compiler}. "
            "Se mantiene el exporte .tex como alternativa."
        )
        return result
    except Exception as exc:
        result["message"] = (
            f"No fue posible compilar el PDF con {compiler}: {exc}. "
            "Se mantiene el exporte .tex como alternativa."
        )
        return result


def _normalize_pdf_text(value):
    if value is None:
        return ""
    text = normalize_spanish_text(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def _normalize_pdf_path(path):
    return str(path or "").replace("\\", "/").strip()


def _save_pdf_page(pdf, fig, page_number):
    fig.text(0.5, 0.03, f"Pagina {int(page_number)}", ha="center", va="bottom", fontsize=PDF_SMALL_FONT, color="#555555", family=PDF_FAMILY)
    pdf.savefig(fig, bbox_inches="tight")


def _iter_pdf_section_tree(section, level=1):
    if not isinstance(section, dict):
        return
    yield section, level
    for child in section.get("child_sections", []) or []:
        yield from _iter_pdf_section_tree(child, level=level + 1)


def _section_paragraphs_for_pdf(section):
    paragraphs = []
    purpose = _normalize_pdf_text(section.get("purpose", ""))
    if purpose:
        paragraphs.append(purpose)

    suggested = [item for item in (section.get("suggested_content", []) or []) if _normalize_pdf_text(item)]
    if suggested:
        paragraphs.append("Contenido sugerido: " + "; ".join(_normalize_pdf_text(item) for item in suggested) + ".")

    for paragraph in section.get("draft_paragraphs", []) or []:
        text = _normalize_pdf_text(paragraph)
        if text:
            paragraphs.append(text)

    for block in section.get("content_blocks", []) or []:
        title = _normalize_pdf_text(block.get("title", ""))
        items = [_normalize_pdf_text(item) for item in (block.get("items", []) or []) if _normalize_pdf_text(item)]
        if items:
            if title:
                paragraphs.append(f"{title}: " + "; ".join(items) + ".")
            else:
                paragraphs.append("; ".join(items) + ".")

    notes = [_normalize_pdf_text(item) for item in (section.get("notes", []) or []) if _normalize_pdf_text(item)]
    if notes:
        paragraphs.append("Notas: " + " ".join(notes))

    return paragraphs


def _sanitize_pdf_note(value):
    text = _normalize_pdf_text(value)
    lower = text.lower()
    if not text:
        return ""
    if any(fragment in lower for fragment in [
        "fallback",
        "matplotlib export",
        "exportado como png",
        "artefacto reconstruido",
        "usar el artefacto exportado",
        "no fue posible generar png",
        "html editable",
        "configuracion persistida",
    ]):
        return ""
    return text


def _normalize_pdf_headers(headers):
    normalized = []
    seen = {}
    for raw in headers or []:
        text = _normalize_pdf_text(raw)
        count = seen.get(text, 0)
        seen[text] = count + 1
        if count == 0:
            normalized.append(text)
        else:
            normalized.append("" if text else text)
    return normalized


def _wrap_and_justify_paragraph(text, width=96):
    words = [part for part in _normalize_pdf_text(text).split() if part]
    if not words:
        return []

    lines = []
    current = []
    current_len = 0
    for word in words:
        projected = current_len + len(word) + (1 if current else 0)
        if projected <= width or not current:
            current.append(word)
            current_len = projected
            continue
        lines.append(current)
        current = [word]
        current_len = len(word)
    if current:
        lines.append(current)

    justified = []
    for idx, line_words in enumerate(lines):
        if idx == len(lines) - 1 or len(line_words) <= 1:
            justified.append(" ".join(line_words))
            continue
        raw_len = sum(len(word) for word in line_words)
        spaces = max(1, width - raw_len)
        gaps = len(line_words) - 1
        base = spaces // gaps
        extra = spaces % gaps
        parts = []
        for gap_idx, word in enumerate(line_words[:-1]):
            parts.append(word)
            parts.append(" " * (base + (1 if gap_idx < extra else 0)))
        parts.append(line_words[-1])
        justified.append("".join(parts))
    return justified


def _wrap_paragraphs_for_pdf(paragraphs, width=96, max_lines=36):
    pages = []
    current_lines = []

    for paragraph in paragraphs:
        text = _normalize_pdf_text(paragraph)
        if not text:
            continue
        wrapped = _wrap_and_justify_paragraph(text, width=width) or [text]
        block = wrapped + [""]
        while block:
            available = max_lines - len(current_lines)
            if available <= 0:
                pages.append(current_lines)
                current_lines = []
                available = max_lines
            take = min(len(block), available)
            current_lines.extend(block[:take])
            block = block[take:]
            if block:
                pages.append(current_lines)
                current_lines = []

    if current_lines:
        pages.append(current_lines)
    return pages or [[]]


def _figure_lookup_for_pdf(figure_files):
    lookup = {}
    for path, content in (figure_files or {}).items():
        normalized = _normalize_pdf_path(path)
        lookup[normalized] = content
        lookup[Path(normalized).name.lower()] = content
    return lookup


def _figure_key_for_pdf(figure_ref):
    return (
        _normalize_pdf_text(figure_ref.get("id", "")),
        _normalize_pdf_text(figure_ref.get("label", "")),
        _normalize_pdf_path(figure_ref.get("path", "")),
        _normalize_pdf_text(figure_ref.get("title", "")),
    )


def _table_key_for_pdf(table_payload):
    headers = tuple(_normalize_pdf_text(h) for h in (table_payload.get("headers", []) or []))
    rows = table_payload.get("rows", []) or []
    preview = tuple(tuple(_normalize_pdf_text(cell) for cell in row[: min(len(row), 5)]) for row in rows[:3])
    return (
        _normalize_pdf_text(table_payload.get("title", "")),
        headers,
        len(rows),
        preview,
    )


def _table_row_chunk_size(headers, rows):
    num_cols = len(headers or [])
    if num_cols >= 9:
        return 10
    if num_cols >= 7:
        return 12
    if num_cols >= 5:
        return 15
    if len(rows or []) >= 30:
        return 18
    return 22


def _render_pdf_title_page(pdf, payload, page_number):
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=PDF_PAGE_SIZE, dpi=150)
    fig.patch.set_facecolor("white")
    title = _normalize_pdf_text(payload.get("title", "Informe tecnico"))
    subtitle = _normalize_pdf_text(payload.get("subtitle", "Borrador inicial"))
    project_name = _normalize_pdf_text(payload.get("project_name", ""))
    report_style = _normalize_pdf_text(payload.get("report_style", "general"))
    fig.text(0.08, 0.93, "ALFA APP", ha="left", va="center", fontsize=11, fontweight="bold", color=PDF_COLOR_PRIMARY, family=PDF_FAMILY)
    fig.text(0.5, 0.78, title, ha="center", va="center", fontsize=22, fontweight="bold", family=PDF_FAMILY)
    if subtitle:
        fig.text(0.5, 0.73, subtitle, ha="center", va="center", fontsize=13, color="#444444", family=PDF_FAMILY)
    if project_name:
        fig.text(0.5, 0.62, f"Proyecto: {project_name}", ha="center", va="center", fontsize=12, family=PDF_FAMILY)
    fig.text(0.5, 0.57, f"Estilo de reporte: {report_style}", ha="center", va="center", fontsize=11, family=PDF_FAMILY)
    box = plt.Rectangle((0.12, 0.18), 0.76, 0.18, facecolor=PDF_COLOR_PANEL, edgecolor=PDF_COLOR_BORDER, linewidth=1.0, transform=fig.transFigure)
    fig.patches.append(box)
    fig.text(0.15, 0.31, "Documento final exportado directamente a PDF", fontsize=12, fontweight="bold", va="center", family=PDF_FAMILY)
    fig.text(0.15, 0.27, "Incluye cuerpo principal, figuras, tablas y anexos por fase.", fontsize=10.5, va="center", family=PDF_FAMILY)
    fig.text(0.15, 0.23, "La version LaTeX permanece disponible como ruta editable secundaria.", fontsize=10.0, va="center", color="#444444", family=PDF_FAMILY)
    fig.text(0.5, 0.10, "Generado desde la estructura de reporte del proyecto", ha="center", va="center", fontsize=10, color="#555555", family=PDF_FAMILY)
    plt.axis("off")
    _save_pdf_page(pdf, fig, page_number)
    plt.close(fig)


def _render_pdf_metadata_page(pdf, payload, page_number):
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=PDF_PAGE_SIZE, dpi=150)
    fig.patch.set_facecolor("white")
    fig.text(0.08, 0.95, "Datos generales del reporte", fontsize=16, fontweight="bold", va="top", family=PDF_FAMILY, color=PDF_COLOR_PRIMARY)
    metadata_rows = [
        ("Proyecto", _normalize_pdf_text(payload.get("project_name", "Sin nombre"))),
        ("Estilo", _normalize_pdf_text(payload.get("report_style", "general"))),
        ("Subtitulo", _normalize_pdf_text(payload.get("subtitle", "Borrador inicial"))),
        ("Secciones principales", str(len(payload.get("sections", []) or []))),
        ("Anexos por fase", str(len(payload.get("appendix_sections", []) or []))),
    ]
    y = 0.87
    for label, value in metadata_rows:
        fig.text(0.10, y, f"{label}:", fontsize=11, fontweight="bold", va="top", family=PDF_FAMILY)
        fig.text(0.30, y, value or "Sin dato", fontsize=11, va="top", family=PDF_FAMILY)
        y -= 0.06
    fig.text(0.08, 0.48, "Alcance del documento", fontsize=13, fontweight="bold", va="top", family=PDF_FAMILY, color=PDF_COLOR_PRIMARY)
    fig.text(
        0.08,
        0.43,
        "Este PDF reutiliza la estructura actual del reporte, incluyendo secciones tecnicas, figuras, tablas y anexos organizados por fase.",
        fontsize=10.5,
        va="top",
        family=PDF_FAMILY,
        wrap=True,
    )
    plt.axis("off")
    _save_pdf_page(pdf, fig, page_number)
    plt.close(fig)


def _render_pdf_toc_page(pdf, payload, page_number):
    import matplotlib.pyplot as plt

    sections = payload.get("sections", []) or []
    appendices = payload.get("appendix_sections", []) or []
    lines = ["Contenido", ""]
    for idx, section in enumerate(sections, start=1):
        lines.append(f"{idx}. {section.get('title', 'Seccion')}")
    if appendices:
        lines.extend(["", "Anexos"])
        for appendix in appendices:
            lines.append(f"- {appendix.get('title', 'Anexo')}")
            for child in appendix.get("child_sections", []) or []:
                lines.append(f"    - {child.get('title', 'Detalle')}")
                for grandchild in child.get("child_sections", []) or []:
                    lines.append(f"        - {grandchild.get('title', 'Subdetalle')}")

    fig = plt.figure(figsize=PDF_PAGE_SIZE, dpi=150)
    fig.patch.set_facecolor("white")
    fig.text(0.08, 0.95, "Indice del documento", fontsize=16, fontweight="bold", va="top", family=PDF_FAMILY, color=PDF_COLOR_PRIMARY)
    fig.text(0.08, 0.91, "\n".join(lines[1:]), fontsize=10.2, va="top", family="DejaVu Sans Mono", color=PDF_COLOR_SECONDARY)
    plt.axis("off")
    _save_pdf_page(pdf, fig, page_number)
    plt.close(fig)


def _render_pdf_divider_page(pdf, title, subtitle, page_number, appendix=False):
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=PDF_PAGE_SIZE, dpi=150)
    fig.patch.set_facecolor("white")
    band_color = "#eaf1f8" if appendix else PDF_COLOR_PANEL
    box = plt.Rectangle((0.08, 0.28), 0.84, 0.30, facecolor=band_color, edgecolor=PDF_COLOR_BORDER, linewidth=1.2, transform=fig.transFigure)
    fig.patches.append(box)
    fig.text(0.10, 0.52, title, fontsize=20 if appendix else 18, fontweight="bold", va="center", family=PDF_FAMILY, color=PDF_COLOR_PRIMARY)
    if subtitle:
        fig.text(0.10, 0.45, subtitle, fontsize=11.5, va="center", color="#444444", family=PDF_FAMILY)
    plt.axis("off")
    _save_pdf_page(pdf, fig, page_number)
    plt.close(fig)


def _render_pdf_text_pages(pdf, title, paragraphs, page_number_start, level=1):
    import matplotlib.pyplot as plt

    width = max(68, 100 - (level - 1) * 6)
    max_lines = max(24, 38 - (level - 1) * 3)
    pages = _wrap_paragraphs_for_pdf(paragraphs, width=width, max_lines=max_lines)
    heading_size = {1: 16, 2: 13, 3: 11}.get(level, 11)

    for page_idx, page_lines in enumerate(pages, start=1):
        fig = plt.figure(figsize=PDF_PAGE_SIZE, dpi=150)
        fig.patch.set_facecolor("white")
        heading = title if page_idx == 1 else f"{title} (cont.)"
        fig.text(0.08, 0.95, heading, fontsize=heading_size, fontweight="bold", va="top", family=PDF_FAMILY, color=PDF_COLOR_PRIMARY)
        fig.text(0.08, 0.90, "\n".join(page_lines), fontsize=PDF_BODY_FONT, va="top", family=PDF_FAMILY, color="#222222")
        plt.axis("off")
        _save_pdf_page(pdf, fig, page_number_start + page_idx - 1)
        plt.close(fig)
    return len(pages)


def _render_pdf_table_pages(pdf, section_title, table_payload, page_number_start, level=1):
    import matplotlib.pyplot as plt

    headers = list(table_payload.get("headers", []) or [])
    rows = list(table_payload.get("rows", []) or [])
    if not headers or not rows:
        return 0

    chunk_size = _table_row_chunk_size(headers, rows)
    font_size = 8.0 if len(headers) >= 8 else 8.6 if len(headers) >= 6 else 9.0
    pages_rendered = 0

    for chunk_start in range(0, len(rows), chunk_size):
        chunk = rows[chunk_start:chunk_start + chunk_size]
        fig, ax = plt.subplots(figsize=PDF_PAGE_SIZE, dpi=150)
        fig.patch.set_facecolor("white")
        ax.axis("off")
        title = _normalize_pdf_text(table_payload.get("title", "Tabla"))
        note = _sanitize_pdf_note(table_payload.get("note", ""))
        heading = title if chunk_start == 0 else f"{title} (cont.)"
        fig.text(0.08, 0.965, section_title, fontsize=12 if level == 1 else 10.5, fontweight="bold", va="top", family=PDF_FAMILY, color=PDF_COLOR_PRIMARY)
        fig.text(0.08, 0.935, heading, fontsize=11, va="top", family=PDF_FAMILY)
        table = ax.table(
            cellText=chunk,
            colLabels=_normalize_pdf_headers(headers),
            loc="center",
            cellLoc="left",
            colLoc="left",
            bbox=[0.04, 0.16, 0.92, 0.72],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(font_size)
        table.scale(1, 1.18 if len(headers) <= 6 else 1.08)
        try:
            table.auto_set_column_width(col=list(range(len(headers))))
        except Exception:
            pass
        if note:
            fig.text(0.08, 0.09, note, fontsize=PDF_CAPTION_FONT, va="bottom", style="italic", family=PDF_FAMILY, color=PDF_COLOR_SECONDARY)
        _save_pdf_page(pdf, fig, page_number_start + pages_rendered)
        plt.close(fig)
        pages_rendered += 1
    return pages_rendered


def _open_pdf_figure_image(content, max_dimension=1800):
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        image = Image.open(io.BytesIO(content))
        image = image.convert("RGB")
        image.thumbnail((max_dimension, max_dimension))
        return image
    except Exception:
        return None


def _figure_box_for_pdf(title):
    lower = _normalize_pdf_text(title).lower()
    if "layout" in lower or "vista en planta" in lower or "parque" in lower:
        return [0.06, 0.18, 0.88, 0.68], 2400
    return [0.10, 0.22, 0.80, 0.58], 1800


def _render_pdf_figure_page(pdf, section_title, figure_ref, figure_lookup, page_number, level=1):
    import matplotlib.pyplot as plt

    title = _normalize_pdf_text(figure_ref.get("title", "Figura"))
    caption = _normalize_pdf_text(figure_ref.get("caption", title))
    note = _sanitize_pdf_note(figure_ref.get("note", ""))
    path = _normalize_pdf_path(figure_ref.get("path", ""))
    content = figure_lookup.get(path) or figure_lookup.get(Path(path).name.lower())
    figure_box, max_dimension = _figure_box_for_pdf(title)

    fig = plt.figure(figsize=PDF_PAGE_SIZE, dpi=150)
    fig.patch.set_facecolor("white")
    fig.text(0.08, 0.965, section_title, fontsize=12 if level == 1 else 10.5, fontweight="bold", va="top", family=PDF_FAMILY, color=PDF_COLOR_PRIMARY)
    fig.text(0.08, 0.935, title, fontsize=11.5, fontweight="bold", va="top", family=PDF_FAMILY)
    if caption and caption != title:
        fig.text(0.08, 0.905, caption, fontsize=PDF_CAPTION_FONT, va="top", family=PDF_FAMILY, color=PDF_COLOR_SECONDARY)

    if content:
        image = _open_pdf_figure_image(content, max_dimension=max_dimension)
    else:
        image = None

    if image is not None:
        ax = fig.add_axes(figure_box)
        ax.imshow(image)
        ax.axis("off")
        border = plt.Rectangle((figure_box[0], figure_box[1]), figure_box[2], figure_box[3], fill=False, edgecolor=PDF_COLOR_BORDER, linewidth=0.8, transform=fig.transFigure)
        fig.patches.append(border)
    else:
        fig.text(
            0.08,
            0.55,
            f"No fue posible insertar automaticamente la figura: {title}.",
            fontsize=11,
            va="center",
            family=PDF_FAMILY,
        )
        if path:
            fig.text(0.08, 0.50, f"Referencia de artefacto: {path}", fontsize=9.5, va="center", family=PDF_FAMILY)

    if note:
        fig.text(0.08, 0.09, note, fontsize=PDF_CAPTION_FONT, va="bottom", style="italic", family=PDF_FAMILY, color=PDF_COLOR_SECONDARY)

    plt.axis("off")
    _save_pdf_page(pdf, fig, page_number)
    plt.close(fig)
    return 1


def build_direct_pdf_report(report_payload, figure_files=None, file_name="reporte_final.pdf"):
    result = {
        "success": False,
        "pdf_bytes": None,
        "file_name": file_name,
        "message": "",
        "page_count": 0,
    }

    try:
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except Exception as exc:
        result["message"] = f"No fue posible inicializar el render PDF directo: {exc}."
        return result

    plt.rcParams.update({
        "font.family": PDF_FAMILY,
        "font.size": PDF_BODY_FONT,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
    })

    payload = report_payload or {}
    figure_lookup = _figure_lookup_for_pdf(figure_files or {})
    output = io.BytesIO()
    page_count = 0
    seen_figures = set()
    seen_tables = set()

    try:
        with PdfPages(output) as pdf:
            _render_pdf_title_page(pdf, payload, page_count + 1)
            page_count += 1
            _render_pdf_metadata_page(pdf, payload, page_count + 1)
            page_count += 1
            _render_pdf_toc_page(pdf, payload, page_count + 1)
            page_count += 1

            for section in payload.get("sections", []) or []:
                _render_pdf_divider_page(
                    pdf,
                    _normalize_pdf_text(section.get("title", "Seccion")),
                    _normalize_pdf_text(section.get("purpose", "")),
                    page_count + 1,
                    appendix=False,
                )
                page_count += 1
                for nested_section, level in _iter_pdf_section_tree(section, level=1):
                    paragraphs = _section_paragraphs_for_pdf(nested_section)
                    title = _normalize_pdf_text(nested_section.get("title", "Seccion"))
                    if paragraphs:
                        page_count += _render_pdf_text_pages(pdf, title, paragraphs, page_count + 1, level=level)
                    for table_payload in nested_section.get("latex_tables", []) or []:
                        table_key = _table_key_for_pdf(table_payload)
                        if table_key in seen_tables:
                            continue
                        seen_tables.add(table_key)
                        page_count += _render_pdf_table_pages(pdf, title, table_payload, page_count + 1, level=level)
                    for figure_ref in nested_section.get("figure_refs", []) or []:
                        figure_key = _figure_key_for_pdf(figure_ref)
                        if figure_key in seen_figures:
                            continue
                        seen_figures.add(figure_key)
                        page_count += _render_pdf_figure_page(pdf, title, figure_ref, figure_lookup, page_count + 1, level=level)

            for appendix in payload.get("appendix_sections", []) or []:
                _render_pdf_divider_page(
                    pdf,
                    _normalize_pdf_text(appendix.get("title", "Anexo")),
                    _normalize_pdf_text(appendix.get("purpose", "")),
                    page_count + 1,
                    appendix=True,
                )
                page_count += 1
                for nested_section, level in _iter_pdf_section_tree(appendix, level=1):
                    title = _normalize_pdf_text(nested_section.get("title", "Anexo"))
                    paragraphs = _section_paragraphs_for_pdf(nested_section)
                    if paragraphs:
                        page_count += _render_pdf_text_pages(pdf, title, paragraphs, page_count + 1, level=level)
                    for table_payload in nested_section.get("latex_tables", []) or []:
                        table_key = _table_key_for_pdf(table_payload)
                        if table_key in seen_tables:
                            continue
                        seen_tables.add(table_key)
                        page_count += _render_pdf_table_pages(pdf, title, table_payload, page_count + 1, level=level)
                    for figure_ref in nested_section.get("figure_refs", []) or []:
                        figure_key = _figure_key_for_pdf(figure_ref)
                        if figure_key in seen_figures:
                            continue
                        seen_figures.add(figure_key)
                        page_count += _render_pdf_figure_page(pdf, title, figure_ref, figure_lookup, page_count + 1, level=level)

            metadata = pdf.infodict()
            metadata["Title"] = _normalize_pdf_text(payload.get("title", "Informe"))
            metadata["Subject"] = "Reporte tecnico exportado directamente a PDF desde Alfa app"
            metadata["Author"] = "Alfa app"
            metadata["Keywords"] = "energia eolica, reporte, pdf"

        plt.close("all")
        result["success"] = True
        result["pdf_bytes"] = output.getvalue()
        result["page_count"] = page_count
        result["message"] = f"PDF directo generado correctamente con {page_count} paginas."
        return result
    except Exception as exc:
        result["message"] = f"No fue posible construir el PDF directo: {exc}."
        return result


TECH_PDF_PAGE_SIZE = (8.27, 11.69)
TECH_PDF_FAMILY = "DejaVu Serif"
TECH_PDF_BODY = 10.5
TECH_PDF_SMALL = 8.6
TECH_PDF_TITLE = 20
TECH_PDF_H1 = 15
TECH_PDF_H2 = 12
TECH_PDF_ACCENT = "#18324a"
TECH_PDF_PANEL = "#f4f6f8"


def _tech_pdf_page(pdf, fig, page_number):
    fig.text(0.5, 0.025, f"Página {page_number}", ha="center", va="bottom", fontsize=TECH_PDF_SMALL, family=TECH_PDF_FAMILY, color="#555555")
    pdf.savefig(fig, bbox_inches="tight")


def _tech_pdf_wrap(text, width=94):
    words = [w for w in _normalize_pdf_text(text).split() if w]
    if not words:
        return [""]
    lines = []
    current = []
    current_len = 0
    for word in words:
        projected = current_len + len(word) + (1 if current else 0)
        if projected <= width or not current:
            current.append(word)
            current_len = projected
        else:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
    if current:
        lines.append(" ".join(current))
    return lines


def _tech_render_cover(pdf, report_model, page_number):
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=TECH_PDF_PAGE_SIZE, dpi=150)
    fig.patch.set_facecolor("white")
    fig.text(0.08, 0.93, "INFORME TÉCNICO", fontsize=10.5, fontweight="bold", color=TECH_PDF_ACCENT, family=TECH_PDF_FAMILY)
    fig.text(0.5, 0.74, _normalize_pdf_text(report_model.get("title", "Informe técnico")), ha="center", fontsize=TECH_PDF_TITLE, fontweight="bold", family=TECH_PDF_FAMILY)
    fig.text(0.5, 0.67, _normalize_pdf_text(report_model.get("project_name", "")), ha="center", fontsize=12, family=TECH_PDF_FAMILY)
    panel = plt.Rectangle((0.12, 0.18), 0.76, 0.18, facecolor=TECH_PDF_PANEL, edgecolor="#d4dbe3", linewidth=1.0, transform=fig.transFigure)
    fig.patches.append(panel)
    fig.text(0.15, 0.30, "Configuración técnica inicial del proyecto eólico", fontsize=12, fontweight="bold", family=TECH_PDF_FAMILY)
    fig.text(0.15, 0.25, "Documento base generado desde la información real disponible en Fase 1.", fontsize=TECH_PDF_BODY, family=TECH_PDF_FAMILY)
    plt.axis("off")
    _tech_pdf_page(pdf, fig, page_number)
    plt.close(fig)


def _tech_render_intro(pdf, report_model, page_number):
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=TECH_PDF_PAGE_SIZE, dpi=150)
    fig.patch.set_facecolor("white")
    fig.text(0.08, 0.95, "Introducción", fontsize=TECH_PDF_H1, fontweight="bold", family=TECH_PDF_FAMILY, color=TECH_PDF_ACCENT, va="top")
    intro_lines = []
    for paragraph in report_model.get("intro_paragraphs", []) or []:
        intro_lines.extend(_tech_pdf_wrap(paragraph, width=92))
        intro_lines.append("")
    fig.text(0.08, 0.89, "\n".join(intro_lines), fontsize=TECH_PDF_BODY, family=TECH_PDF_FAMILY, va="top")
    plt.axis("off")
    _tech_pdf_page(pdf, fig, page_number)
    plt.close(fig)


def _tech_render_toc(pdf, report_model, page_number):
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=TECH_PDF_PAGE_SIZE, dpi=150)
    fig.patch.set_facecolor("white")
    fig.text(0.08, 0.95, "Contenido", fontsize=TECH_PDF_H1, fontweight="bold", family=TECH_PDF_FAMILY, color=TECH_PDF_ACCENT, va="top")
    lines = []
    for idx, section in enumerate(report_model.get("sections", []) or [], start=1):
        lines.append(f"{idx}. {section.get('title', 'Sección')}")
        for sub_idx, subsection in enumerate(section.get("subsections", []) or [], start=1):
            lines.append(f"    {idx}.{sub_idx} {subsection.get('title', 'Subsección')}")
    fig.text(0.08, 0.89, "\n".join(lines), fontsize=TECH_PDF_BODY, family="DejaVu Sans Mono", va="top")
    plt.axis("off")
    _tech_pdf_page(pdf, fig, page_number)
    plt.close(fig)


def _tech_render_section_page(pdf, section, page_number):
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=TECH_PDF_PAGE_SIZE, dpi=150)
    fig.patch.set_facecolor("white")
    band = plt.Rectangle((0.08, 0.30), 0.84, 0.24, facecolor=TECH_PDF_PANEL, edgecolor="#d4dbe3", linewidth=1.0, transform=fig.transFigure)
    fig.patches.append(band)
    fig.text(0.10, 0.47, _normalize_pdf_text(section.get("title", "Sección")), fontsize=TECH_PDF_TITLE - 2, fontweight="bold", family=TECH_PDF_FAMILY, color=TECH_PDF_ACCENT)
    fig.text(0.10, 0.40, _normalize_pdf_text(section.get("description", "")), fontsize=TECH_PDF_BODY, family=TECH_PDF_FAMILY, color="#444444")
    plt.axis("off")
    _tech_pdf_page(pdf, fig, page_number)
    plt.close(fig)


def _tech_table_chunks(rows, max_rows=18):
    for start in range(0, len(rows), max_rows):
        yield rows[start:start + max_rows]


def _tech_render_table(pdf, section_title, subsection_title, block, page_number_start):
    import matplotlib.pyplot as plt

    headers = list(block.get("headers", []) or [])
    rows = list(block.get("rows", []) or [])
    if not headers or not rows:
        return 0
    rendered = 0
    max_rows = 16 if len(headers) >= 4 else 20
    for chunk in _tech_table_chunks(rows, max_rows=max_rows):
        fig, ax = plt.subplots(figsize=TECH_PDF_PAGE_SIZE, dpi=150)
        fig.patch.set_facecolor("white")
        ax.axis("off")
        fig.text(0.08, 0.96, section_title, fontsize=TECH_PDF_H2, fontweight="bold", family=TECH_PDF_FAMILY, color=TECH_PDF_ACCENT, va="top")
        fig.text(0.08, 0.925, subsection_title, fontsize=11.5, fontweight="bold", family=TECH_PDF_FAMILY, va="top")
        fig.text(0.08, 0.895, _normalize_pdf_text(block.get("title", "Tabla")), fontsize=10.5, family=TECH_PDF_FAMILY, va="top")
        description = _normalize_pdf_text(block.get("description", ""))
        if description:
            fig.text(0.08, 0.865, description, fontsize=TECH_PDF_SMALL, family=TECH_PDF_FAMILY, color="#555555", va="top")
        table = ax.table(
            cellText=chunk,
            colLabels=headers,
            cellLoc="left",
            colLoc="left",
            bbox=[0.05, 0.16, 0.90, 0.64],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8.6 if len(headers) <= 4 else 8.0)
        table.scale(1, 1.12)
        try:
            table.auto_set_column_width(col=list(range(len(headers))))
        except Exception:
            pass
        _tech_pdf_page(pdf, fig, page_number_start + rendered)
        plt.close(fig)
        rendered += 1
    return rendered


def _tech_render_figure(pdf, section_title, subsection_title, block, page_number):
    import matplotlib.pyplot as plt
    try:
        from PIL import Image
    except Exception:
        Image = None

    fig = plt.figure(figsize=TECH_PDF_PAGE_SIZE, dpi=150)
    fig.patch.set_facecolor("white")
    fig.text(0.08, 0.96, section_title, fontsize=TECH_PDF_H2, fontweight="bold", family=TECH_PDF_FAMILY, color=TECH_PDF_ACCENT, va="top")
    fig.text(0.08, 0.925, subsection_title, fontsize=11.5, fontweight="bold", family=TECH_PDF_FAMILY, va="top")
    fig.text(0.08, 0.895, _normalize_pdf_text(block.get("title", "Figura")), fontsize=10.5, family=TECH_PDF_FAMILY, va="top")
    description = _normalize_pdf_text(block.get("description", ""))
    if description:
        fig.text(0.08, 0.865, description, fontsize=TECH_PDF_SMALL, family=TECH_PDF_FAMILY, color="#555555", va="top")

    image_bytes = block.get("image_bytes")
    image = None
    if Image is not None and image_bytes:
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            title = _normalize_pdf_text(block.get("title", "")).lower()
            max_dim = 2600 if "potencia" in title or "cp" in title else 1800
            image.thumbnail((max_dim, max_dim))
        except Exception:
            image = None

    if image is not None:
        ax = fig.add_axes([0.08, 0.17, 0.84, 0.62])
        ax.imshow(image)
        ax.axis("off")
        border = plt.Rectangle((0.08, 0.17), 0.84, 0.62, fill=False, edgecolor="#d4dbe3", linewidth=0.8, transform=fig.transFigure)
        fig.patches.append(border)
    else:
        fig.text(0.08, 0.52, "No fue posible insertar automáticamente la figura en este reporte.", fontsize=TECH_PDF_BODY, family=TECH_PDF_FAMILY, va="center")
    _tech_pdf_page(pdf, fig, page_number)
    plt.close(fig)
    return 1


def build_informe_tecnico_pdf(report_model, file_name="informe_tecnico.pdf"):
    result = {
        "success": False,
        "pdf_bytes": None,
        "file_name": file_name,
        "message": "",
        "page_count": 0,
    }
    try:
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except Exception as exc:
        result["message"] = f"No fue posible inicializar el PDF del informe técnico: {exc}."
        return result

    plt.rcParams.update({
        "font.family": TECH_PDF_FAMILY,
        "font.size": TECH_PDF_BODY,
    })
    page_count = 0
    output = io.BytesIO()
    try:
        with PdfPages(output) as pdf:
            _tech_render_cover(pdf, report_model, page_count + 1)
            page_count += 1
            _tech_render_intro(pdf, report_model, page_count + 1)
            page_count += 1
            _tech_render_toc(pdf, report_model, page_count + 1)
            page_count += 1

            for section in report_model.get("sections", []) or []:
                _tech_render_section_page(pdf, section, page_count + 1)
                page_count += 1
                section_title = _normalize_pdf_text(section.get("title", "Sección"))
                for subsection in section.get("subsections", []) or []:
                    subsection_title = _normalize_pdf_text(subsection.get("title", "Subsección"))
                    for block in subsection.get("blocks", []) or []:
                        block_type = block.get("type")
                        if block_type == "table":
                            page_count += _tech_render_table(pdf, section_title, subsection_title, block, page_count + 1)
                        elif block_type == "figure":
                            page_count += _tech_render_figure(pdf, section_title, subsection_title, block, page_count + 1)

            metadata = pdf.infodict()
            metadata["Title"] = _normalize_pdf_text(report_model.get("title", "Informe técnico"))
            metadata["Author"] = "Alfa app"
            metadata["Subject"] = "Informe técnico"
        plt.close("all")
        result["success"] = True
        result["pdf_bytes"] = output.getvalue()
        result["page_count"] = page_count
        result["message"] = f"PDF del informe técnico generado correctamente con {page_count} páginas."
        return result
    except Exception as exc:
        result["message"] = f"No fue posible generar el PDF del informe técnico: {exc}."
        return result
