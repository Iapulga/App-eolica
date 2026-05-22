import io
import json
import os
import zipfile


def _build_zip_bytes(package_files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted((package_files or {}).keys()):
            content = package_files[path]
            if isinstance(content, bytes):
                zf.writestr(path, content)
            else:
                zf.writestr(path, str(content))
    return output.getvalue()


def build_appendix_pack_zip_bytes(package_files):
    return _build_zip_bytes(package_files)


def _latex_escape_path(path):
    return str(path or "").replace("\\", "/").replace("_", r"\_")


def _optimize_mirrored_png_bytes(content, max_dimension=1600):
    try:
        from PIL import Image
    except Exception:
        return content

    try:
        with Image.open(io.BytesIO(content)) as image:
            image = image.convert("RGBA")
            width, height = image.size
            longest = max(width, height)
            if longest > int(max_dimension):
                scale = float(max_dimension) / float(longest)
                new_size = (
                    max(1, int(round(width * scale))),
                    max(1, int(round(height * scale))),
                )
                image = image.resize(new_size, Image.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True, compress_level=9)
            return output.getvalue()
    except Exception:
        return content


def _mirror_static_figure_files(figure_files):
    mirrored_files = {}
    path_map = {}
    for path, content in (figure_files or {}).items():
        normalized = str(path or "").replace("\\", "/")
        ext = os.path.splitext(normalized)[1].lower()
        if ext not in [".png", ".svg", ".pdf"]:
            continue
        basename = os.path.basename(normalized)
        mirrored_path = f"01_Informe/figures/{basename}"
        if ext == ".png" and isinstance(content, (bytes, bytearray)):
            mirrored_files[mirrored_path] = _optimize_mirrored_png_bytes(bytes(content), max_dimension=1600)
        else:
            mirrored_files[mirrored_path] = content
        path_map[normalized] = f"figures/{basename}"
    return mirrored_files, path_map


def _rewrite_tex_asset_paths(tex_text, path_map):
    text = str(tex_text or "")
    for original, target in (path_map or {}).items():
        text = text.replace(original, target)
        text = text.replace(_latex_escape_path(original), _latex_escape_path(target))
    return text


def _collect_pack_inventory(report_payload, appendix_files, table_files, figure_files, mirrored_path_map):
    report_payload = report_payload or {}
    appendix_files = appendix_files or {}
    table_files = table_files or {}
    figure_files = figure_files or {}
    mirrored_path_map = mirrored_path_map or {}

    section_records = []
    appendix_lookup = {
        str(section.get("appendix_file_name") or f"{section.get('id', 'appendix')}.tex"): section
        for section in (report_payload.get("appendix_sections", []) or [])
    }

    def _iter_appendix_tree(section, snippet_file):
        if not isinstance(section, dict):
            return
        yield section, snippet_file
        for child in section.get("child_sections", []) or []:
            yield from _iter_appendix_tree(child, snippet_file)

    for section in report_payload.get("sections", []) or []:
        figures = []
        for fig in section.get("figure_refs", []) or []:
            figures.append({
                "title": fig.get("title", "Figura"),
                "label": fig.get("label", ""),
                "source_path": fig.get("path", ""),
                "render_mode": fig.get("render_mode", "placeholder"),
                "mirrored_path": mirrored_path_map.get(str(fig.get("path", "")).replace("\\", "/"), ""),
            })
        section_records.append({
            "kind": "main",
            "section_id": section.get("id", ""),
            "section_title": section.get("title", ""),
            "snippet_file": "",
            "table_titles": [table.get("title", "") for table in (section.get("latex_tables", []) or [])],
            "table_files": [],
            "figures": figures,
        })

    for path in appendix_files.keys():
        file_name = os.path.basename(path)
        section = appendix_lookup.get(file_name, {})
        for tree_section, snippet_file in _iter_appendix_tree(section, path):
            table_refs = []
            for table in tree_section.get("latex_tables", []) or []:
                table_name = table.get("table_file_name", "")
                if table_name:
                    table_refs.append(f"tables/{table_name}")
            figures = []
            for fig in tree_section.get("figure_refs", []) or []:
                figures.append({
                    "title": fig.get("title", "Figura"),
                    "label": fig.get("label", ""),
                    "source_path": fig.get("path", ""),
                    "render_mode": fig.get("render_mode", "placeholder"),
                    "mirrored_path": mirrored_path_map.get(str(fig.get("path", "")).replace("\\", "/"), ""),
                })
            section_records.append({
                "kind": "appendix",
                "section_id": tree_section.get("id", ""),
                "section_title": tree_section.get("title", file_name),
                "snippet_file": snippet_file,
                "table_titles": [table.get("title", "") for table in (tree_section.get("latex_tables", []) or [])],
                "table_files": table_refs,
                "figures": figures,
            })

    static_used = []
    html_only = []
    missing = []
    for record in section_records:
        for fig in record.get("figures", []):
            item = {
                "section_title": record.get("section_title", ""),
                "title": fig.get("title", ""),
                "label": fig.get("label", ""),
                "source_path": fig.get("source_path", ""),
                "mirrored_path": fig.get("mirrored_path", ""),
                "render_mode": fig.get("render_mode", "placeholder"),
            }
            if fig.get("render_mode") == "includegraphics" and fig.get("mirrored_path"):
                static_used.append(item)
            elif fig.get("render_mode") == "html_reference":
                html_only.append(item)
            else:
                missing.append(item)

    compile_ready = {
        "main_file_to_compile": "01_Informe/main.tex",
        "appendix_files": sorted(appendix_files.keys()),
        "table_files": sorted(table_files.keys()),
        "latex_used_static_figures": static_used,
        "html_only_figures": html_only,
        "missing_figures": missing,
        "paths_to_verify_after_upload": [
            "01_Informe/main.tex",
            "01_Informe/appendices/",
            "01_Informe/tables/",
            "01_Informe/figures/",
        ],
        "notes": [
            "Compilar main.tex como punto de entrada.",
            "Las figuras PNG/SVG/PDF espejadas en 01_Informe/figures ya quedan listas para \\includegraphics.",
            "Las figuras disponibles solo como HTML siguen requiriendo conversion o insercion manual.",
            "La bibliografia y el pulido narrativo siguen siendo pasos manuales.",
        ],
    }

    inventory = {
        "main_file": "01_Informe/main.tex",
        "appendix_files": sorted(appendix_files.keys()),
        "table_files": sorted(table_files.keys()),
        "mirrored_static_figures": sorted(mirrored_path_map.values()),
        "original_figure_artifacts": sorted((figure_files or {}).keys()),
        "sections": section_records,
        "compile_ready": compile_ready,
    }

    lines = [
        "Inventario del pack LaTeX",
        "",
        f"Archivo principal: {inventory['main_file']}",
        f"Snippets de anexos: {len(inventory['appendix_files'])}",
        f"Snippets de tablas: {len(inventory['table_files'])}",
        f"Figuras estaticas espejadas en 01_Informe/figures: {len(inventory['mirrored_static_figures'])}",
        "",
    ]
    for record in section_records:
        lines.append(f"- [{record['kind']}] {record['section_title'] or record['section_id']}")
        if record["snippet_file"]:
            lines.append(f"  snippet: {record['snippet_file']}")
        if record["table_titles"]:
            lines.append(f"  tablas: {', '.join(record['table_titles'])}")
        if record.get("table_files"):
            lines.append(f"  archivos de tabla: {', '.join(record['table_files'])}")
        if record["figures"]:
            figure_parts = []
            for fig in record["figures"]:
                suffix = fig["mirrored_path"] or fig["source_path"] or "sin artefacto"
                figure_parts.append(f"{fig['title']} -> {suffix} ({fig['render_mode']})")
            lines.append(f"  figuras: {'; '.join(figure_parts)}")
    inventory_text = "\n".join(lines) + "\n"

    compile_lines = [
        "Guia compacta de compile readiness",
        "",
        f"Archivo principal a compilar: {compile_ready['main_file_to_compile']}",
        f"Snippets de anexos: {len(compile_ready['appendix_files'])}",
        f"Snippets de tablas: {len(compile_ready['table_files'])}",
        f"Figuras estaticas listas para LaTeX: {len(static_used)}",
        f"Figuras solo HTML: {len(html_only)}",
        f"Figuras aun faltantes o manuales: {len(missing)}",
        "",
        "Rutas a verificar tras subir el proyecto:",
    ]
    for path in compile_ready["paths_to_verify_after_upload"]:
        compile_lines.append(f"- {path}")
    compile_lines.extend(["", "Figuras listas para LaTeX:"])
    if static_used:
        for item in static_used:
            compile_lines.append(f"- {item['title']} -> {item['mirrored_path']}")
    else:
        compile_lines.append("- No se detectaron figuras estaticas espejadas para uso directo.")
    compile_lines.extend(["", "Figuras solo HTML:"])
    if html_only:
        for item in html_only:
            compile_lines.append(f"- {item['title']} -> {item['source_path']}")
    else:
        compile_lines.append("- No hay figuras exclusivamente HTML en esta exportacion.")
    compile_lines.extend(["", "Figuras pendientes/manuales:"])
    if missing:
        for item in missing:
            compile_lines.append(f"- {item['title']} ({item['section_title']})")
    else:
        compile_lines.append("- No se detectaron figuras faltantes en las referencias del pack.")
    compile_lines.extend(["", "Notas:"])
    for note in compile_ready["notes"]:
        compile_lines.append(f"- {note}")
    compile_text = "\n".join(compile_lines) + "\n"
    return inventory, inventory_text, compile_ready, compile_text


def build_appendix_pack_files(
    report_payload,
    report_manifest,
    main_latex_text,
    appendix_files,
    table_files=None,
    export_metadata=None,
    generated_artifacts=None,
    main_file_name="main.tex",
):
    report_payload = report_payload or {}
    report_manifest = report_manifest or {}
    export_metadata = export_metadata or {}
    generated_artifacts = generated_artifacts or {}
    appendix_files = appendix_files or {}
    table_files = table_files or {}
    report_style = str(report_payload.get("report_style") or "general")
    figure_files = generated_artifacts.get("figure_files", {}) or {}
    mirrored_figure_files, mirrored_path_map = _mirror_static_figure_files(figure_files)
    rewritten_main_latex = _rewrite_tex_asset_paths(main_latex_text, mirrored_path_map)
    rewritten_appendix_files = {
        path: _rewrite_tex_asset_paths(content, mirrored_path_map)
        for path, content in appendix_files.items()
    }
    inventory_json, inventory_text, compile_ready_json, compile_ready_text = _collect_pack_inventory(
        report_payload=report_payload,
        appendix_files=rewritten_appendix_files,
        table_files=table_files,
        figure_files=figure_files,
        mirrored_path_map=mirrored_path_map,
    )

    files = {
        "01_Informe/README.txt": (
            "Este paquete consolida el informe principal y todos los anexos dentro de un unico documento LaTeX multiarchivo.\n"
            "Archivo de entrada recomendado: `main.tex`.\n"
            "Los anexos viven en `appendices/`, las tablas grandes en `tables/` y las figuras estaticas listas para LaTeX en `figures/`.\n"
            "Compile solo `main.tex`: desde ahi se incorpora el cuerpo del informe y un flujo unico de apendices por fases.\n"
            "Revise `metadata/inventory_compile_ready.txt` para ver que activos estan realmente listos para compilar y cuales siguen en HTML o pendientes.\n"
            "Si alguna figura existe solo como HTML, use la referencia en el inventario y conviertala o insertela manualmente.\n"
            "Flujo sugerido:\n"
            "1. Suba la carpeta 01_Informe a Overleaf.\n"
            "2. Abra y compile `main.tex`.\n"
            "3. Revise `appendices/`, `tables/` y `figures/`.\n"
            "4. Complete bibliografia, narrativa final y figuras HTML faltantes.\n"
        ),
        "01_Informe/main.tex": rewritten_main_latex,
        "01_Informe/metadata/manifiesto_reporte.json": json.dumps(report_manifest, ensure_ascii=False, indent=2),
    }
    if export_metadata:
        files["01_Informe/metadata/metadata_exportacion.json"] = json.dumps(export_metadata, ensure_ascii=False, indent=2)

    appendix_index = [
        "Snippets de anexos incluidos:",
        "",
    ]
    if rewritten_appendix_files:
        for path, content in rewritten_appendix_files.items():
            files[f"01_Informe/{path}"] = content
            appendix_index.append(f"- {path}")
    else:
        appendix_index.append("- No hay anexos estructurados disponibles en esta exportacion.")
    files["01_Informe/appendices/README.txt"] = "\n".join(appendix_index) + "\n"
    table_index = ["Snippets tabulares incluidos:", ""]
    if table_files:
        for path, content in table_files.items():
            files[f"01_Informe/{path}"] = content
            table_index.append(f"- {path}")
    else:
        table_index.append("- No se generaron snippets tabulares separados en esta exportacion.")
    files["01_Informe/tables/README.txt"] = "\n".join(table_index) + "\n"
    files["01_Informe/figures/README.txt"] = (
        "Use esta carpeta si decide copiar aqui un subconjunto de figuras para compilar en un proyecto LaTeX aislado.\n"
        "La app mantiene los artefactos originales en 04_Figuras_mapas/.\n"
    )
    files["01_Informe/metadata/README.txt"] = (
        "Metadatos y trazabilidad del pack LaTeX.\n"
        f"Estilo de reporte detectado: {report_style}\n"
    )

    files["02_Anexos/README.txt"] = "Resultados tabulares y exportes auxiliares del escenario actual.\n"
    files["03_Datos_crudos/README.txt"] = "Procedencia y referencias a datos crudos asociados al escenario.\n"
    files["04_Figuras_mapas/README.txt"] = "Artefactos graficos y referencias visuales para ensamblar el informe.\n"

    for key, path in [
        ("excel_bytes", "02_Anexos/resultados_fase5.xlsx"),
        ("csv_bytes", "02_Anexos/resultados_fase5.csv"),
        ("summary_json", "02_Anexos/resumen_resultados_fase5.json"),
        ("provenance_json", "03_Datos_crudos/procedencia_datos.json"),
        ("provenance_txt", "03_Datos_crudos/procedencia_datos.txt"),
        ("figures_manifest_json", "04_Figuras_mapas/manifiesto_figuras_mapas.json"),
        ("figures_manifest_txt", "04_Figuras_mapas/figuras_mapas.txt"),
    ]:
        content = generated_artifacts.get(key)
        if content:
            files[path] = content

    for path, content in figure_files.items():
        files[path] = content
    for path, content in mirrored_figure_files.items():
        files[path] = content

    files["01_Informe/metadata/resumen_pack.txt"] = (
        "Pack de anexos LaTeX generado automaticamente como un unico documento principal.\n"
        "Archivo principal recomendado: main.tex\n"
        "Los apendices se integran dentro del mismo documento mediante snippets multiarchivo.\n"
        f"Snippets de anexos: {len(rewritten_appendix_files)}\n"
        f"Snippets tabulares: {len(table_files)}\n"
        f"Artefactos graficos originales: {len(figure_files)}\n"
        f"Figuras estaticas espejadas en 01_Informe/figures: {len(mirrored_figure_files)}\n"
    )
    files["01_Informe/metadata/inventory_appendices.json"] = json.dumps(inventory_json, ensure_ascii=False, indent=2)
    files["01_Informe/metadata/inventory_appendices.txt"] = inventory_text
    files["01_Informe/metadata/inventory_compile_ready.json"] = json.dumps(compile_ready_json, ensure_ascii=False, indent=2)
    files["01_Informe/metadata/inventory_compile_ready.txt"] = compile_ready_text
    return files
