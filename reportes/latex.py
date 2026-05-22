import re

from .texto import normalize_spanish_text as _normalize_spanish_text


def _escape_latex_text(value):
    text = _normalize_spanish_text(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _sanitize_latex_label(value, prefix="fig"):
    text = str(value or "").strip().lower()
    text = text.replace("\\", "-").replace("{", "-").replace("}", "-")
    text = re.sub(r"[^a-z0-9:._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-:.")
    if not text:
        text = str(prefix or "lbl")
    if ":" not in text:
        text = f"{prefix}:{text}"
    return text


def _sanitize_latex_graphics_path(path):
    normalized = str(path or "").replace("\\", "/").strip()
    normalized = normalized.replace("{", "").replace("}", "")
    return normalized


def _sanitize_report_note(value):
    text = " ".join(_normalize_spanish_text(value).replace("\r", "\n").split())
    lower = text.lower()
    if not text:
        return ""
    if "kaleido" in lower or "pip install" in lower or "traceback" in lower:
        return "La exportaci\u00f3n autom\u00e1tica de esta figura dependi\u00f3 del entorno local; si hace falta, reempl\u00e1cela manualmente."
    if "no fue posible generar png estatico" in lower:
        return "No se obtuvo una imagen est\u00e1tica en este paso; se mantiene una referencia editable."
    if any(fragment in lower for fragment in [
        "figura de ubicaci",
        "mapa del sitio exportado como png",
        "usar el artefacto exportado si est",
        "figura exportada como png est",
        "artefacto reconstruido desde la configuraci",
        "complementa la discusi",
        "representa el arreglo actual del parque",
        "figura recomendada para reforzar la interpretaci",
        "insertar si la discusi",
    ]):
        return ""
    if len(text) > 280:
        text = text[:277].rstrip() + "..."
    return text


def _compact_header_cell(value):
    return str(value or "").strip()


def _table_column_spec(num_columns, use_longtable=False):
    if use_longtable:
        width = 0.94 if num_columns <= 1 else max(0.12, 0.94 / float(num_columns))
        column = r">{\raggedright\arraybackslash}p{" + f"{width:.2f}" + r"\textwidth}"
        return r"@{}" + "".join(column for _ in range(max(1, num_columns))) + r"@{}"
    if num_columns <= 1:
        return r"@{}>{\raggedright\arraybackslash}X@{}"
    if num_columns == 2:
        return r"@{}>{\raggedright\arraybackslash}p{0.30\textwidth}>{\raggedright\arraybackslash}X@{}"
    if num_columns == 3:
        return r"@{}>{\raggedright\arraybackslash}p{0.23\textwidth}>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}X@{}"
    if num_columns == 4:
        return r"@{}>{\raggedright\arraybackslash}p{0.18\textwidth}>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}X@{}"
    width = max(0.12, 0.94 / float(num_columns))
    column = r">{\raggedright\arraybackslash}p{" + f"{width:.2f}" + r"\textwidth}"
    return r"@{}" + "".join(column for _ in range(num_columns)) + r"@{}"


def _build_latex_table(lines, table):
    headers = table.get("headers", []) or []
    rows = table.get("rows", []) or []
    if not headers or not rows:
        return

    title = _escape_latex_text(table.get("title", "Tabla"))
    use_longtable = len(headers) >= 5 or len(rows) >= 16
    cols = _table_column_spec(len(headers), use_longtable=use_longtable)
    env_name = "longtable" if use_longtable else "tabularx"
    compact_table = len(headers) >= 6 or len(rows) >= 20
    font_size = r"\scriptsize" if compact_table else r"\footnotesize"
    tabcolsep = "3.5pt" if compact_table else "5pt"
    arraystretch = "1.08" if compact_table else "1.15"

    lines.extend([
        r"\subsection*{" + title + r"}",
        r"\begingroup",
        font_size,
        r"\setlength{\tabcolsep}{" + tabcolsep + r"}",
        r"\renewcommand{\arraystretch}{" + arraystretch + r"}",
    ])
    if use_longtable:
        lines.append(r"\begin{longtable}{" + cols + r"}")
    else:
        lines.append(r"\begin{tabularx}{\textwidth}{" + cols + r"}")
    lines.append(r"\toprule")
    lines.append(
        " & ".join(r"\textbf{" + _escape_latex_text(_compact_header_cell(h)) + r"}" for h in headers) + r" \\"
    )
    lines.append(r"\midrule")
    for row in rows:
        lines.append(" & ".join(_escape_latex_text(cell) for cell in row) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{" + env_name + r"}")
    lines.append(r"\endgroup")
    note = table.get("note", "")
    if note:
        lines.extend(["", r"\par\medskip", r"\noindent\small\textit{" + _escape_latex_text(note) + r"}", ""])
    lines.append("")


def _render_latex_table(table):
    lines = []
    _build_latex_table(lines, table)
    return "\n".join(lines).strip() + "\n"


def _default_table_file_name(section_id, table_title, index):
    title = str(table_title or "").lower()
    if "operacion" in title:
        return "table_operating_zones.tex"
    if "interval" in title or "probabilidad" in title:
        return "table_probability_intervals.tex"
    if "perdida" in title:
        return "table_loss_detail.tex"
    if "sector" in title:
        return "table_sector_aep.tex"
    if "cheque" in title or "trazabilidad" in title:
        return "table_assignment_checks.tex"
    if "sensibilidad" in title:
        return "table_sensitivity_summary.tex"
    section_id = str(section_id or "appendix").strip() or "appendix"
    return f"table_{section_id}_{index + 1}.tex"


def _contextual_figure_label(base_label, context_suffix="", index=0):
    suffix = str(context_suffix or "sec").strip().lower()
    suffix = re.sub(r"[^a-z0-9._:-]+", "-", suffix)
    return _sanitize_latex_label(f"{base_label}-{suffix}-{index + 1}")


def _append_figure_refs(lines, figure_refs, context_suffix="section"):
    figure_refs = figure_refs or []
    if not figure_refs:
        return

    lines.extend([r"\subsection*{Figuras sugeridas}", r"\begin{itemize}"])
    for idx, figure in enumerate(figure_refs):
        title = str(figure.get("title", "Figura") or "Figura")
        note = _sanitize_report_note(figure.get("note", ""))
        item = f"Figura sugerida: {title.lower()}."
        if note:
            item += f". {note}"
        lines.append(r"\item " + _escape_latex_text(item))
    lines.extend([r"\end{itemize}", ""])


def _append_figure_blocks(lines, figure_refs, include_static_figures=False, context_suffix="section"):
    figure_refs = figure_refs or []
    if not figure_refs:
        return

    for idx, figure in enumerate(figure_refs):
        title = _escape_latex_text(figure.get("title", "Figura"))
        label = _contextual_figure_label(figure.get("label", "fig:placeholder"), context_suffix=context_suffix, index=idx)
        caption = _escape_latex_text(figure.get("caption", figure.get("title", "Figura")))
        note = _escape_latex_text(_sanitize_report_note(figure.get("note", "")))
        path = _sanitize_latex_graphics_path(figure.get("path", ""))
        render_mode = figure.get("render_mode", "placeholder")

        if include_static_figures and render_mode == "includegraphics" and path:
            lines.extend([
                r"\begin{figure}[!htbp]",
                r"\centering",
                r"\includegraphics[width=\linewidth,height=0.72\textheight,keepaspectratio]{" + r"\detokenize{" + path + r"}" + r"}",
                r"\caption{" + caption + r"}",
                r"\label{" + label + r"}",
                r"\end{figure}",
                "",
            ])
            if note:
                lines.extend([r"\noindent\textit{" + note + r"}", ""])
            continue

        if render_mode in ["includegraphics", "static_reference"] and path:
            continue

        if render_mode == "html_reference" and path:
            lines.extend([
                r"\begin{quote}",
                _escape_latex_text(f"Figura sugerida: {figure.get('title', 'Figura')}."),
                r"\end{quote}",
                "",
            ])
            continue

        lines.extend([
            r"\begin{quote}",
            _escape_latex_text(f"Figura sugerida: {figure.get('title', 'Figura')}."),
            r"\end{quote}",
            "",
        ])


def _heading_command_for_level(level):
    try:
        level = int(level)
    except Exception:
        level = 1
    if level <= 1:
        return r"\section"
    if level == 2:
        return r"\subsection"
    return r"\subsubsection"


def _iter_section_tree(section):
    if not isinstance(section, dict):
        return
    yield section
    for child in section.get("child_sections", []) or []:
        yield from _iter_section_tree(child)


def _append_latex_section(lines, section, externalize_tables=False, tables_dir="tables", include_static_figures=False, heading_level=1):
    section_title = _escape_latex_text(section.get("title", "Seccion"))
    purpose = _escape_latex_text(section.get("purpose", ""))
    suggested_content = section.get("suggested_content", []) or []
    draft_paragraphs = section.get("draft_paragraphs", []) or []
    content_blocks = section.get("content_blocks", []) or []
    latex_tables = section.get("latex_tables", []) or []
    figure_refs = section.get("figure_refs", []) or []
    child_sections = section.get("child_sections", []) or []
    context_suffix = str(section.get("id") or section.get("title") or "section")
    heading_command = _heading_command_for_level(heading_level)

    lines.extend([heading_command + "{" + section_title + r"}", ""])
    if purpose:
        lines.extend([purpose, ""])
    if suggested_content:
        lines.extend([r"\subsection*{Contenido sugerido}", r"\begin{itemize}"])
        for item in suggested_content:
            lines.append(r"\item " + _escape_latex_text(item))
        lines.extend([r"\end{itemize}", ""])
    for paragraph in draft_paragraphs:
        text = _escape_latex_text(paragraph)
        if text:
            lines.extend([text, ""])
    for block in content_blocks:
        block_title = _escape_latex_text(block.get("title", "Resumen"))
        block_items = block.get("items", []) or []
        if not block_items:
            continue
        lines.append(r"\subsection*{" + block_title + r"}")
        lines.append(r"\begin{itemize}")
        for item in block_items:
            lines.append(r"\item " + _escape_latex_text(item))
        lines.append(r"\end{itemize}")
        lines.append("")
    for idx, table in enumerate(latex_tables):
        if externalize_tables:
            table_name = str(table.get("table_file_name") or _default_table_file_name(section.get("id", ""), table.get("title", ""), idx))
            table["table_file_name"] = table_name
            table_stem = table_name[:-4] if table_name.endswith(".tex") else table_name
            lines.append(r"\input{" + tables_dir.replace("\\", "/") + "/" + table_stem + r"}")
            lines.append("")
        else:
            _build_latex_table(lines, table)
    if include_static_figures:
        _append_figure_blocks(lines, figure_refs, include_static_figures=include_static_figures, context_suffix=context_suffix)
    else:
        _append_figure_refs(lines, figure_refs, context_suffix=context_suffix)
    for child in child_sections:
        _append_latex_section(
            lines,
            child,
            externalize_tables=externalize_tables,
            tables_dir=tables_dir,
            include_static_figures=include_static_figures,
            heading_level=heading_level + 1,
        )
    lines.extend([r"% Espacio reservado para contenido desarrollado, tablas y figuras futuras.", ""])


def _render_latex_section(section, externalize_tables=False, tables_dir="tables", include_static_figures=False, heading_level=1):
    lines = []
    _append_latex_section(
        lines,
        section,
        externalize_tables=externalize_tables,
        tables_dir=tables_dir,
        include_static_figures=include_static_figures,
        heading_level=heading_level,
    )
    return "\n".join(lines).strip() + "\n"


def _append_appendix_content(lines, appendix_sections, appendix_hints, externalize_appendices=False, appendix_dir="appendices", include_static_figures=False):
    if not appendix_sections and not appendix_hints:
        return

    lines.extend([r"\clearpage", r"\appendix", r"\onehalfspacing", ""])
    if appendix_sections:
        if externalize_appendices:
            for idx, appendix in enumerate(appendix_sections):
                if idx > 0:
                    lines.extend([r"\FloatBarrier", r"\clearpage", ""])
                appendix_name = str(appendix.get("appendix_file_name") or appendix.get("id") or "appendix")
                appendix_stem = appendix_name[:-4] if appendix_name.endswith(".tex") else appendix_name
                lines.append(r"\input{" + appendix_dir.replace("\\", "/") + "/" + appendix_stem + r"}")
                lines.append("")
        else:
            for idx, appendix in enumerate(appendix_sections):
                if idx > 0:
                    lines.extend([r"\FloatBarrier", r"\clearpage", ""])
                _append_latex_section(lines, appendix, include_static_figures=include_static_figures)
    if appendix_hints:
        lines.extend([r"\section{Anexos sugeridos}", r"\begin{itemize}"])
        for hint in appendix_hints:
            lines.append(r"\item " + _escape_latex_text(hint))
        lines.extend([r"\end{itemize}", ""])


def build_latex_skeleton(report_payload, externalize_appendices=False, appendix_dir="appendices", include_static_figures=False):
    payload = report_payload or {}

    title = _escape_latex_text(payload.get("title", "Informe tecnico"))
    subtitle = _escape_latex_text(payload.get("subtitle", "Borrador inicial"))
    project_name = _escape_latex_text(payload.get("project_name", ""))
    report_style = _escape_latex_text(payload.get("report_style", "general"))
    citation_style = _escape_latex_text(payload.get("citation_style", "Opcional"))
    include_ai_declaration = bool(payload.get("include_ai_declaration", False))
    sections = payload.get("sections", []) or []
    appendix_sections = payload.get("appendix_sections", []) or []
    appendix_hints = payload.get("appendix_hints", []) or []
    references_hint = _escape_latex_text(payload.get("references_hint", ""))
    ai_declaration_text = _escape_latex_text(payload.get("ai_declaration_text", ""))

    lines = [
        r"\documentclass[12pt, letterpaper]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[spanish, es-tabla]{babel}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{geometry}",
        r"\geometry{margin=2.54cm}",
        r"\usepackage{times}",
        r"\usepackage{setspace}",
        r"\doublespacing",
        r"\usepackage{indentfirst}",
        r"\usepackage{graphicx}",
        r"\usepackage{hyperref}",
        r"\usepackage{booktabs}",
        r"\usepackage{tabularx}",
        r"\usepackage{longtable}",
        r"\usepackage{array}",
        r"\usepackage{float}",
        r"\usepackage{placeins}",
        r"\usepackage{microtype}",
        r"\newcolumntype{Y}{>{\raggedright\arraybackslash}X}",
        r"\setlength{\parindent}{1.27cm}",
        r"\setlength{\emergencystretch}{3em}",
        r"\setcounter{tocdepth}{3}",
        "",
        f"% Estilo de reporte: {report_style}",
        f"% Estilo de citas sugerido: {citation_style}",
        "% Archivo principal editable generado por Alfa app.",
        "% Puede reorganizar secciones, mover anexos o reemplazar figuras sin afectar los datos exportados.",
        "% Punto de entrada recomendado para Overleaf: compile este archivo como main.tex.",
        "% Los anexos viven en appendices/ y las tablas separadas en tables/ cuando el pack multiarchivo esta activo.",
        "",
        r"\title{" + title + r"\\[0.5em]\large " + subtitle + r"}",
        r"\author{Proyecto eolico}",
        r"\date{\today}",
        "",
        r"\begin{document}",
        r"\maketitle",
        "",
    ]

    if project_name:
        lines.extend([
            r"\noindent\textbf{Nombre del proyecto:} " + project_name + r"\\",
            r"\textbf{Estilo de reporte:} " + report_style + r"\\",
            r"\textbf{Estilo de citas sugerido:} " + citation_style,
            "",
        ])

    lines.extend([r"\tableofcontents", r"\newpage", ""])
    if externalize_appendices:
        lines.extend([
            "% Los anexos se incluyen mediante archivos separados en la carpeta indicada.",
            "% Esto facilita el trabajo en Overleaf u otros editores LaTeX multiarchivo.",
            "% En este modo se pueden usar figuras estaticas reales empaquetadas junto al proyecto.",
            "",
        ])
    else:
        lines.extend([
            "% Este exporte single-file prioriza compilacion segura.",
            "% Las figuras externas se dejan como referencias o placeholders editables para no depender de archivos adicionales.",
            "",
        ])

    for section in sections:
        _append_latex_section(lines, section, include_static_figures=include_static_figures)

    _append_appendix_content(
        lines,
        appendix_sections=appendix_sections,
        appendix_hints=appendix_hints,
        externalize_appendices=externalize_appendices,
        appendix_dir=appendix_dir,
        include_static_figures=include_static_figures,
    )

    if references_hint:
        lines.extend([r"\section*{Referencias}", references_hint, ""])

    if include_ai_declaration and ai_declaration_text:
        lines.extend([r"\section*{Declaracion de uso de IA}", ai_declaration_text, ""])

    lines.extend([r"\end{document}", ""])
    return "\n".join(lines)


def build_table_snippet_files(report_payload, tables_dir="tables"):
    payload = report_payload or {}
    appendix_sections = payload.get("appendix_sections", []) or []
    files = {}
    table_entries = []

    for appendix in appendix_sections:
        for section in _iter_section_tree(appendix):
            section_id = str(section.get("id") or "appendix").strip() or "appendix"
            for idx, table in enumerate(section.get("latex_tables", []) or []):
                table_name = str(table.get("table_file_name") or _default_table_file_name(section_id, table.get("title", ""), idx))
                table["table_file_name"] = table_name
                path = f"{tables_dir}/{table_name}"
                files[path] = _render_latex_table(table)
                table_entries.append({
                    "section_id": section_id,
                    "section_title": section.get("title", appendix.get("title", "Anexo")),
                    "table_title": table.get("title", "Tabla"),
                    "path": path,
                })

    return {
        "files": files,
        "entries": table_entries,
    }


def build_appendix_snippet_files(report_payload, appendix_dir="appendices", externalize_tables=False, tables_dir="tables", include_static_figures=False):
    payload = report_payload or {}
    appendix_sections = payload.get("appendix_sections", []) or []
    files = {}
    appendix_entries = []

    for appendix in appendix_sections:
        appendix_id = str(appendix.get("id") or "appendix").strip() or "appendix"
        file_name = str(appendix.get("appendix_file_name") or f"{appendix_id}.tex")
        appendix["appendix_file_name"] = file_name
        path = f"{appendix_dir}/{file_name}"
        files[path] = _render_latex_section(
            appendix,
            externalize_tables=externalize_tables,
            tables_dir=tables_dir,
            include_static_figures=include_static_figures,
            heading_level=1,
        )
        appendix_entries.append({
            "id": appendix_id,
            "title": appendix.get("title", "Anexo"),
            "path": path,
        })

    return {
        "files": files,
        "entries": appendix_entries,
    }


def build_latex_appendix_pack(report_payload, main_file_name="main.tex", appendix_dir="appendices", tables_dir="tables"):
    table_snippets = build_table_snippet_files(report_payload=report_payload, tables_dir=tables_dir)
    snippets = build_appendix_snippet_files(
        report_payload=report_payload,
        appendix_dir=appendix_dir,
        externalize_tables=True,
        tables_dir=tables_dir,
        include_static_figures=True,
    )
    main_text = build_latex_skeleton(
        report_payload=report_payload,
        externalize_appendices=True,
        appendix_dir=appendix_dir,
        include_static_figures=True,
    )
    return {
        "main_file_name": main_file_name,
        "main_text": main_text,
        "appendix_files": snippets["files"],
        "appendix_entries": snippets["entries"],
        "table_files": table_snippets["files"],
        "table_entries": table_snippets["entries"],
    }
