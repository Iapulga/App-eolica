import base64
import math
import re
import unicodedata
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from calculos import (
    SECTOR_CENTERS_16,
    SECTOR_LABELS_16,
    ajustar_logaritmico_dos_puntos,
    analizar_estelas_parque_16,
    calcular_alpha_desde_dos_alturas,
    calcular_cp,
    calcular_estelas_jensen_direccion,
    calcular_perfil_exponencial,
    calcular_perfil_logaritmico,
    construir_serie_viento_analisis,
    crear_figura_direccion_estela,
    crear_figura_layout_parque,
    crear_grafica_curva,
    crear_grafica_nasa_hourly,
    crear_grafica_perfil_individual,
    crear_histograma_sector_con_ajustes,
    crear_rosa_vientos_16,
    inferir_puntos_operacion_curva,
    preparar_datos_curva,
    preparar_datos_rosa,
    rayleigh_cdf,
    rayleigh_interval_prob,
    resumir_sectores_rosa,
    velocidad_logaritmica_en_altura,
    weibull_cdf,
    weibull_interval_prob,
)

from .texto import normalize_spanish_text as _normalize_spanish_text


def _slugify_figure_name(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_") or "figura"

def _safe_export_file_name(stem, extension):
    safe_stem = _slugify_figure_name(stem)
    ext = str(extension or "").strip().lower()
    if not ext.startswith("."):
        ext = f".{ext}" if ext else ""
    if not re.fullmatch(r"\.[a-z0-9]+", ext or ""):
        ext = ".png"
    return f"{safe_stem}{ext}"


def _norm_col(texto):
    """Clave comparable de un nombre de columna (tolera tildes, mojibake y signos)."""
    t = _normalize_spanish_text(str(texto or ""))
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", t.lower())


def _col(df, *candidatos):
    """Nombre real de la primera columna de `df` que coincide con algún candidato (o None)."""
    if df is None:
        return None
    mapa = {_norm_col(c): c for c in df.columns}
    for cand in candidatos:
        real = mapa.get(_norm_col(cand))
        if real is not None:
            return real
    return None




def _normalize_plotly_figure_text(fig):
    if fig is None:
        return fig
    fig = go.Figure(fig)
    try:
        if getattr(getattr(fig.layout, "title", None), "text", None):
            fig.layout.title.text = _normalize_spanish_text(fig.layout.title.text)
        for axis_name in ["xaxis", "yaxis", "xaxis2", "yaxis2", "polar", "polar2", "scene", "scene2", "scene3"]:
            axis = getattr(fig.layout, axis_name, None)
            if axis is None:
                continue
            title_obj = getattr(axis, "title", None)
            if getattr(title_obj, "text", None):
                title_obj.text = _normalize_spanish_text(title_obj.text)
            colorbar = getattr(axis, "colorbar", None)
            if getattr(getattr(colorbar, "title", None), "text", None):
                colorbar.title.text = _normalize_spanish_text(colorbar.title.text)
            if axis_name.startswith("polar"):
                for sub in ("radialaxis", "angularaxis"):
                    sub_axis = getattr(axis, sub, None)
                    sub_title = getattr(sub_axis, "title", None)
                    if getattr(sub_title, "text", None):
                        sub_title.text = _normalize_spanish_text(sub_title.text)
        legend_title = getattr(getattr(fig.layout, "legend", None), "title", None)
        if getattr(legend_title, "text", None):
            legend_title.text = _normalize_spanish_text(legend_title.text)
        for ann in fig.layout.annotations or []:
            if getattr(ann, "text", None):
                ann.text = _normalize_spanish_text(ann.text)
        for trace in fig.data:
            if getattr(trace, "name", None):
                trace.name = _normalize_spanish_text(trace.name)
            colorbar = getattr(trace, "colorbar", None)
            if getattr(getattr(colorbar, "title", None), "text", None):
                colorbar.title.text = _normalize_spanish_text(colorbar.title.text)
            try:
                marker_cb = getattr(getattr(trace, "marker", None), "colorbar", None)
                if getattr(getattr(marker_cb, "title", None), "text", None):
                    marker_cb.title.text = _normalize_spanish_text(marker_cb.title.text)
            except Exception:
                pass
            if getattr(trace, "hovertemplate", None):
                trace.hovertemplate = _normalize_spanish_text(trace.hovertemplate)
    except Exception:
        return fig
    return fig


def _is_number_like(value):
    try:
        float(value)
        return True
    except Exception:
        return False


def _plotly_color_to_matplotlib(color, fallback=None):
    if color is None:
        return fallback or "#4c78a8"
    if isinstance(color, np.ndarray):
        if color.size == 0:
            return fallback or "#4c78a8"
        return color[0]
    if isinstance(color, (list, tuple)):
        return color[0] if color else (fallback or "#4c78a8")
    text = str(color)
    if not text.strip():
        return fallback or "#4c78a8"
    return text


def _color_sequence_for_values(values, cmap_name="viridis"):
    try:
        import matplotlib.cm as cm
        import matplotlib.colors as mcolors
    except Exception:
        return None

    numeric = np.asarray(values, dtype=float)
    if numeric.size == 0:
        return None
    vmin = float(np.nanmin(numeric))
    vmax = float(np.nanmax(numeric))
    if not np.isfinite(vmin) or not np.isfinite(vmax):
        return None
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1.0
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap = cm.get_cmap(cmap_name)
    return [cmap(norm(item)) for item in numeric]


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return list(value)
    except Exception:
        return [value]


def _optimize_png_bytes(content, max_dimension=1600):
    try:
        from PIL import Image
    except Exception:
        return content

    try:
        with Image.open(BytesIO(content)) as image:
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
            output = BytesIO()
            image.save(output, format="PNG", optimize=True, compress_level=9)
            return output.getvalue()
    except Exception:
        return content


def _export_plotly_figure_matplotlib(fig, title="", export_options=None):
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle
    except Exception as exc:
        raise RuntimeError(f"matplotlib no esta disponible: {exc}") from exc

    export_options = export_options or {}
    figsize = tuple(export_options.get("figsize") or ())

    def _pick_size(default_width, default_height):
        if len(figsize) == 2:
            return figsize
        width = float(export_options.get("width") or default_width)
        height = float(export_options.get("height") or default_height)
        return (max(4.0, width / 150.0), max(3.2, height / 150.0))

    traces = list(getattr(fig, "data", []) or [])
    if not traces:
        raise RuntimeError("La figura no contiene trazas renderizables.")

    trace_types = [str(getattr(trace, "type", "") or "").lower() for trace in traces]
    output = BytesIO()

    if "histogram" in trace_types and all(t in ["histogram", "scatter"] for t in trace_types):
        mpl_fig, ax = plt.subplots(figsize=_pick_size(960, 620), dpi=160)
        layout = getattr(fig, "layout", None)
        histogram_traces = [trace for trace in traces if str(getattr(trace, "type", "") or "").lower() == "histogram"]
        scatter_traces = [trace for trace in traces if str(getattr(trace, "type", "") or "").lower() == "scatter"]

        for idx, trace in enumerate(histogram_traces):
            x_values = [float(v) for v in _as_list(getattr(trace, "x", [])) if _is_number_like(v)]
            if not x_values:
                continue
            nbins = getattr(trace, "nbinsx", None)
            try:
                bins = int(nbins) if nbins is not None else min(24, max(8, int(np.sqrt(len(x_values)) * 2)))
            except Exception:
                bins = min(24, max(8, int(np.sqrt(len(x_values)) * 2)))
            histnorm = str(getattr(trace, "histnorm", "") or "").lower()
            density = histnorm in ["probability density", "density"]
            weights = None
            if histnorm in ["percent", "probability"]:
                divisor = 100.0 if histnorm == "percent" else float(len(x_values))
                if divisor > 0:
                    weights = np.ones(len(x_values), dtype=float) / divisor
            color = _plotly_color_to_matplotlib(getattr(getattr(trace, "marker", None), "color", None), fallback="#8fb8de")
            label = str(getattr(trace, "name", "") or f"Histograma {idx + 1}")
            ax.hist(
                x_values,
                bins=bins,
                density=density,
                weights=weights,
                color=color,
                alpha=float(getattr(trace, "opacity", 0.65) or 0.65),
                edgecolor="white",
                linewidth=0.7,
                label=label,
            )

        for idx, trace in enumerate(scatter_traces):
            x_values = [float(v) for v in _as_list(getattr(trace, "x", [])) if _is_number_like(v)]
            y_values = [float(v) for v in _as_list(getattr(trace, "y", [])) if _is_number_like(v)]
            if not x_values or not y_values:
                continue
            usable_len = min(len(x_values), len(y_values))
            mode = str(getattr(trace, "mode", "") or "lines").lower()
            color = _plotly_color_to_matplotlib(getattr(getattr(trace, "line", None), "color", None), fallback="#1f77b4")
            dash = str(getattr(getattr(trace, "line", None), "dash", "") or "").lower()
            linestyle = "--" if "dash" in dash else "-"
            marker = "o" if "markers" in mode else None
            linewidth = float(getattr(getattr(trace, "line", None), "width", 2) or 2)
            ax.plot(
                x_values[:usable_len],
                y_values[:usable_len],
                label=str(getattr(trace, "name", "") or f"Serie {idx + 1}"),
                color=color,
                marker=marker,
                linestyle=linestyle,
                linewidth=linewidth,
            )

        if getattr(getattr(layout, "xaxis", None), "title", None):
            ax.set_xlabel(_normalize_spanish_text(str(layout.xaxis.title.text or "")))
        if getattr(getattr(layout, "yaxis", None), "title", None):
            ax.set_ylabel(_normalize_spanish_text(str(layout.yaxis.title.text or "")))
        ax.set_title(_normalize_spanish_text(str(getattr(getattr(layout, "title", None), "text", None) or title or "Figura")))
        ax.grid(True, alpha=0.22)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, loc="best")
        mpl_fig.tight_layout()
        mpl_fig.savefig(output, format="png", bbox_inches="tight")
        plt.close(mpl_fig)
        return output.getvalue()

    if all(t in ["scatter", "bar"] for t in trace_types):
        mpl_fig, ax = plt.subplots(figsize=_pick_size(960, 620), dpi=160)
        layout = getattr(fig, "layout", None)
        has_secondary = any(str(getattr(trace, "yaxis", "") or "y").lower() == "y2" for trace in traces)
        ax2 = ax.twinx() if has_secondary else None
        categorical_map = {}

        def map_x(values):
            mapped = []
            for val in values:
                if _is_number_like(val):
                    mapped.append(float(val))
                else:
                    key = str(val)
                    if key not in categorical_map:
                        categorical_map[key] = len(categorical_map)
                    mapped.append(float(categorical_map[key]))
            return mapped

        bar_traces = [trace for trace in traces if str(getattr(trace, "type", "")).lower() == "bar"]
        scatter_traces = [trace for trace in traces if str(getattr(trace, "type", "")).lower() == "scatter"]
        bar_width = 0.8 / max(1, len(bar_traces))

        for idx, trace in enumerate(bar_traces):
            target_ax = ax2 if str(getattr(trace, "yaxis", "") or "y").lower() == "y2" and ax2 is not None else ax
            x_values = _as_list(getattr(trace, "x", []))
            y_values = [float(v) for v in _as_list(getattr(trace, "y", []))]
            mapped_x = np.array(map_x(x_values), dtype=float) + (idx - (len(bar_traces) - 1) / 2.0) * bar_width
            color = _plotly_color_to_matplotlib(getattr(getattr(trace, "marker", None), "color", None))
            target_ax.bar(mapped_x, y_values, width=bar_width * 0.92, label=str(getattr(trace, "name", "") or f"Serie {idx + 1}"), color=color, alpha=0.9)

        for idx, trace in enumerate(scatter_traces):
            target_ax = ax2 if str(getattr(trace, "yaxis", "") or "y").lower() == "y2" and ax2 is not None else ax
            x_values = _as_list(getattr(trace, "x", []))
            y_values = [float(v) for v in _as_list(getattr(trace, "y", []))]
            mapped_x = map_x(x_values)
            mode = str(getattr(trace, "mode", "") or "lines").lower()
            color = _plotly_color_to_matplotlib(getattr(getattr(trace, "line", None), "color", None), fallback="#1f77b4")
            marker = "o" if "markers" in mode else None
            target_ax.plot(mapped_x, y_values, label=str(getattr(trace, "name", "") or f"Serie {idx + 1}"), color=color, marker=marker, linewidth=2)
            text_values = _as_list(getattr(trace, "text", []))
            if text_values and len(text_values) == len(mapped_x):
                for px, py, text_value in zip(mapped_x, y_values, text_values):
                    if str(text_value or "").strip():
                        target_ax.annotate(str(text_value), (px, py), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)

        if categorical_map:
            ordered = sorted(categorical_map.items(), key=lambda item: item[1])
            ax.set_xticks([item[1] for item in ordered], [item[0] for item in ordered], rotation=25, ha="right")

        if getattr(getattr(layout, "xaxis", None), "title", None):
            ax.set_xlabel(str(layout.xaxis.title.text or ""))
        if getattr(getattr(layout, "yaxis", None), "title", None):
            ax.set_ylabel(str(layout.yaxis.title.text or ""))
        if ax2 is not None and getattr(getattr(layout, "yaxis2", None), "title", None):
            ax2.set_ylabel(str(layout.yaxis2.title.text or ""))
        ax.set_title(str(getattr(getattr(layout, "title", None), "text", None) or title or "Figura"))
        ax.grid(True, alpha=0.25)
        for shape in list(getattr(layout, "shapes", []) or []):
            shape_type = str(getattr(shape, "type", "") or "").lower()
            if shape_type == "circle":
                try:
                    x0 = float(shape.x0)
                    x1 = float(shape.x1)
                    y0 = float(shape.y0)
                    y1 = float(shape.y1)
                    center = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
                    radius = abs(x1 - x0) / 2.0
                    edgecolor = _plotly_color_to_matplotlib(getattr(getattr(shape, "line", None), "color", None), fallback="#4c78a8")
                    ax.add_patch(Circle(center, radius, fill=False, edgecolor=edgecolor, linewidth=1.0, alpha=0.35))
                except Exception:
                    pass
            elif shape_type == "line":
                try:
                    x0 = float(shape.x0)
                    x1 = float(shape.x1)
                    y0 = float(shape.y0)
                    y1 = float(shape.y1)
                    color = _plotly_color_to_matplotlib(getattr(getattr(shape, "line", None), "color", None), fallback="#7a7a7a")
                    linestyle = ":" if str(getattr(getattr(shape, "line", None), "dash", "") or "").lower() else "-"
                    ax.plot([x0, x1], [y0, y1], color=color, linestyle=linestyle, linewidth=1.0, alpha=0.6)
                except Exception:
                    pass
        handles, labels = ax.get_legend_handles_labels()
        if ax2 is not None:
            handles2, labels2 = ax2.get_legend_handles_labels()
            handles.extend(handles2)
            labels.extend(labels2)
        if handles:
            ax.legend(handles, labels, loc="best")
        if str(getattr(getattr(layout, "yaxis", None), "scaleanchor", "") or "").lower() == "x":
            ax.set_aspect("equal", adjustable="box")
        mpl_fig.tight_layout()
        mpl_fig.savefig(output, format="png", bbox_inches="tight")
        plt.close(mpl_fig)
        return output.getvalue()

    if len(traces) == 1 and trace_types[0] == "pie":
        trace = traces[0]
        mpl_fig, ax = plt.subplots(figsize=(7.2, 5.6), dpi=160)
        labels = [str(v) for v in _as_list(getattr(trace, "labels", []))]
        values = [float(v) for v in _as_list(getattr(trace, "values", []))]
        ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
        ax.set_title(str(getattr(getattr(fig.layout, "title", None), "text", None) or title or "Figura"))
        mpl_fig.tight_layout()
        mpl_fig.savefig(output, format="png", bbox_inches="tight")
        plt.close(mpl_fig)
        return output.getvalue()

    if len(traces) == 1 and trace_types[0] == "heatmap":
        trace = traces[0]
        z = np.array(_as_list(getattr(trace, "z", [])))
        mpl_fig, ax = plt.subplots(figsize=(8.2, 5.8), dpi=160)
        im = ax.imshow(z, aspect="auto", cmap="YlOrRd")
        x_values = _as_list(getattr(trace, "x", []))
        y_values = _as_list(getattr(trace, "y", []))
        if x_values:
            ax.set_xticks(range(len(x_values)), [str(v) for v in x_values], rotation=35, ha="right")
        if y_values:
            ax.set_yticks(range(len(y_values)), [str(v) for v in y_values])
        ax.set_title(str(getattr(getattr(fig.layout, "title", None), "text", None) or title or "Figura"))
        plt.colorbar(im, ax=ax)
        mpl_fig.tight_layout()
        mpl_fig.savefig(output, format="png", bbox_inches="tight")
        plt.close(mpl_fig)
        return output.getvalue()

    if all(t in ["barpolar", "scatterpolar"] for t in trace_types):
        mpl_fig, ax = plt.subplots(figsize=(7.0, 7.0), dpi=160, subplot_kw={"projection": "polar"})
        for idx, trace in enumerate(traces):
            theta = np.deg2rad([float(v) for v in _as_list(getattr(trace, "theta", []))])
            r = [float(v) for v in _as_list(getattr(trace, "r", []))]
            name = str(getattr(trace, "name", "") or f"Serie {idx + 1}")
            marker_color = getattr(getattr(trace, "marker", None), "color", None)
            color = _plotly_color_to_matplotlib(marker_color, fallback="#4c78a8")
            if trace_types[idx] == "barpolar":
                width = np.repeat((2 * np.pi / max(1, len(theta))) * 0.9, len(theta))
                if isinstance(marker_color, (list, tuple, np.ndarray)):
                    color_sequence = _color_sequence_for_values(marker_color, cmap_name="Blues")
                    ax.bar(theta, r, width=width, alpha=0.82, color=color_sequence or color, label=name)
                else:
                    ax.bar(theta, r, width=width, alpha=0.75, color=color, label=name)
            else:
                ax.plot(theta, r, linewidth=2, marker="o", color=color, label=name)
        ax.set_title(str(getattr(getattr(fig.layout, "title", None), "text", None) or title or "Figura"))
        if len(traces) > 1:
            ax.legend(loc="upper right", bbox_to_anchor=(1.18, 1.10))
        mpl_fig.tight_layout()
        mpl_fig.savefig(output, format="png", bbox_inches="tight")
        plt.close(mpl_fig)
        return output.getvalue()

    raise RuntimeError(f"Las trazas {trace_types} no tienen fallback estatico implementado.")


_RE_CIFRA_INGLES_MILES = re.compile(r"^([−-]?)(\d{1,3}(?:,\d{3})+)\.(\d+)$")
_RE_CIFRA_INGLES_DECIMAL = re.compile(r"^([−-]?\d+)\.(\d{1,2})$")
_RE_PORCENTAJE_INGLES = re.compile(r"(?<![\d.,])(\d{1,3})\.(\d{1,2})(?=\s?%)")


def _cifra_en_espanol(texto):
    """'62,858.2' → '62.858,2' y '-33.9' → '-33,9'. Solo formatos ingleses inequívocos: una cifra que ya
    está en español (p. ej. '62.858') se deja igual."""
    limpio = texto.strip()
    m = _RE_CIFRA_INGLES_MILES.match(limpio)
    if m:
        return f"{m.group(1)}{m.group(2).replace(',', '.')},{m.group(3)}"
    m = _RE_CIFRA_INGLES_DECIMAL.match(limpio)
    if m:
        return f"{m.group(1)},{m.group(2)}"
    return texto


def _imagen_formal(fig):
    """Copia para la imagen estática: sin título interno (el título lo pone el rótulo «Figura N.» del
    documento o el nombre del archivo) y con separadores decimales en español. Si la leyenda va arriba
    conserva su espacio; si no, se recorta el margen superior que ocupaba el título."""
    try:
        fig = go.Figure(fig)
        leyenda = fig.layout.legend
        leyenda_arriba = leyenda.orientation == "h" and leyenda.y is not None and leyenda.y >= 0.95
        if getattr(fig.layout.title, "text", None):
            fig.layout.title.text = None
            if not leyenda_arriba:
                t = fig.layout.margin.t
                fig.layout.margin.t = 50 if t is None else min(t, 50)
        fig.layout.separators = ",."
        for traza in fig.data:  # etiquetas de valor escritas en formato inglés
            texto = getattr(traza, "text", None)
            if isinstance(texto, (list, tuple)) and texto and all(isinstance(x, str) for x in texto):
                traza.text = [_cifra_en_espanol(x) for x in texto]
        for anotacion in fig.layout.annotations or ():  # «6.42%» → «6,42%»
            if isinstance(anotacion.text, str):
                anotacion.text = _RE_PORCENTAJE_INGLES.sub(r"\1,\2", anotacion.text)
    except Exception:
        pass
    return fig


def export_plotly_figure_artifact(fig, figure_id, title, stem=None, source_hint="", preferred_format="png", export_options=None):
    fig = _normalize_plotly_figure_text(fig)
    if fig is not None:
        try:  # estilo formal común de los entregables (Calibri, paleta azul marino, rejilla suave)
            from .estilo import recolorear_plotly, registrar_plantilla_plotly

            fig = recolorear_plotly(go.Figure(fig))
            fig.update_layout(template=registrar_plantilla_plotly(),
                              font=dict(family="Calibri, Segoe UI, Arial, sans-serif"))
        except Exception:
            pass
    title = _normalize_spanish_text(title or "")
    source_hint = _normalize_spanish_text(source_hint or "")
    filename_stem = _slugify_figure_name(stem or figure_id or title)
    export_options = export_options or {}
    metadata = {
        "id": str(figure_id or filename_stem),
        "title": str(title or filename_stem),
        "status": "missing",
        "export_format": None,
        "file_name": None,
        "mime_type": None,
        "path": None,
        "source_hint": str(source_hint or ""),
        "note": "",
    }

    if fig is None:
        metadata["note"] = "No hay figura disponible para exportar en el contexto actual."
        return None, metadata

    if preferred_format == "png":
        try:
            width = export_options.get("width")
            height = export_options.get("height")
            scale = float(export_options.get("scale", 1.5) or 1.5)
            kwargs = {"format": "png", "scale": scale}
            if width:
                kwargs["width"] = int(width)
            if height:
                kwargs["height"] = int(height)
            png_bytes = _imagen_formal(fig).to_image(**kwargs)
            png_bytes = _optimize_png_bytes(png_bytes, max_dimension=int(export_options.get("max_dimension", 1600)))
            file_name = _safe_export_file_name(filename_stem, ".png")
            metadata.update({
                "status": "exported",
                "export_format": "png",
                "file_name": file_name,
                "mime_type": "image/png",
                "note": "Figura exportada como imagen PNG.",
            })
            return png_bytes, metadata
        except Exception:
            try:
                png_bytes = _export_plotly_figure_matplotlib(fig, title=title, export_options=export_options)
                png_bytes = _optimize_png_bytes(png_bytes, max_dimension=int(export_options.get("max_dimension", 1600)))
                file_name = _safe_export_file_name(filename_stem, ".png")
                metadata.update({
                    "status": "exported",
                    "export_format": "png",
                    "file_name": file_name,
                    "mime_type": "image/png",
                    "note": "Figura exportada como PNG estÃ¡tico mediante fallback compatible con matplotlib.",
                })
                return png_bytes, metadata
            except Exception as fallback_exc:
                metadata["note"] = (
                    "No fue posible generar PNG estÃ¡tico en este entorno; "
                    f"se exporta HTML editable. Detalle resumido: {fallback_exc}"
                )

    try:
        html_text = fig.to_html(full_html=True, include_plotlyjs="cdn")
        file_name = _safe_export_file_name(filename_stem, ".html")
        metadata.update({
            "status": "exported",
            "export_format": "html",
            "file_name": file_name,
            "mime_type": "text/html",
        })
        if not metadata["note"]:
            metadata["note"] = "Figura exportada como HTML interactivo."
        return html_text.encode("utf-8"), metadata
    except Exception as exc:
        metadata["status"] = "missing"
        metadata["note"] = _normalize_spanish_text(f"No fue posible exportar la figura. Detalle: {exc}")
        return None, metadata


def build_figure_export_bundle(figure_specs, base_folder="04_Figuras_mapas"):
    figure_specs = figure_specs or []
    files = {}
    artifacts = []

    for spec in figure_specs:
        content, metadata = export_plotly_figure_artifact(
            fig=spec.get("figure"),
            figure_id=spec.get("id"),
            title=spec.get("title"),
            stem=spec.get("stem"),
            source_hint=spec.get("source_hint", ""),
            preferred_format=spec.get("preferred_format", "png"),
        )

        if content and metadata.get("file_name"):
            metadata["path"] = f"{base_folder}/{metadata['file_name']}"
            files[metadata["path"]] = content
        artifacts.append(metadata)

    return {
        "files": files,
        "artifacts": artifacts,
    }


def _coerce_float_or_none(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        number = float(value)
    except Exception:
        return None
    if not np.isfinite(number):
        return None
    return number


def _build_site_map_figure(latitude, longitude, site_label="", source_label=""):
    lat = float(latitude)
    lon = float(longitude)
    span_lon = max(0.25, min(5.0, abs(lon) * 0.03))
    span_lat = max(0.25, min(5.0, abs(lat) * 0.03))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[lon],
            y=[lat],
            mode="markers+text",
            text=[site_label or "Sitio del proyecto"],
            textposition="top center",
            marker=dict(size=14, color="#d62728", line=dict(width=2, color="#7f0000")),
            hovertemplate=(
                f"{site_label or 'Sitio del proyecto'}<br>"
                "Longitud: %{x:.6f}<br>"
                "Latitud: %{y:.6f}<extra></extra>"
            ),
            name="Sitio",
        )
    )
    fig.add_vline(x=lon, line_width=1, line_dash="dot", line_color="#636363")
    fig.add_hline(y=lat, line_width=1, line_dash="dot", line_color="#636363")
    fig.add_annotation(
        x=lon,
        y=lat,
        yshift=-35,
        showarrow=False,
        text=f"({lat:.6f}, {lon:.6f})",
        font=dict(size=11, color="#333333"),
        bgcolor="rgba(255,255,255,0.85)",
    )
    if source_label:
        fig.add_annotation(
            x=1.0,
            y=1.12,
            xref="paper",
            yref="paper",
            xanchor="right",
            showarrow=False,
            text=f"Fuente/seleccion: {source_label}",
            font=dict(size=11, color="#555555"),
        )
    fig.update_layout(
        title="Mapa simplificado del sitio del proyecto",
        template="plotly_white",
        height=540,
        margin=dict(l=40, r=40, t=70, b=40),
        xaxis_title="Longitud (deg)",
        yaxis_title="Latitud (deg)",
    )
    fig.update_xaxes(range=[lon - span_lon, lon + span_lon], zeroline=False, showgrid=True)
    fig.update_yaxes(range=[lat - span_lat, lat + span_lat], zeroline=False, showgrid=True, scaleanchor="x", scaleratio=1)
    return fig


def _build_site_map_html(latitude, longitude, site_label="", source_label="", zoom_start=4, tiles="OpenStreetMap"):
    try:
        import folium
    except Exception:
        return None

    lat = float(latitude)
    lon = float(longitude)
    popup_lines = [site_label or "Sitio del proyecto", f"Lat: {lat:.6f}", f"Lon: {lon:.6f}"]
    if source_label:
        popup_lines.append(f"Fuente: {source_label}")

    site_map = folium.Map(
        location=[lat, lon],
        zoom_start=int(zoom_start or 4),
        tiles=str(tiles or "OpenStreetMap"),
        control_scale=True,
    )
    folium.CircleMarker(
        location=[lat, lon],
        radius=8,
        color="#d62728",
        fill=True,
        fill_color="#d62728",
        fill_opacity=0.9,
        tooltip=site_label or "Sitio del proyecto",
        popup="<br>".join(popup_lines),
    ).add_to(site_map)
    folium.Marker(
        location=[lat, lon],
        tooltip="Coordenadas del sitio",
        popup="<br>".join(popup_lines),
    ).add_to(site_map)
    folium.LatLngPopup().add_to(site_map)
    return site_map.get_root().render().encode("utf-8")


def _resolve_tile_template(tiles="OpenStreetMap"):
    value = str(tiles or "OpenStreetMap").strip()
    lower = value.lower()
    if "{z}" in value and "{x}" in value and "{y}" in value:
        return value
    known = {
        "openstreetmap": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "osm": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "cartodb positron": "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "cartodb dark_matter": "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "cartodb voyager": "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
    }
    return known.get(lower)


def _latlon_to_world_pixels(latitude, longitude, zoom):
    lat = max(min(float(latitude), 85.05112878), -85.05112878)
    lon = float(longitude)
    scale = 256 * (2 ** int(zoom))
    x = (lon + 180.0) / 360.0 * scale
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * scale
    return x, y


def _download_tile_image(tile_url):
    import requests
    from PIL import Image

    headers = {
        "User-Agent": "AlfaApp/1.0 (site-map-export)",
        "Accept": "image/png,image/*;q=0.8,*/*;q=0.5",
    }
    response = requests.get(tile_url, timeout=10, headers=headers)
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGB")


def _draw_tile_placeholder(image, x0, y0, label="Sin tile"):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    draw.rectangle([x0, y0, x0 + 255, y0 + 255], fill="#eef3f8", outline="#c4ced8", width=1)
    draw.line([x0, y0, x0 + 255, y0 + 255], fill="#c4ced8", width=1)
    draw.line([x0 + 255, y0, x0, y0 + 255], fill="#c4ced8", width=1)
    draw.text((x0 + 84, y0 + 118), label, fill="#607080")


def _build_site_map_phase2_tiles_png(latitude, longitude, site_label="", source_label="", start_date="", end_date="", zoom_start=9, tiles="OpenStreetMap"):
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError(f"Pillow no esta disponible para construir el snapshot cartografico: {exc}") from exc

    tile_template = _resolve_tile_template(tiles)
    if not tile_template:
        raise RuntimeError(f"No existe una plantilla de tiles soportada para '{tiles}'.")

    zoom = max(9, min(18, int(zoom_start or 9)))
    world_x, world_y = _latlon_to_world_pixels(latitude, longitude, zoom)
    center_tile_x = int(world_x // 256)
    center_tile_y = int(world_y // 256)
    tiles_per_axis = 5
    tile_radius = tiles_per_axis // 2
    max_tile = (2 ** zoom) - 1

    canvas = Image.new("RGB", (tiles_per_axis * 256, tiles_per_axis * 256), color="#eef3f8")
    fetched_any = False

    for ix, dx in enumerate(range(-tile_radius, tile_radius + 1)):
        for iy, dy in enumerate(range(-tile_radius, tile_radius + 1)):
            tile_x = (center_tile_x + dx) % (2 ** zoom)
            tile_y = center_tile_y + dy
            paste_x = ix * 256
            paste_y = iy * 256
            if tile_y < 0 or tile_y > max_tile:
                _draw_tile_placeholder(canvas, paste_x, paste_y, label="Fuera")
                continue
            tile_url = tile_template.format(z=zoom, x=tile_x, y=tile_y)
            try:
                tile_image = _download_tile_image(tile_url)
                canvas.paste(tile_image, (paste_x, paste_y))
                fetched_any = True
            except Exception:
                _draw_tile_placeholder(canvas, paste_x, paste_y)

    if not fetched_any:
        raise RuntimeError("No fue posible descargar tiles del mapa para el snapshot de Fase 2.")

    center_offset_x = int(round(world_x - center_tile_x * 256))
    center_offset_y = int(round(world_y - center_tile_y * 256))
    global_center_x = tile_radius * 256 + center_offset_x
    global_center_y = tile_radius * 256 + center_offset_y

    # Los tiles trabajan con zoom entero; abrimos ligeramente el recorte final
    # para aproximar visualmente un zoom intermedio entre 8 y 9.
    output_size = 608
    half = output_size // 2
    left = max(0, min(canvas.width - output_size, global_center_x - half))
    top = max(0, min(canvas.height - output_size, global_center_y - half))
    cropped = canvas.crop((left, top, left + output_size, top + output_size))

    draw = ImageDraw.Draw(cropped, "RGBA")
    px = global_center_x - left
    py = global_center_y - top

    draw.rounded_rectangle((12, 12, output_size - 12, output_size - 12), radius=12, outline="#d0d7de", width=2, fill=None)
    draw.ellipse((px - 12, py - 12, px + 12, py + 12), fill="#d62728", outline="white", width=3)
    draw.ellipse((px - 22, py - 22, px + 22, py + 22), outline=(214, 39, 40, 120), width=3)

    title = site_label or "Sitio del proyecto"
    subtitle_bits = []
    if source_label:
        subtitle_bits.append(source_label)
    if start_date or end_date:
        subtitle_bits.append(f"{start_date or 's/d'} a {end_date or 's/d'}")
    subtitle_bits.append(f"{tiles or 'OpenStreetMap'} | zoom local {zoom}")
    subtitle = " | ".join(subtitle_bits)
    coords = f"{float(latitude):.4f}, {float(longitude):.4f}"

    draw.rounded_rectangle((18, 18, output_size - 18, 84), radius=14, fill=(255, 255, 255, 228), outline=(210, 215, 223, 255), width=1)
    draw.text((32, 32), title, fill="#111827")
    draw.text((32, 54), subtitle, fill="#4b5563")
    draw.rounded_rectangle((18, output_size - 62, 244, output_size - 18), radius=12, fill=(255, 255, 255, 228), outline=(210, 215, 223, 255), width=1)
    draw.text((32, output_size - 46), f"Coordenadas: {coords}", fill="#374151")

    output = BytesIO()
    cropped.save(output, format="PNG")
    return output.getvalue()


def _build_site_map_static_png(latitude, longitude, site_label="", source_label="", start_date="", end_date="", zoom_start=4, tiles="OpenStreetMap"):
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError(f"Pillow no esta disponible para el fallback estatico del mapa: {exc}") from exc

    lat = float(latitude)
    lon = float(longitude)
    width = 768
    height = 768
    image = Image.new("RGB", (width, height), color="#dfead7")
    draw = ImageDraw.Draw(image, "RGBA")

    # Water-like zone
    draw.ellipse((-120, -40, 280, 220), fill=(191, 222, 245, 255))
    draw.ellipse((500, 520, 880, 860), fill=(191, 222, 245, 235))

    # Land texture / blocks
    patches = [
        (40, 120, 240, 250, "#d8d0b0"),
        (250, 80, 470, 220, "#c6ddb1"),
        (500, 100, 710, 250, "#d9c7a5"),
        (90, 340, 300, 520, "#cadfbb"),
        (330, 290, 560, 470, "#d6d0aa"),
        (540, 340, 730, 560, "#c7d9b8"),
        (110, 560, 330, 700, "#d7cba7"),
        (360, 540, 690, 720, "#d2e1c0"),
    ]
    for x0, y0, x1, y1, color in patches:
        draw.rounded_rectangle((x0, y0, x1, y1), radius=24, fill=color, outline=(182, 185, 168, 170), width=1)

    # Roads
    roads = [
        [(0, 210), (180, 250), (380, 280), (768, 360)],
        [(120, 0), (210, 140), (290, 300), (340, 768)],
        [(0, 610), (180, 560), (430, 520), (768, 470)],
        [(520, 0), (500, 160), (470, 330), (420, 768)],
    ]
    for road in roads:
        draw.line(road, fill=(247, 246, 242, 255), width=14)
        draw.line(road, fill=(183, 168, 135, 255), width=2)

    # Small route / local access road to point
    center_x = width // 2
    center_y = height // 2
    local_route = [(center_x - 170, center_y + 90), (center_x - 60, center_y + 35), (center_x + 10, center_y + 12)]
    draw.line(local_route, fill=(247, 246, 242, 255), width=10)
    draw.line(local_route, fill=(183, 168, 135, 255), width=2)

    # Marker
    draw.ellipse((center_x - 18, center_y - 18, center_x + 18, center_y + 18), fill=(214, 39, 40, 255), outline="white", width=4)
    draw.ellipse((center_x - 30, center_y - 30, center_x + 30, center_y + 30), outline=(214, 39, 40, 120), width=4)

    title = site_label or "Sitio del proyecto"
    subtitle_parts = []
    if source_label:
        subtitle_parts.append(source_label)
    if start_date or end_date:
        subtitle_parts.append(f"{start_date or 's/d'} a {end_date or 's/d'}")
    subtitle_parts.append(f"{tiles or 'OpenStreetMap'} | zoom {int(zoom_start or 4)}")
    subtitle = " | ".join(subtitle_parts)
    coords = f"{lat:.4f}, {lon:.4f}"

    draw.rounded_rectangle((20, 20, width - 20, 92), radius=14, fill=(255, 255, 255, 228), outline=(210, 215, 223, 255), width=1)
    draw.text((36, 36), title, fill="#111827")
    draw.text((36, 58), subtitle, fill="#4b5563")
    draw.rounded_rectangle((20, height - 70, 258, height - 20), radius=12, fill=(255, 255, 255, 228), outline=(210, 215, 223, 255), width=1)
    draw.text((36, height - 52), f"Coordenadas: {coords}", fill="#374151")
    draw.rounded_rectangle((width - 92, height - 96, width - 20, height - 20), radius=12, fill=(255, 255, 255, 228), outline=(210, 215, 223, 255), width=1)
    draw.line([(width - 56, height - 74), (width - 56, height - 36)], fill="#2f4858", width=4)
    draw.polygon([(width - 56, height - 86), (width - 66, height - 68), (width - 46, height - 68)], fill="#2f4858")
    draw.text((width - 61, height - 32), "N", fill="#2f4858")
    draw.rounded_rectangle((10, 10, width - 10, height - 10), radius=18, outline=(208, 215, 222, 255), width=2)

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _build_site_map_uploaded_png(config=None):
    config = config or {}
    encoded_image = str(config.get("site_map_image_b64") or "").strip()
    if not encoded_image:
        return None, ""

    try:
        raw_bytes = base64.b64decode(encoded_image)
    except Exception as exc:
        return None, f"No se pudo decodificar la imagen canonica cargada para el mapa del sitio. Detalle: {exc}"

    try:
        from PIL import Image, ImageOps
    except Exception as exc:
        return None, f"Pillow no esta disponible para normalizar la imagen canonica del mapa del sitio. Detalle: {exc}"

    try:
        with Image.open(BytesIO(raw_bytes)) as image:
            normalized = ImageOps.exif_transpose(image)
            if normalized.mode not in ["RGB", "RGBA"]:
                normalized = normalized.convert("RGBA" if "A" in normalized.getbands() else "RGB")
            output = BytesIO()
            normalized.save(output, format="PNG")
            return output.getvalue(), ""
    except Exception as exc:
        return None, f"No se pudo convertir la imagen canonica del mapa del sitio a PNG. Detalle: {exc}"


def build_site_map_bundle(config=None, base_folder="04_Figuras_mapas"):
    config = config or {}
    latitude = _coerce_float_or_none(config.get("nasa_lat"))
    longitude = _coerce_float_or_none(config.get("nasa_lon"))
    source_label = str(config.get("nasa_fuente") or "").strip()
    project_name = str(config.get("project_name") or "").strip()
    start_date = str(config.get("nasa_inicio") or "").strip()
    end_date = str(config.get("nasa_fin") or "").strip()
    zoom_start = max(9, int(float(config.get("site_map_zoom") or 9)))
    tiles = str(config.get("site_map_tiles") or "OpenStreetMap").strip() or "OpenStreetMap"
    uploaded_image_name = str(config.get("site_map_image_name") or "").strip()
    uploaded_image_mime = str(config.get("site_map_image_mime") or "").strip()

    site_files = {}
    site_artifact = {
        "id": "site_map",
        "title": "Mapa del sitio",
        "status": "missing",
        "export_format": None,
        "file_name": None,
        "mime_type": None,
        "path": None,
        "source_hint": "Ubicacion del sitio a partir de latitud/longitud persistidas en Fase 2.",
        "note": "",
    }
    extra_artifacts = []
    summary = {
        "available": False,
        "latitude": latitude,
        "longitude": longitude,
        "export_format": None,
        "canonical_source": None,
        "has_interactive_phase2_map": False,
        "note": "",
    }

    html_bytes = None
    if latitude is not None and longitude is not None:
        html_bytes = _build_site_map_html(
            latitude=latitude,
            longitude=longitude,
            site_label=project_name or "Sitio del proyecto",
            source_label=source_label,
            zoom_start=zoom_start,
            tiles=tiles,
        )
        if html_bytes:
            html_path = f"{base_folder}/mapa_sitio.html"
            site_files[html_path] = html_bytes
            extra_artifacts.append({
                "id": "site_map_interactive",
                "title": "Mapa del sitio (interactivo Fase 2)",
                "status": "exported",
                "export_format": "html",
                "file_name": "mapa_sitio.html",
                "mime_type": "text/html",
                "path": html_path,
                "source_hint": "Vista HTML alineada con la seleccion del sitio usada en Fase 2.",
                "note": "Mapa interactivo basado en folium/OpenStreetMap con la misma ubicacion seleccionada en Fase 2.",
            })
            summary["has_interactive_phase2_map"] = True

    uploaded_png, uploaded_error = _build_site_map_uploaded_png(config)
    if uploaded_png:
        png_path = f"{base_folder}/mapa_sitio.png"
        site_files[png_path] = uploaded_png
        site_artifact.update({
            "status": "exported",
            "export_format": "png",
            "file_name": "mapa_sitio.png",
            "mime_type": "image/png",
            "path": png_path,
            "source_hint": "Imagen canonica del mapa suministrada por el usuario desde Fase 2.",
            "note": (
                "Mapa del sitio exportado como PNG canonico a partir de una imagen suministrada por el usuario "
                "para representar la vista seleccionada en Fase 2."
            ),
        })
        summary.update({
            "available": True,
            "export_format": "png",
            "canonical_source": "user_supplied_phase2_image",
            "uploaded_image_name": uploaded_image_name,
            "uploaded_image_mime": uploaded_image_mime,
            "note": "Se uso la imagen canonica cargada por el usuario en Fase 2 como mapa principal del sitio.",
        })
    elif latitude is None or longitude is None:
        site_artifact["note"] = uploaded_error or "No se pudo generar el mapa del sitio porque faltan latitud y/o longitud en la configuracion actual."
        summary["note"] = uploaded_error or "No hay coordenadas persistidas suficientes para construir el mapa del sitio."
    else:
        try:
            static_png = _build_site_map_phase2_tiles_png(
                latitude=latitude,
                longitude=longitude,
                site_label=project_name or "Sitio del proyecto",
                source_label=source_label,
                start_date=start_date,
                end_date=end_date,
                zoom_start=zoom_start,
                tiles=tiles,
            )
            png_path = f"{base_folder}/mapa_sitio.png"
            site_files[png_path] = static_png
            site_artifact.update({
                "status": "exported",
                "export_format": "png",
                "file_name": "mapa_sitio.png",
                "mime_type": "image/png",
                "path": png_path,
                "note": (
                    "Mapa del sitio exportado como snapshot PNG usando la misma base cartografica, zoom y ubicacion persistida de Fase 2."
                ),
            })
            summary.update({
                "available": True,
                "export_format": "png",
                "canonical_source": "generated_phase2_tile_snapshot",
                "note": site_artifact["note"],
            })
        except Exception as exc:
            try:
                static_png = _build_site_map_static_png(
                    latitude=latitude,
                    longitude=longitude,
                    site_label=project_name or "Sitio del proyecto",
                    source_label=source_label,
                    start_date=start_date,
                    end_date=end_date,
                    zoom_start=zoom_start,
                    tiles=tiles,
                )
                png_path = f"{base_folder}/mapa_sitio.png"
                site_files[png_path] = static_png
                site_artifact.update({
                    "status": "exported",
                    "export_format": "png",
                    "file_name": "mapa_sitio.png",
                    "mime_type": "image/png",
                    "path": png_path,
                    "note": "Se uso un fallback grafico del mapa del sitio porque no fue posible descargar el snapshot cartografico de Fase 2.",
                })
                summary.update({
                    "available": True,
                    "export_format": "png",
                    "canonical_source": "generated_phase2_map_snapshot",
                    "note": site_artifact["note"],
                })
            except Exception:
                if html_bytes:
                    site_artifact.update({
                        "status": "exported",
                        "export_format": "html",
                        "file_name": "mapa_sitio.html",
                        "mime_type": "text/html",
                        "path": f"{base_folder}/mapa_sitio.html",
                        "note": "No fue posible generar el mapa PNG; se conserva el mapa HTML interactivo alineado con la seleccion del sitio de Fase 2.",
                    })
                    summary.update({
                        "available": True,
                        "export_format": "html",
                        "canonical_source": "phase2_interactive_html_only",
                        "note": "Solo se pudo conservar la vista HTML interactiva del mapa de Fase 2.",
                    })
                else:
                    site_fig = _build_site_map_figure(
                        latitude=latitude,
                        longitude=longitude,
                        site_label=project_name or "Sitio del proyecto",
                        source_label=source_label,
                    )
                    content, metadata = export_plotly_figure_artifact(
                        fig=site_fig,
                        figure_id="site_map",
                        title="Mapa del sitio",
                        stem="mapa_sitio",
                        source_hint=site_artifact["source_hint"],
                        preferred_format="html",
                    )
                    if content and metadata.get("file_name"):
                        metadata["path"] = f"{base_folder}/{metadata['file_name']}"
                        site_files[metadata["path"]] = content
                    metadata["note"] = (
                        "No fue posible generar ni el snapshot cartografico de Fase 2 ni el HTML folium; "
                        "se conserva un HTML simplificado basado en coordenadas."
                    )
                    site_artifact.update(metadata)
                    summary.update({
                        "available": site_artifact.get("status") == "exported",
                        "export_format": site_artifact.get("export_format"),
                        "canonical_source": "generated_phase2_coordinate_fallback" if site_artifact.get("status") == "exported" else None,
                        "note": (
                            "Se uso el fallback coordenado del mapa del sitio porque no hubo snapshot cartografico, "
                            "imagen canonica cargada por el usuario ni vista HTML de Fase 2 disponible."
                        ) if site_artifact.get("status") == "exported" else (
                            uploaded_error or f"No fue posible generar el mapa del sitio. Detalle resumido: {exc}"
                        ),
                    })
    return {
        "files": site_files,
        "artifacts": [site_artifact] + extra_artifacts,
        "summary": summary,
    }


def _build_probability_bins(vmax, bin_width):
    bins = np.arange(0.0, float(vmax) + float(bin_width), float(bin_width))
    if len(bins) == 0:
        bins = np.array([0.0, float(vmax)])
    if bins[-1] < float(vmax):
        bins = np.append(bins, float(vmax))
    return bins


def _build_probability_heatmap(df_rosa, vmax, bin_width):
    bins = _build_probability_bins(vmax=vmax, bin_width=bin_width)
    labels = [f"{bins[i]:.1f}-{bins[i+1]:.1f}" for i in range(len(bins) - 1)]
    matrix = []

    for sector in SECTOR_LABELS_16:
        sub = df_rosa.loc[df_rosa["Sector"] == sector, "WS_ANALISIS"].dropna().to_numpy(dtype=float)
        if len(sub) == 0:
            probs = np.zeros(len(bins) - 1)
        else:
            counts, _ = np.histogram(sub, bins=bins)
            probs = counts / counts.sum() * 100.0
        matrix.append(probs)

    fig = go.Figure(
        data=go.Heatmap(
            z=np.array(matrix),
            x=labels,
            y=SECTOR_LABELS_16,
            colorscale="YlOrRd",
            colorbar=dict(title="Probabilidad (%)"),
            hovertemplate=(
                "Sector: %{y}<br>"
                "Intervalo: %{x} m/s<br>"
                "Probabilidad: %{z:.2f}%"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title="Mapa visual de probabilidad de ocurrencia por sector",
        template="plotly_white",
        height=700,
        margin=dict(l=40, r=40, t=60, b=40),
        xaxis_title="Intervalo de velocidad (m/s)",
        yaxis_title="Sector",
    )
    return fig, bins


def _build_probability_sector_figure(df_sector, fila_sector, bins, mostrar_cdf, cut_in, nominal, cut_out):
    v = df_sector["WS_ANALISIS"].dropna().to_numpy(dtype=float)
    counts, edges = np.histogram(v, bins=bins)
    probs_real = counts / counts.sum() * 100.0 if counts.sum() > 0 else np.zeros_like(counts, dtype=float)
    centers = 0.5 * (edges[:-1] + edges[1:])

    k = float(fila_sector["k Weibull"])
    c_weib = float(fila_sector["c Weibull (m/s)"])
    c_ray = float(fila_sector["c Rayleigh (m/s)"])

    probs_weib = []
    probs_ray = []
    for i in range(len(edges) - 1):
        a = edges[i]
        b = edges[i + 1]
        probs_weib.append(weibull_interval_prob(a, b, k, c_weib) * 100.0 if np.isfinite(k) and np.isfinite(c_weib) else np.nan)
        probs_ray.append(rayleigh_interval_prob(a, b, c_ray) * 100.0 if np.isfinite(c_ray) else np.nan)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=centers,
            y=probs_real,
            name="Histograma real (%)",
            marker_color="#7fb3c4",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=centers, y=probs_weib, mode="lines+markers", name="Weibull (%)", line=dict(width=3, color="#1f77b4")),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=centers, y=probs_ray, mode="lines+markers", name="Rayleigh (%)", line=dict(width=3, color="#ff7f0e", dash="dash")),
        secondary_y=False,
    )

    if mostrar_cdf:
        xcdf = np.linspace(0.0, edges[-1], 400)
        fig.add_trace(go.Scatter(x=xcdf, y=weibull_cdf(xcdf, k, c_weib) * 100.0, mode="lines", name="CDF Weibull (%)", line=dict(width=2, color="#2ca02c")), secondary_y=True)
        fig.add_trace(go.Scatter(x=xcdf, y=rayleigh_cdf(xcdf, c_ray) * 100.0, mode="lines", name="CDF Rayleigh (%)", line=dict(width=2, color="#d62728", dash="dot")), secondary_y=True)

    for xline, name, color in [
        (cut_in, "Cut-in", "#2ca02c"),
        (nominal, "Nominal", "#9467bd"),
        (cut_out, "Cut-out", "#d62728"),
    ]:
        fig.add_vline(x=float(xline), line_width=2, line_dash="dot", line_color=color)
        fig.add_annotation(x=float(xline), y=1.02, yref="paper", text=name, showarrow=False, font=dict(color=color))

    fig.update_layout(
        title=f"Curva de probabilidad de ocurrencia - Sector {fila_sector['Sector']}",
        template="plotly_white",
        height=620,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        bargap=0.05,
    )
    fig.update_xaxes(title_text="Velocidad del viento (m/s)")
    fig.update_yaxes(title_text="Probabilidad por intervalo (%)", secondary_y=False)
    if mostrar_cdf:
        fig.update_yaxes(title_text="Probabilidad acumulada (%)", secondary_y=True, range=[0, 100])
    return fig


def _build_probability_interval_table(df_sector, fila_sector, vmax, bin_width):
    v = df_sector["WS_ANALISIS"].dropna().to_numpy(dtype=float)
    bins = _build_probability_bins(vmax=vmax, bin_width=bin_width)
    k = float(fila_sector["k Weibull"])
    c_weib = float(fila_sector["c Weibull (m/s)"])
    c_ray = float(fila_sector["c Rayleigh (m/s)"])
    filas = []
    total = len(v)
    for i in range(len(bins) - 1):
        a = bins[i]
        b = bins[i + 1]
        if total > 0:
            if i < len(bins) - 2:
                prob_real = 100.0 * np.sum((v >= a) & (v < b)) / total
            else:
                prob_real = 100.0 * np.sum((v >= a) & (v <= b)) / total
        else:
            prob_real = np.nan
        filas.append({
            "Rango": f"{a:.1f} - {b:.1f} m/s",
            "Probabilidad real (%)": prob_real,
            "Probabilidad Weibull (%)": weibull_interval_prob(a, b, k, c_weib) * 100.0 if np.isfinite(k) and np.isfinite(c_weib) else np.nan,
            "Probabilidad Rayleigh (%)": rayleigh_interval_prob(a, b, c_ray) * 100.0 if np.isfinite(c_ray) else np.nan,
        })
    return pd.DataFrame(filas)


def _build_probability_operation_table(df_sector, fila_sector, cut_in, nominal, cut_out):
    v = df_sector["WS_ANALISIS"].dropna().to_numpy(dtype=float)
    k = float(fila_sector["k Weibull"])
    c_weib = float(fila_sector["c Weibull (m/s)"])
    c_ray = float(fila_sector["c Rayleigh (m/s)"])
    rangos = [
        (0.0, cut_in, "Menor que cut-in"),
        (cut_in, nominal, "Entre cut-in y nominal"),
        (nominal, cut_out, "Entre nominal y cut-out"),
        (cut_out, max(cut_out + 20.0, cut_out * 1.5), "Mayor que cut-out"),
    ]
    filas = []
    total = len(v)
    for a, b, nombre in rangos:
        if total > 0:
            prob_real = 100.0 * np.sum(v >= a) / total if nombre == "Mayor que cut-out" else 100.0 * np.sum((v >= a) & (v < b)) / total
        else:
            prob_real = np.nan
        if nombre == "Mayor que cut-out":
            prob_weib = (1.0 - weibull_cdf(a, k, c_weib)) * 100.0 if np.isfinite(k) and np.isfinite(c_weib) else np.nan
            prob_ray = (1.0 - rayleigh_cdf(a, c_ray)) * 100.0 if np.isfinite(c_ray) else np.nan
        else:
            prob_weib = weibull_interval_prob(a, b, k, c_weib) * 100.0 if np.isfinite(k) and np.isfinite(c_weib) else np.nan
            prob_ray = rayleigh_interval_prob(a, b, c_ray) * 100.0 if np.isfinite(c_ray) else np.nan
        filas.append({
            "Zona de operacion": nombre,
            "Probabilidad real (%)": prob_real,
            "Probabilidad Weibull (%)": prob_weib,
            "Probabilidad Rayleigh (%)": prob_ray,
        })
    return pd.DataFrame(filas)


def build_probability_curve_bundle(df_nasa, config, df_curva_raw, roughness_options, base_folder="04_Figuras_mapas"):
    config = config or {}
    if df_nasa is None or len(df_nasa) == 0:
        return {"files": {}, "artifacts": [], "tables": {}, "summary": {"available": False, "note": "No hay datos horarios para reconstruir Fase 3.5."}}

    altura_deseada = float(config.get("perfil_hhub") or 80.0)
    modelo = config.get("f35_modelo", config.get("f3_modelo_altura", "Exponencial"))
    direccion_fuente = config.get("f35_direccion_fuente", config.get("f3_direccion_fuente", "WD50M"))
    roughness_label = config.get("f35_roughness_label", config.get("f3_roughness_label", "Grass / C?sped"))
    sector_preferido = config.get("f35_selected_sector", "N")
    vmax = float(config.get("f35_vmax", 25.0))
    bin_width = float(config.get("f35_bin_width", 0.5))
    mostrar_cdf = str(config.get("f35_show_cdf", "False")) == "True"

    df_curva_num = preparar_datos_curva(df_curva_raw)
    cut_in_inf, nominal_inf, cut_out_inf = inferir_puntos_operacion_curva(df_curva_num)
    cut_in = float(config.get("f35_cutin", cut_in_inf))
    nominal = float(config.get("f35_nominal", nominal_inf))
    cut_out = float(config.get("f35_cutout", cut_out_inf))

    try:
        df_analisis, meta = construir_serie_viento_analisis(
            df_nasa=df_nasa,
            modelo=modelo,
            altura_deseada=altura_deseada,
            roughness_label=roughness_label,
            direccion_fuente=direccion_fuente,
            roughness_options=roughness_options,
            output_speed_col="WS_ANALISIS",
            output_direction_col="WD_USADA",
        )
        df_rosa = preparar_datos_rosa(df_analisis, ws_col="WS_ANALISIS", wd_col="WD_USADA")
        if len(df_rosa) == 0:
            return {"files": {}, "artifacts": [], "tables": {}, "summary": {"available": False, "note": "No hay datos validos para la curva de probabilidad."}}
        resumen = resumir_sectores_rosa(df_rosa, ws_col="WS_ANALISIS").copy()
        sectores_disponibles = resumen.loc[resumen["Datos"] > 0, "Sector"].tolist()
        if not sectores_disponibles:
            return {"files": {}, "artifacts": [], "tables": {}, "summary": {"available": False, "note": "No hay sectores con datos suficientes para exportar la curva de probabilidad."}}
        sector_elegido = sector_preferido if sector_preferido in sectores_disponibles else sectores_disponibles[0]
        fila_sector = resumen[resumen["Sector"] == sector_elegido].iloc[0]
        df_sector = df_rosa[df_rosa["Sector"] == sector_elegido].copy()
        heatmap_fig, bins = _build_probability_heatmap(df_rosa, vmax=vmax, bin_width=bin_width)
        sector_fig = _build_probability_sector_figure(
            df_sector=df_sector,
            fila_sector=fila_sector,
            bins=bins,
            mostrar_cdf=mostrar_cdf,
            cut_in=cut_in,
            nominal=nominal,
            cut_out=cut_out,
        )
        export_bundle = build_figure_export_bundle(
            [
                {
                    "id": "probability_curves",
                    "title": f"Curva de probabilidad - Sector {sector_elegido}",
                    "stem": "curva_probabilidad_sector",
                    "figure": sector_fig,
                    "source_hint": "Curva de probabilidad reconstruida desde la configuracion persistida de Fase 3.5.",
                },
                {
                    "id": "probability_heatmap",
                    "title": "Mapa de probabilidad por sector",
                    "stem": "mapa_probabilidad_sectorial",
                    "figure": heatmap_fig,
                    "source_hint": "Heatmap de probabilidad por sector reconstruido desde Fase 3.5.",
                },
            ],
            base_folder=base_folder,
        )
        return {
            "files": export_bundle["files"],
            "artifacts": export_bundle["artifacts"],
            "tables": {
                "probability_intervals": _build_probability_interval_table(df_sector, fila_sector, vmax=vmax, bin_width=bin_width),
                "probability_operation": _build_probability_operation_table(df_sector, fila_sector, cut_in=cut_in, nominal=nominal, cut_out=cut_out),
                "probability_sector_summary": resumen[["Sector", "Frecuencia (%)", "Velocidad media (m/s)", "k Weibull", "c Weibull (m/s)"]].copy(),
            },
            "summary": {
                "available": True,
                "selected_sector": sector_elegido,
                "model": modelo,
                "note": meta.get("descripcion", ""),
            },
        }
    except Exception as exc:
        return {"files": {}, "artifacts": [], "tables": {}, "summary": {"available": False, "note": f"No fue posible reconstruir la exportacion de probabilidad: {exc}"}}


def _merge_export_bundle(target_bundle, export_bundle):
    target_bundle["files"].update(export_bundle.get("files", {}) or {})
    target_bundle["artifacts"].extend(export_bundle.get("artifacts", []) or [])


def _bundle_table(table_defs, key, df, title, columns=None, note="", file_name=""):
    if df is None or len(df) == 0:
        return
    df_visible = df.copy()
    df_visible.columns = [_normalize_spanish_text(col) for col in df_visible.columns]
    table_defs[key] = {
        "df": df_visible,
        "title": _normalize_spanish_text(title),
        "columns": [_normalize_spanish_text(col) for col in list(columns)] if columns else None,
        "note": _normalize_spanish_text(note),
        "max_rows": int(len(df_visible)),
        "file_name": file_name or "",
    }


def _figure_ref(figure_id, title, label, path, note="", caption=""):
    return {
        "id": figure_id,
        "title": _normalize_spanish_text(title),
        "label": label,
        "path": path,
        "note": _normalize_spanish_text(note),
        "caption": _normalize_spanish_text(caption or title),
    }


def _sector_slug(sector):
    return _slugify_figure_name(sector).replace("_", "")


def _build_phase2_profile_figures(df_nasa, config, roughness_options):
    if df_nasa is None or len(df_nasa) == 0:
        return None

    df_local = df_nasa.copy()
    for col in ["WS10M", "WS50M", "WD10M", "WD50M"]:
        if col in df_local.columns:
            df_local[col] = pd.to_numeric(df_local[col], errors="coerce")

    ws10 = pd.to_numeric(df_local.get("WS10M"), errors="coerce").dropna()
    ws50 = pd.to_numeric(df_local.get("WS50M"), errors="coerce").dropna()
    if len(ws10) == 0 or len(ws50) == 0:
        return None

    v10 = float(ws10.mean())
    v50 = float(ws50.mean())
    h1 = 10.0
    altura_deseada = float(config.get("perfil_hhub") or 80.0)
    alpha = float(calcular_alpha_desde_dos_alturas(v10, h1, v50, 50.0))
    u_star_a, z0_ajustada = ajustar_logaritmico_dos_puntos(v10, h1, v50, 50.0)
    u_star_a = float(u_star_a)
    z0_ajustada = float(z0_ajustada)

    v_exp_deseada = float(v10 * (altura_deseada / h1) ** alpha)
    v_log_a_deseada = float(velocidad_logaritmica_en_altura(u_star_a, altura_deseada, z0_ajustada))
    v_log_b_deseada = float((v_exp_deseada + v_log_a_deseada) / 2.0)

    altura_min = max(1.0, z0_ajustada + 0.1)
    altura_max = max(altura_deseada, 50.0)
    alturas = np.linspace(altura_min, altura_max, 120)

    df_exp = calcular_perfil_exponencial(v10, h1, alpha, alturas)
    df_log_a = calcular_perfil_logaritmico(u_star_a, z0_ajustada, alturas)
    df_log_b = df_exp.copy()
    df_log_b["Velocidad (m/s)"] = (df_exp["Velocidad (m/s)"].to_numpy(dtype=float) + df_log_a["Velocidad (m/s)"].to_numpy(dtype=float)) / 2.0

    puntos_medidos = [
        {"altura": 10.0, "velocidad": v10, "etiqueta": "Punto medido 10 m"},
        {"altura": 50.0, "velocidad": v50, "etiqueta": "Punto medido 50 m"},
    ]

    fig_exp = crear_grafica_perfil_individual(
        df_perfil=df_exp,
        titulo="Perfil exponencial ajustado con 10 m y 50 m",
        nombre_traza="Perfil exponencial",
        altura_objetivo=altura_deseada,
        v_objetivo=v_exp_deseada,
        color="#3366ff",
        yaxis_type="linear",
        puntos_medidos=puntos_medidos,
    )
    fig_log_a = crear_grafica_perfil_individual(
        df_perfil=df_log_a,
        titulo="Perfil logar?tmico modo A - ajustado con 10 m y 50 m",
        nombre_traza="Perfil logar?tmico A",
        altura_objetivo=altura_deseada,
        v_objetivo=v_log_a_deseada,
        color="#ff5533",
        dash="dash",
        yaxis_type="log",
        puntos_medidos=puntos_medidos,
    )
    fig_log_b = crear_grafica_perfil_individual(
        df_perfil=df_log_b,
        titulo="Promedio Log-Exp",
        nombre_traza="Promedio Log-Exp",
        altura_objetivo=altura_deseada,
        v_objetivo=v_log_b_deseada,
        color="#2ca25f",
        dash="dot",
        yaxis_type="log",
        puntos_medidos=puntos_medidos,
    )

    fig_compare_linear = go.Figure()
    for df_plot, name, color, dash in [
        (df_exp, "Exponencial (2 puntos)", "#3366ff", None),
        (df_log_a, "Logar?tmico A (2 puntos)", "#ff5533", "dash"),
        (df_log_b, "Promedio Log-Exp", "#2ca25f", "dot"),
    ]:
        fig_compare_linear.add_trace(
            go.Scatter(
                x=df_plot["Velocidad (m/s)"],
                y=df_plot["Altura (m)"],
                mode="lines",
                name=name,
                line=dict(width=3, color=color, dash=dash),
            )
        )
    fig_compare_linear.add_trace(
        go.Scatter(
            x=[p["velocidad"] for p in puntos_medidos],
            y=[p["altura"] for p in puntos_medidos],
            mode="markers",
            name="Puntos medidos",
            marker=dict(size=10, color="black"),
        )
    )
    fig_compare_linear.add_hline(y=float(altura_deseada), line_dash="dot", line_color="gray")
    fig_compare_linear.update_layout(
        title="Comparaci?n entre Exponencial, Log A y Promedio Log-Exp - escala normal",
        template="plotly_white",
        height=620,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis_title="Velocidad del viento (m/s)",
        yaxis_title="Altura (m)",
    )

    fig_compare_log = go.Figure(fig_compare_linear)
    fig_compare_log.update_layout(
        title="Comparaci?n entre Exponencial, Log A y Promedio Log-Exp - escala logar?tmica",
        yaxis_type="log",
    )

    return {
        "figures": {
            "phase2_hourly_series": crear_grafica_nasa_hourly(df_local),
            "phase2_profile_exponential": fig_exp,
            "phase2_profile_log_a": fig_log_a,
            "phase2_profile_log_b": fig_log_b,
            "phase2_compare_linear": fig_compare_linear,
            "phase2_compare_log": fig_compare_log,
        },
        "tables": {
            "phase2_hourly_summary": pd.DataFrame({
                "Campo": [
                    "Registros horarios",
                    "Fecha inicial",
                    "Fecha final",
                    "Promedio WS10M (m/s)",
                    "Promedio WS50M (m/s)",
                    "Promedio WD10M (?)",
                    "Promedio WD50M (?)",
                    "Fuente",
                ],
                "Valor": [
                    len(df_local),
                    str(df_local["timestamp"].min()) if "timestamp" in df_local.columns else "",
                    str(df_local["timestamp"].max()) if "timestamp" in df_local.columns else "",
                    v10,
                    v50,
                    float(pd.to_numeric(df_local.get("WD10M"), errors="coerce").dropna().mean()) if "WD10M" in df_local.columns else np.nan,
                    float(pd.to_numeric(df_local.get("WD50M"), errors="coerce").dropna().mean()) if "WD50M" in df_local.columns else np.nan,
                    str(config.get("nasa_fuente") or ""),
                ],
            }),
            "phase2_profile_comparison": pd.DataFrame({
                "Concepto": [
                    "Velocidad media a 10 m",
                    "Velocidad media a 50 m",
                    "Alpha exponencial (2 puntos)",
                    "u* modo A (2 puntos)",
                    "z0 modo A ajustada",
                    "Velocidad a altura deseada - Exponencial",
                    "Velocidad a altura deseada - Log A",
                    "Velocidad a altura deseada - Promedio Log-Exp",
                ],
                "Valor": [v10, v50, alpha, u_star_a, z0_ajustada, v_exp_deseada, v_log_a_deseada, v_log_b_deseada],
            }),
            "phase2_profiles_full": pd.DataFrame({
                "Altura (m)": df_exp["Altura (m)"],
                "Velocidad exp. (m/s)": df_exp["Velocidad (m/s)"],
                "Velocidad log A (m/s)": df_log_a["Velocidad (m/s)"],
                "Velocidad promedio log-exp (m/s)": df_log_b["Velocidad (m/s)"],
            }),
        },
    }


def _polar_16(radial=None):
    return dict(
        angularaxis=dict(direction="clockwise", rotation=90, tickmode="array",
                         tickvals=list(SECTOR_CENTERS_16), ticktext=SECTOR_LABELS_16),
        radialaxis=dict(angle=90, **(radial or {})),
    )


def _create_phase4_geometric_rose(df_geom):
    col_r = _col(df_geom, "Pérdida geométrica (%)")
    col_t = _col(df_geom, "Dirección centro (°)")
    fig = go.Figure()
    fig.add_trace(go.Barpolar(
        r=df_geom[col_r], theta=df_geom[col_t], width=[22.5] * len(df_geom),
        marker=dict(color=df_geom[col_r], colorscale="Reds", colorbar=dict(title="Pérdida geométrica (%)")),
        name="Pérdida geométrica",
    ))
    fig.update_layout(title="Análisis geométrico puro del arreglo", template="plotly_white", height=650,
                      margin=dict(l=40, r=40, t=60, b=40), polar=_polar_16())
    return fig


def _create_phase4_annual_rose(df_resumen):
    col_pond = _col(df_resumen, "Pérdida ponderada (%)")
    col_sector = _col(df_resumen, "Pérdida por estela (%)")
    col_t = _col(df_resumen, "Dirección centro (°)")
    fig = go.Figure()
    fig.add_trace(go.Barpolar(
        r=df_resumen[col_pond], theta=df_resumen[col_t], width=[22.5] * len(df_resumen),
        marker=dict(color=df_resumen[col_sector], colorscale="Blues", colorbar=dict(title="Pérdida del sector (%)")),
        name="Pérdida anual ponderada",
    ))
    fig.update_layout(title="Análisis anual ponderado", template="plotly_white", height=650,
                      margin=dict(l=40, r=40, t=60, b=40), polar=_polar_16())
    return fig


def _create_phase4_energy_bars(df_resumen):
    col_b = _col(df_resumen, "Energía bruta (MWh/año)")
    col_w = _col(df_resumen, "Energía con estela (MWh/año)")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_resumen["Sector"], y=df_resumen[col_b], name="Bruta"))
    fig.add_trace(go.Bar(x=df_resumen["Sector"], y=df_resumen[col_w], name="Con estela"))
    fig.update_layout(title="Energía anual por dirección", template="plotly_white", barmode="group", height=500,
                      margin=dict(l=40, r=40, t=60, b=40), xaxis_title="Sector", yaxis_title="Energía (MWh/año)")
    return fig


def _create_phase4_geom_vs_annual(df_geom, df_anual):
    col_g = _col(df_geom, "Pérdida geométrica (%)")
    col_a = _col(df_anual, "Pérdida ponderada (%)")
    df_plot = df_geom[["Sector", col_g]].merge(df_anual[["Sector", col_a]], on="Sector", how="left")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_plot["Sector"], y=df_plot[col_g], name="Geométrica (%)"))
    fig.add_trace(go.Bar(x=df_plot["Sector"], y=df_plot[col_a], name="Anual ponderada (%)"))
    fig.update_layout(title="Comparación: criticidad geométrica vs criticidad anual", template="plotly_white",
                      barmode="group", height=500, margin=dict(l=40, r=40, t=60, b=40),
                      xaxis_title="Sector", yaxis_title="Pérdida (%)")
    return fig


def _build_phase4_wind_analysis(df_nasa, config, roughness_options):
    if df_nasa is None or len(df_nasa) == 0:
        return None, None

    base_viento = str(config.get("f4_base_viento") or "50 m")
    altura_deseada = float(config.get("perfil_hhub") or 100.0)
    roughness_label = str(config.get("f4_roughness_label") or "Grass / Césped")
    direccion_altura = str(config.get("f4_dir_altura") or "WD50M")
    model_map = {
        "50 m": "50 m",
        "10 m": "10 m",
        "Altura deseada - Exponencial": "Exponencial",
        "Altura deseada - Log A (2 puntos)": "Log A (2 puntos)",
        "Altura deseada - Log B (z0 teórica)": "Promedio Log-Exp",
        "Altura deseada - Promedio Log-Exp": "Promedio Log-Exp",
    }
    modelo = model_map.get(base_viento, "50 m")
    return construir_serie_viento_analisis(
        df_nasa=df_nasa,
        modelo=modelo,
        altura_deseada=altura_deseada,
        roughness_label=roughness_label,
        direccion_fuente=direccion_altura,
        roughness_options=roughness_options,
        output_speed_col="WS_ANALISIS",
        output_direction_col="WD_ANALISIS",
    )


def _analyze_geometry_all_sectors(df_layout, curva_df, diametro, ct, kw, velocidad_ref):
    filas = []
    detalles = {}
    for sector, center_deg in zip(SECTOR_LABELS_16, SECTOR_CENTERS_16):
        df_dir = calcular_estelas_jensen_direccion(
            df_layout=df_layout,
            wind_speed=float(velocidad_ref),
            direction_deg=float(center_deg),
            diametro=diametro,
            ct=ct,
            kw=kw,
            curva_df=curva_df,
        )
        p_base = float(df_dir["potencia_base_W"].sum())
        p_wake = float(df_dir["potencia_wake_W"].sum())
        if p_base > 0:
            loss_pct = 100.0 * (1.0 - p_wake / p_base)
            eff_pct = 100.0 * p_wake / p_base
        else:
            loss_pct = 0.0
            eff_pct = 100.0
        filas.append({
            "Sector": sector,
            "Dirección centro (°)": float(center_deg),
            "Velocidad referencia (m/s)": float(velocidad_ref),
            "Potencia parque sin estela (W)": p_base,
            "Potencia parque con estela (W)": p_wake,
            "Pérdida geométrica (%)": loss_pct,
            "Eficiencia geométrica (%)": eff_pct,
            "Turbinas afectadas": int((df_dir["deficit_total"] > 1e-8).sum()),
        })
        detalles[sector] = df_dir.copy()
    return pd.DataFrame(filas), detalles


def analisis_anual_fase4(df_nasa, config, df_curva_raw, df_layout):
    """Análisis anual de estelas EXACTAMENTE como la Fase 4 (misma función y mismos parámetros).

    Devuelve (resumen_por_sector con energías, detalles_por_sector, pérdida_ponderada_pct,
    resumen_energía) o None si faltan layout o serie de viento.
    """
    if df_layout is None or len(df_layout) == 0 or df_nasa is None or len(df_nasa) == 0:
        return None
    import calculos_energia as energia_calc

    config = config or {}
    base_viento = str(config.get("f4_base_viento") or "50 m").strip()
    if base_viento == "Altura deseada - Log B (z0 teórica)":
        base_viento = "Altura deseada - Promedio Log-Exp"
    resultado = energia_calc.calcular_aep_autoritativa(
        df_layout=df_layout, df_nasa=df_nasa, df_curva_raw=df_curva_raw, base_viento=base_viento,
        modo_estadistico="Weibull", metodo_detalle="Weibull",
        altura_deseada=float(config.get("f4_altura_deseada") or config.get("perfil_hhub") or 100.0),
        roughness_label=str(config.get("f4_roughness_label") or "Grass / Césped"),
        direccion_fuente=str(config.get("f4_dir_altura") or "WD50M"),
        n_turbinas=len(df_layout), diametro=float(config.get("diametro") or 100.0),
        ct=float(config.get("f4_ct") or 0.80), kw=float(config.get("f4_kw") or 0.05),
        wake_mode="Automática desde Fase 4", wake_manual_pct=0.0, disp_pct=0.0, elec_pct=0.0, otras_pct=0.0,
    )
    resumen = resultado["wake_resumen"].copy()
    if len(resumen) == 0:
        return None
    energia = resultado["df_sector"][["Sector", "AEP bruta parque (MWh/año)", "AEP con estela (MWh/año)",
                                      "Pérdida estela energética (MWh/año)"]].rename(columns={
        "AEP bruta parque (MWh/año)": "Energía bruta (MWh/año)",
        "AEP con estela (MWh/año)": "Energía con estela (MWh/año)",
        "Pérdida estela energética (MWh/año)": "Pérdida energética (MWh/año)",
    })
    resumen = resumen.drop(columns=[c for c in energia.columns if c != "Sector" and c in resumen.columns]).merge(
        energia, on="Sector", how="left")
    return resumen, resultado["wake_detalles"], float(resultado["wake_perdida_ponderada"]), resultado["resumen"]


def build_indexed_appendix_annex_bundle(df_nasa, config, df_curva_raw, df_layout, roughness_options, base_folder="04_Figuras_mapas"):
    bundle = {
        "files": {},
        "artifacts": [],
        "tables": {},
        "appendix_specs": [],
        "summary": {"available": False, "phase_count": 0},
    }
    config = config or {}
    roughness_options = roughness_options or {}
    phase_count = 0

    try:
        df_curva_num = preparar_datos_curva(df_curva_raw)
        diametro = float(config.get("diametro") or 100.0)
        densidad = float(config.get("densidad") or 1.22)
        area = math.pi * (diametro / 2.0) ** 2
        df_cp = calcular_cp(df_curva_num, densidad, area)
        if len(df_cp) > 0:
            phase_count += 1
            phase1_export = build_figure_export_bundle([
                {
                    "id": "phase1_cp_curve",
                    "title": "Curva de potencia y coeficiente Cp",
                    "stem": "fase1_potencia_cp",
                    "figure": crear_grafica_curva(df_cp),
                    "source_hint": "Figura real reconstruida desde la curva de potencia persistida en Fase 1.",
                }
            ], base_folder=base_folder)
            _merge_export_bundle(bundle, phase1_export)
            _bundle_table(
                bundle["tables"],
                "phase1_cp_table",
                df_cp.rename(columns={
                    "Velocidad_num": "Velocidad (m/s)",
                    "Potencia_W": "Potencia (W)",
                    "P_viento_W": "Potencia del viento (W)",
                    "Cp": "Cp",
                })[["Velocidad (m/s)", "Potencia (W)", "Potencia del viento (W)", "Cp"]],
                title="Tabla completa de Cp calculado",
                columns=["Velocidad (m/s)", "Potencia (W)", "Potencia del viento (W)", "Cp"],
                note="Tabla derivada directamente de la curva de potencia guardada en Fase 1.",
                file_name="table_phase1_cp.tex",
            )
            bundle["appendix_specs"].append({
                "id": "anexo_fase1_curva_cp",
                "appendix_file_name": "appendix_fase1_curva_cp.tex",
                "title": "Anexo A - Fase 1 - Curva de potencia y Cp",
                "purpose": "Reunir la curva del aerogenerador y la tabla completa de Cp calculado a partir de los datos persistidos del rotor.",
                "notes": ["Si la curva cambia en Fase 1, este anexo se regenera autom?ticamente en el pack."],
                "table_keys": ["phase1_cp_table"],
                "figure_refs": [
                    _figure_ref(
                        "phase1_cp_curve",
                        "Curva de potencia y Cp",
                        "fig:fase1_potencia_cp",
                        "04_Figuras_mapas/fase1_potencia_cp.(png|html)",
                        caption="Curva de potencia y coeficiente Cp del aerogenerador",
                    )
                ],
            })
    except Exception:
        pass

    try:
        phase2_data = _build_phase2_profile_figures(df_nasa=df_nasa, config=config, roughness_options=roughness_options)
        if phase2_data:
            phase_count += 1
            phase2_specs = [
                ("phase2_hourly_series", "Serie horaria de velocidades", "fase2_serie_horaria"),
                ("phase2_profile_exponential", "Perfil exponencial", "fase2_perfil_exponencial"),
                ("phase2_profile_log_a", "Perfil logar?tmico modo A", "fase2_perfil_log_a"),
                ("phase2_profile_log_b", "Promedio Log-Exp", "fase2_promedio_log_exp"),
                ("phase2_compare_linear", "Comparaci?n de perfiles en escala normal", "fase2_comparacion_perfiles_normal"),
                ("phase2_compare_log", "Comparaci?n de perfiles en escala logar?tmica", "fase2_comparacion_perfiles_log"),
            ]
            phase2_export = build_figure_export_bundle(
                [
                    {
                        "id": figure_id,
                        "title": title,
                        "stem": stem,
                        "figure": phase2_data["figures"].get(figure_id),
                        "source_hint": "Figura real reconstruida desde los datos horarios y la configuraci?n persistida de Fase 2.",
                    }
                    for figure_id, title, stem in phase2_specs
                ],
                base_folder=base_folder,
            )
            _merge_export_bundle(bundle, phase2_export)
            _bundle_table(bundle["tables"], "phase2_hourly_summary", phase2_data["tables"]["phase2_hourly_summary"], "Resumen de datos horarios guardados", ["Campo", "Valor"], "Resumen derivado de la serie NASA POWER o CSV persistida en Fase 2.", "table_phase2_hourly_summary.tex")
            _bundle_table(bundle["tables"], "phase2_profile_comparison", phase2_data["tables"]["phase2_profile_comparison"], "Comparaci?n num?rica entre perfiles", ["Concepto", "Valor"], "Par?metros y velocidades de referencia usados para comparar los perfiles verticales.", "table_phase2_profile_comparison.tex")
            _bundle_table(bundle["tables"], "phase2_profiles_full", phase2_data["tables"]["phase2_profiles_full"], "Tabla completa de perfiles verticales", list(phase2_data["tables"]["phase2_profiles_full"].columns), "Tabla completa de velocidades para los perfiles exponencial, log A y Promedio Log-Exp.", "table_phase2_profiles_full.tex")
            bundle["appendix_specs"].append({
                "id": "anexo_fase2_series_perfiles",
                "appendix_file_name": "appendix_fase2_series_perfiles.tex",
                "title": "Anexo B - Fase 2 - Series y perfiles verticales",
                "purpose": "Agrupar la serie horaria, los perfiles verticales y la comparaci?n entre modos de extrapolaci?n usando la configuraci?n real del proyecto.",
                "notes": ["Las figuras y tablas se regeneran desde la base de datos horaria y los par?metros guardados en Fase 2."],
                "table_keys": ["phase2_hourly_summary", "phase2_profile_comparison", "phase2_profiles_full"],
                "figure_refs": [
                    _figure_ref("phase2_hourly_series", "Serie horaria de velocidades", "fig:fase2_serie_horaria", "04_Figuras_mapas/fase2_serie_horaria.(png|html)"),
                    _figure_ref("phase2_profile_exponential", "Perfil exponencial", "fig:fase2_perfil_exponencial", "04_Figuras_mapas/fase2_perfil_exponencial.(png|html)"),
                    _figure_ref("phase2_profile_log_a", "Perfil logar?tmico modo A", "fig:fase2_perfil_log_a", "04_Figuras_mapas/fase2_perfil_log_a.(png|html)"),
                    _figure_ref("phase2_profile_log_b", "Promedio Log-Exp", "fig:fase2_promedio_log_exp", "04_Figuras_mapas/fase2_promedio_log_exp.(png|html)"),
                    _figure_ref("phase2_compare_linear", "Comparaci?n entre perfiles en escala normal", "fig:fase2_comparacion_perfiles_normal", "04_Figuras_mapas/fase2_comparacion_perfiles_normal.(png|html)"),
                    _figure_ref("phase2_compare_log", "Comparaci?n entre perfiles en escala logar?tmica", "fig:fase2_comparacion_perfiles_log", "04_Figuras_mapas/fase2_comparacion_perfiles_log.(png|html)"),
                ],
            })
    except Exception:
        pass

    try:
        altura_deseada = float(config.get("perfil_hhub") or 80.0)
        modelo_f3 = config.get("f3_modelo_altura", "Exponencial")
        direccion_f3 = config.get("f3_direccion_fuente", "WD50M")
        roughness_f3 = config.get("f3_roughness_label", "Grass / C?sped")
        df_f3, _ = construir_serie_viento_analisis(
            df_nasa=df_nasa,
            modelo=modelo_f3,
            altura_deseada=altura_deseada,
            roughness_label=roughness_f3,
            direccion_fuente=direccion_f3,
            roughness_options=roughness_options,
            output_speed_col="WS_ALTURA",
            output_direction_col="WD_USADA",
        )
        df_rosa_f3 = preparar_datos_rosa(df_f3, ws_col="WS_ALTURA", wd_col="WD_USADA")
        resumen_f3 = resumir_sectores_rosa(df_rosa_f3, ws_col="WS_ALTURA").copy()
        if len(resumen_f3) > 0:
            phase_count += 1
            resumen_f3["Horas observadas (h)"] = resumen_f3["Datos"].astype(int)
            resumen_f3["Horas equivalentes anuales (h/a?o)"] = resumen_f3["Frecuencia (%)"] / 100.0 * 8760.0
            rose_fig = crear_rosa_vientos_16(resumen_f3)
            rose_fig.update_layout(title="Rosa de vientos para el modelo seleccionado")
            phase3_export_specs = [{
                "id": "wind_rose",
                "title": "Rosa de vientos",
                "stem": "rosa_vientos",
                "figure": rose_fig,
                "source_hint": "Rosa de vientos reconstruida desde la configuraci?n persistida de Fase 3.",
            }]
            for _, row in resumen_f3.iterrows():
                sector = str(row["Sector"])
                if int(row["Datos"]) <= 0:
                    continue
                slug = _sector_slug(sector)
                velocidades = df_rosa_f3.loc[df_rosa_f3["Sector"] == sector, "WS_ALTURA"].to_numpy()
                hist_fig = crear_histograma_sector_con_ajustes(
                    velocidades=velocidades,
                    sector=sector,
                    k_weibull=row["k Weibull"],
                    c_weibull=row["c Weibull (m/s)"],
                    c_rayleigh=row["c Rayleigh (m/s)"],
                )
                phase3_export_specs.append({
                    "id": f"phase3_hist_sector_{slug}",
                    "title": f"Histograma sectorial {sector}",
                    "stem": f"fase3_histograma_sector_{slug}",
                    "figure": hist_fig,
                    "source_hint": "Histograma real del sector reconstruido desde la rosa de vientos de Fase 3.",
                })
                detail_df = resumen_f3[resumen_f3["Sector"] == sector].copy()
                _bundle_table(bundle["tables"], f"phase3_sector_detail_{slug}", detail_df, f"Detalle sectorial - {sector}", list(detail_df.columns), "Detalle completo del sector con frecuencia, Weibull y Rayleigh.", f"table_phase3_sector_{slug}.tex")
                bundle["appendix_specs"].append({
                    "id": f"anexo_fase3_sector_{slug}",
                    "appendix_file_name": f"appendix_fase3_sector_{slug}.tex",
                    "title": f"Anexo C.{len(bundle['appendix_specs'])} - Fase 3 - Sector {sector}",
                    "purpose": f"Presentar el detalle sectorial y el histograma ajustado para la direcci?n {sector}.",
                    "notes": [],
                    "table_keys": [f"phase3_sector_detail_{slug}"],
                    "figure_refs": [_figure_ref(f"phase3_hist_sector_{slug}", f"Histograma sectorial {sector}", f"fig:fase3_hist_sector_{slug}", f"04_Figuras_mapas/fase3_histograma_sector_{slug}.(png|html)")],
                })
            phase3_export = build_figure_export_bundle(phase3_export_specs, base_folder=base_folder)
            _merge_export_bundle(bundle, phase3_export)
            _bundle_table(bundle["tables"], "phase3_sector_summary", resumen_f3, "Tabla sectorial completa", list(resumen_f3.columns), "Resumen completo de la rosa de vientos y del ajuste estad?stico por sector.", "table_phase3_sector_summary.tex")
            _bundle_table(bundle["tables"], "phase3_direction_index", resumen_f3[["Sector", "Centro (?)", "Datos", "Frecuencia (%)", "Horas equivalentes anuales (h/a?o)"]].copy(), "?ndice de las 16 direcciones", ["Sector", "Centro (?)", "Datos", "Frecuencia (%)", "Horas equivalentes anuales (h/a?o)"], "?ndice base para navegar el detalle direccional de Fase 3.", "table_phase3_direction_index.tex")
            bundle["appendix_specs"].append({
                "id": "anexo_fase3_recurso_direccional",
                "appendix_file_name": "appendix_fase3_00_recurso_direccional.tex",
                "title": "Anexo C - Fase 3 - Recurso direccional",
                "purpose": "Incluir la rosa de vientos, la tabla sectorial completa y el ?ndice de las 16 direcciones disponibles.",
                "notes": ["Los anexos sectoriales siguientes desarrollan las direcciones con datos observados."],
                "table_keys": ["phase3_direction_index", "phase3_sector_summary"],
                "figure_refs": [_figure_ref("wind_rose", "Rosa de vientos", "fig:rosa_vientos", "04_Figuras_mapas/rosa_vientos.(png|html)")],
            })
    except Exception:
        pass

    try:
        altura_deseada = float(config.get("perfil_hhub") or 80.0)
        modelo_f35 = config.get("f35_modelo", config.get("f3_modelo_altura", "Exponencial"))
        direccion_f35 = config.get("f35_direccion_fuente", config.get("f3_direccion_fuente", "WD50M"))
        roughness_f35 = config.get("f35_roughness_label", config.get("f3_roughness_label", "Grass / C?sped"))
        vmax = float(config.get("f35_vmax", 25.0))
        bin_width = float(config.get("f35_bin_width", 0.5))
        mostrar_cdf = str(config.get("f35_show_cdf", "False")) == "True"
        df_curva_num = preparar_datos_curva(df_curva_raw)
        cut_in_inf, nominal_inf, cut_out_inf = inferir_puntos_operacion_curva(df_curva_num)
        cut_in = float(config.get("f35_cutin", cut_in_inf))
        nominal = float(config.get("f35_nominal", nominal_inf))
        cut_out = float(config.get("f35_cutout", cut_out_inf))
        df_f35, meta_f35 = construir_serie_viento_analisis(
            df_nasa=df_nasa,
            modelo=modelo_f35,
            altura_deseada=altura_deseada,
            roughness_label=roughness_f35,
            direccion_fuente=direccion_f35,
            roughness_options=roughness_options,
            output_speed_col="WS_ANALISIS",
            output_direction_col="WD_USADA",
        )
        df_rosa_f35 = preparar_datos_rosa(df_f35, ws_col="WS_ANALISIS", wd_col="WD_USADA")
        resumen_f35 = resumir_sectores_rosa(df_rosa_f35, ws_col="WS_ANALISIS").copy()
        if len(resumen_f35) > 0:
            phase_count += 1
            resumen_f35["Horas observadas (h)"] = resumen_f35["Datos"].astype(int)
            resumen_f35["Horas equivalentes anuales (h/a?o)"] = resumen_f35["Frecuencia (%)"] / 100.0 * 8760.0
            heatmap_fig, bins = _build_probability_heatmap(df_rosa_f35, vmax=vmax, bin_width=bin_width)
            phase35_export_specs = [{
                "id": "probability_heatmap",
                "title": "Mapa visual de probabilidad por sector",
                "stem": "mapa_probabilidad_sectorial",
                "figure": heatmap_fig,
                "source_hint": "Mapa visual reconstruido desde Fase 3.5 para las 16 direcciones.",
            }]
            _bundle_table(bundle["tables"], "phase35_sector_summary", resumen_f35[["Sector", "Frecuencia (%)", "Velocidad media (m/s)", "k Weibull", "c Weibull (m/s)", "c Rayleigh (m/s)", "Horas equivalentes anuales (h/a?o)"]].copy(), "Resumen sectorial completo de probabilidad", ["Sector", "Frecuencia (%)", "Velocidad media (m/s)", "k Weibull", "c Weibull (m/s)", "c Rayleigh (m/s)", "Horas equivalentes anuales (h/a?o)"], meta_f35.get("descripcion", ""), "table_phase35_sector_summary.tex")
            _bundle_table(bundle["tables"], "phase35_direction_index", resumen_f35[["Sector", "Datos", "Frecuencia (%)", "Horas equivalentes anuales (h/a?o)"]].copy(), "?ndice de las 16 direcciones para Fase 3.5", ["Sector", "Datos", "Frecuencia (%)", "Horas equivalentes anuales (h/a?o)"], "Permite ubicar las curvas y tablas direccionales generadas para la Fase 3.5.", "table_phase35_direction_index.tex")
            for _, row in resumen_f35.iterrows():
                sector = str(row["Sector"])
                if int(row["Datos"]) <= 0:
                    continue
                slug = _sector_slug(sector)
                df_sector = df_rosa_f35[df_rosa_f35["Sector"] == sector].copy()
                sector_fig = _build_probability_sector_figure(df_sector=df_sector, fila_sector=row, bins=bins, mostrar_cdf=mostrar_cdf, cut_in=cut_in, nominal=nominal, cut_out=cut_out)
                phase35_export_specs.append({
                    "id": f"phase35_probability_curve_{slug}",
                    "title": f"Curva de probabilidad - Sector {sector}",
                    "stem": f"fase35_curva_probabilidad_{slug}",
                    "figure": sector_fig,
                    "source_hint": "Curva de probabilidad real reconstruida para cada una de las 16 direcciones.",
                })
                _bundle_table(bundle["tables"], f"phase35_intervals_{slug}", _build_probability_interval_table(df_sector, row, vmax=vmax, bin_width=bin_width), f"Tabla completa de probabilidad por intervalo - Sector {sector}", ["Rango", "Probabilidad real (%)", "Probabilidad Weibull (%)", "Probabilidad Rayleigh (%)"], "Tabla completa por intervalos para la direcci?n seleccionada del anexo.", f"table_phase35_intervals_{slug}.tex")
                _bundle_table(bundle["tables"], f"phase35_operation_{slug}", _build_probability_operation_table(df_sector, row, cut_in=cut_in, nominal=nominal, cut_out=cut_out), f"Probabilidades por zona de operaci?n - Sector {sector}", ["Zona de operacion", "Probabilidad real (%)", "Probabilidad Weibull (%)", "Probabilidad Rayleigh (%)"], "Tabla de zonas de operaci?n del aerogenerador para este sector.", f"table_phase35_operation_{slug}.tex")
                bundle["appendix_specs"].append({
                    "id": f"anexo_fase35_sector_{slug}",
                    "appendix_file_name": f"appendix_fase35_sector_{slug}.tex",
                    "title": f"Anexo D.{len(bundle['appendix_specs'])} - Fase 3.5 - Sector {sector}",
                    "purpose": f"Documentar la curva de probabilidad de ocurrencia y las tablas por intervalo para la direcci?n {sector}.",
                    "notes": [],
                    "table_keys": [f"phase35_intervals_{slug}", f"phase35_operation_{slug}"],
                    "figure_refs": [_figure_ref(f"phase35_probability_curve_{slug}", f"Curva de probabilidad - Sector {sector}", f"fig:fase35_curva_probabilidad_{slug}", f"04_Figuras_mapas/fase35_curva_probabilidad_{slug}.(png|html)")],
                })
            phase35_export = build_figure_export_bundle(phase35_export_specs, base_folder=base_folder)
            _merge_export_bundle(bundle, phase35_export)
            bundle["appendix_specs"].append({
                "id": "anexo_fase35_probabilidad_direccional",
                "appendix_file_name": "appendix_fase35_00_probabilidad_direccional.tex",
                "title": "Anexo D - Fase 3.5 - Probabilidad de ocurrencia por direcci?n",
                "purpose": "Reunir el mapa visual de las 16 direcciones, el resumen sectorial y el ?ndice de curvas generadas para cada sector con datos.",
                "notes": ["Las curvas por sector se anexan en archivos individuales para facilitar el trabajo en Overleaf."],
                "table_keys": ["phase35_direction_index", "phase35_sector_summary"],
                "figure_refs": [_figure_ref("probability_heatmap", "Mapa visual para las 16 direcciones", "fig:mapa_probabilidad_sectorial", "04_Figuras_mapas/mapa_probabilidad_sectorial.(png|html)")],
            })
    except Exception:
        pass

    try:
        analisis_f4 = analisis_anual_fase4(df_nasa, config, df_curva_raw, df_layout)
        if analisis_f4 is not None:
            resumen_anual, detalles_anual, _, _ = analisis_f4
            diametro = float(config.get("diametro") or 100.0)
            ct = float(config.get("f4_ct") or 0.80)
            kw = float(config.get("f4_kw") or 0.05)
            velocidad_geom = float(config.get("f4_geom_speed") or 8.0)
            phase_count += 1
            resumen_geom, detalles_geom = _analyze_geometry_all_sectors(df_layout=df_layout, curva_df=df_curva_raw, diametro=diametro, ct=ct, kw=kw, velocidad_ref=velocidad_geom)
            col_dir_geom = _col(resumen_geom, "Dirección centro (°)")
            col_dir_anual = _col(resumen_anual, "Dirección centro (°)")
            phase4_export = build_figure_export_bundle([
                {"id": "layout_wakes", "title": "Vista en planta del parque", "stem": "layout_parque", "figure": crear_figura_layout_parque(df_layout=df_layout, diametro=diametro, titulo="Vista en planta del parque"), "source_hint": "Vista en planta del layout guardado del parque."},
                {"id": "phase4_geometric_analysis", "title": "Análisis geométrico puro", "stem": "fase4_analisis_geometrico", "figure": _create_phase4_geometric_rose(resumen_geom), "source_hint": "Rosa geométrica de pérdidas de la Fase 4."},
                {"id": "phase4_annual_analysis", "title": "Análisis anual ponderado", "stem": "fase4_analisis_anual", "figure": _create_phase4_annual_rose(resumen_anual), "source_hint": "Rosa anual ponderada de la Fase 4."},
                {"id": "phase4_geom_vs_annual", "title": "Comparación criticidad geométrica vs anual", "stem": "fase4_geometrico_vs_anual", "figure": _create_phase4_geom_vs_annual(resumen_geom, resumen_anual), "source_hint": "Comparación entre criticidad geométrica y anual por dirección."},
                {"id": "phase4_energy_by_direction", "title": "Energía anual por dirección", "stem": "fase4_energia_direccional", "figure": _create_phase4_energy_bars(resumen_anual), "source_hint": "Energía anual bruta y con estela por dirección."},
            ], base_folder=base_folder)
            _bundle_table(bundle["tables"], "phase4_geom_summary", resumen_geom, "Análisis geométrico puro del arreglo", list(resumen_geom.columns), "Resumen geométrico por dirección con el modelo de estelas Jensen, como en la Fase 4.", "table_phase4_geom_summary.tex")
            _bundle_table(bundle["tables"], "phase4_annual_summary", resumen_anual, "Análisis anual ponderado", list(resumen_anual.columns), "Resumen anual ponderado con energía bruta, con estela y pérdida energética por dirección (mismo cálculo que la Fase 4).", "table_phase4_annual_summary.tex")
            cols_indice = [c for c in ["Sector", "Frecuencia (%)", "Horas equivalentes anuales (h/año)", "Pérdida por estela (%)", "Pérdida ponderada (%)"] if c in resumen_anual.columns]
            _bundle_table(bundle["tables"], "phase4_direction_index", resumen_anual[cols_indice].copy(), "Índice direccional del análisis de estelas", cols_indice, "Índice de sectores usado para navegar los anexos direccionales de Fase 4.", "table_phase4_direction_index.tex")
            cols_detalle = ["turbina_id", "x_m", "y_m", "velocidad_libre", "velocidad_efectiva", "deficit_total", "perdida_potencia_pct", "potencia_base_W", "potencia_wake_W"]
            for sector in SECTOR_LABELS_16:
                slug = _sector_slug(sector)
                df_detalle_geom = detalles_geom.get(sector, pd.DataFrame())
                df_detalle_anual = detalles_anual.get(sector, pd.DataFrame())
                fila_geom = resumen_geom[resumen_geom["Sector"] == sector]
                fila_anual = resumen_anual[resumen_anual["Sector"] == sector]
                if len(fila_geom) == 0 or len(fila_anual) == 0 or len(df_detalle_anual) == 0:
                    continue
                try:
                    fig_geom = crear_figura_direccion_estela(df_detalle=df_detalle_geom, sector=sector, direction_deg=float(fila_geom.iloc[0][col_dir_geom]), diametro=diametro)
                    fig_anual = crear_figura_direccion_estela(df_detalle=df_detalle_anual, sector=sector, direction_deg=float(fila_anual.iloc[0][col_dir_anual]), diametro=diametro)
                except Exception:
                    continue
                _merge_export_bundle(phase4_export, build_figure_export_bundle([
                    {"id": f"phase4_geom_detail_{slug}", "title": f"Detalle geométrico - Sector {sector}", "stem": f"fase4_detalle_geometrico_{slug}", "figure": fig_geom, "source_hint": "Detalle geométrico por dirección de la Fase 4."},
                    {"id": f"phase4_annual_detail_{slug}", "title": f"Detalle anual - Sector {sector}", "stem": f"fase4_detalle_anual_{slug}", "figure": fig_anual, "source_hint": "Detalle anual por dirección de la Fase 4."},
                ], base_folder=base_folder))
                if len(df_detalle_geom) > 0 and all(c in df_detalle_geom.columns for c in cols_detalle):
                    _bundle_table(bundle["tables"], f"phase4_geom_detail_table_{slug}", df_detalle_geom[cols_detalle].copy(), f"Detalle geométrico por turbina - Sector {sector}", cols_detalle, "Detalle geométrico por turbina para la dirección analizada.", f"table_phase4_geom_detail_{slug}.tex")
                if all(c in df_detalle_anual.columns for c in cols_detalle):
                    _bundle_table(bundle["tables"], f"phase4_annual_detail_table_{slug}", df_detalle_anual[cols_detalle].copy(), f"Detalle anual por turbina - Sector {sector}", cols_detalle, "Detalle anual ponderado por turbina para la dirección analizada.", f"table_phase4_annual_detail_{slug}.tex")
                bundle["appendix_specs"].append({
                    "id": f"anexo_fase4_sector_{slug}",
                    "appendix_file_name": f"appendix_fase4_sector_{slug}.tex",
                    "title": f"Anexo E.{len(bundle['appendix_specs'])} - Fase 4 - Dirección {sector}",
                    "purpose": f"Incluir el detalle geométrico y anual para la dirección {sector} del análisis de estelas.",
                    "notes": [],
                    "table_keys": [key for key in [f"phase4_geom_detail_table_{slug}", f"phase4_annual_detail_table_{slug}"] if key in bundle["tables"]],
                    "figure_refs": [
                        _figure_ref(f"phase4_geom_detail_{slug}", f"Detalle geométrico - Sector {sector}", f"fig:fase4_geom_detail_{slug}", f"04_Figuras_mapas/fase4_detalle_geometrico_{slug}.(png|html)"),
                        _figure_ref(f"phase4_annual_detail_{slug}", f"Detalle anual - Sector {sector}", f"fig:fase4_annual_detail_{slug}", f"04_Figuras_mapas/fase4_detalle_anual_{slug}.(png|html)"),
                    ],
                })
            _merge_export_bundle(bundle, phase4_export)
            bundle["appendix_specs"].append({
                "id": "anexo_fase4_estelas_y_arreglo",
                "appendix_file_name": "appendix_fase4_00_estelas_y_arreglo.tex",
                "title": "Anexo E - Fase 4 - Estelas y arreglo del parque",
                "purpose": "Concentrar la vista en planta del parque, el análisis geométrico, el análisis anual ponderado y la comparación entre criticidad geométrica y anual.",
                "notes": ["Las direcciones individuales se desarrollan en anexos posteriores para facilitar la navegación del pack."],
                "table_keys": ["phase4_direction_index", "phase4_geom_summary", "phase4_annual_summary"],
                "figure_refs": [
                    _figure_ref("layout_wakes", "Vista en planta del parque", "fig:layout_parque", "04_Figuras_mapas/layout_parque.(png|html)"),
                    _figure_ref("phase4_geometric_analysis", "Análisis geométrico puro", "fig:fase4_analisis_geometrico", "04_Figuras_mapas/fase4_analisis_geometrico.(png|html)"),
                    _figure_ref("phase4_annual_analysis", "Análisis anual ponderado", "fig:fase4_analisis_anual", "04_Figuras_mapas/fase4_analisis_anual.(png|html)"),
                    _figure_ref("phase4_geom_vs_annual", "Comparación criticidad geométrica vs criticidad anual", "fig:fase4_geometrico_vs_anual", "04_Figuras_mapas/fase4_geometrico_vs_anual.(png|html)"),
                    _figure_ref("phase4_energy_by_direction", "Energía anual por dirección", "fig:fase4_energia_direccional", "04_Figuras_mapas/fase4_energia_direccional.(png|html)"),
                ],
            })
    except Exception:
        pass

    bundle["summary"] = {
        "available": phase_count > 0,
        "phase_count": phase_count,
        "appendix_count": len(bundle["appendix_specs"]),
        "table_count": len(bundle["tables"]),
        "figure_count": len(bundle["artifacts"]),
    }
    return bundle

