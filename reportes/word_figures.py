# reportes/word_figures.py
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from PIL import Image, ImageChops
from docx.shared import Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

# ---------------------------------------------------------------------
# Configuración de exportación e inserción por familia visual
# ---------------------------------------------------------------------

WORD_FIGURE_SPECS: Dict[str, Dict[str, Any]] = {
    "phase1_power_cp":            {"w": 1500, "h": 950,  "scale": 2, "insert_cm": 15.8},
    "phase2_map":                 {"w": 1100, "h": 850,  "scale": 2, "insert_cm": 13.5},
    "phase2_time_series":         {"w": 1800, "h": 900,  "scale": 2, "insert_cm": 16.2},
    "phase2_profile":             {"w": 1100, "h": 1350, "scale": 2, "insert_cm": 11.8},
    "phase2_comparison":          {"w": 1450, "h": 980,  "scale": 2, "insert_cm": 15.4},

    "phase3_wind_rose":           {"w": 1250, "h": 1150, "scale": 2, "insert_cm": 13.8},
    "phase3_histogram":           {"w": 1450, "h": 980,  "scale": 2, "insert_cm": 15.4},
    "phase3_sector_table_image":  {"w": 1600, "h": 1000, "scale": 2, "insert_cm": 16.0},

    "phase35_probability_curve":  {"w": 1500, "h": 980,  "scale": 2, "insert_cm": 15.5},
    "phase35_heatmap":            {"w": 1550, "h": 950,  "scale": 2, "insert_cm": 16.0},

    "phase4_layout":              {"w": 1500, "h": 980,  "scale": 2, "insert_cm": 15.6},
    "phase4_polar":               {"w": 1300, "h": 1150, "scale": 2, "insert_cm": 14.0},
    "phase4_comparison":          {"w": 1500, "h": 950,  "scale": 2, "insert_cm": 15.5},
    "phase4_energy":              {"w": 1500, "h": 930,  "scale": 2, "insert_cm": 15.5},
    "phase4_direction_detail":    {"w": 1500, "h": 980,  "scale": 2, "insert_cm": 15.5},

    "phase5_loss_distribution":   {"w": 1250, "h": 1000, "scale": 2, "insert_cm": 13.8},
    "phase5_sector_chart":        {"w": 1500, "h": 930,  "scale": 2, "insert_cm": 15.5},

    "generic":                    {"w": 1400, "h": 900,  "scale": 2, "insert_cm": 15.0},
}


def _spec_for_family(family: str | None) -> Dict[str, Any]:
    if not family:
        return WORD_FIGURE_SPECS["generic"]
    return WORD_FIGURE_SPECS.get(family, WORD_FIGURE_SPECS["generic"])


# ---------------------------------------------------------------------
# Limpieza de márgenes blancos
# ---------------------------------------------------------------------

def trim_white_margins(image_path: str | Path, padding: int = 18) -> None:
    path = Path(image_path)
    img = Image.open(path).convert("RGB")
    bg = Image.new("RGB", img.size, "white")
    diff = ImageChops.difference(img, bg)

    # Intensificar diferencia para detectar mejor el borde útil
    diff = ImageChops.add(diff, diff, 2.0, -20)
    bbox = diff.getbbox()
    if not bbox:
        return

    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(img.width, bbox[2] + padding)
    bottom = min(img.height, bbox[3] + padding)

    cropped = img.crop((left, top, right, bottom))
    cropped.save(path, format="PNG", optimize=True)


# ---------------------------------------------------------------------
# Normalización visual de figuras Plotly para Word
# ---------------------------------------------------------------------

def prepare_plotly_figure_for_word(fig, family: str | None = None):
    """
    Devuelve una copia de la figura Plotly ajustada para exportación Word.
    """
    spec = _spec_for_family(family)
    fig2 = deepcopy(fig)

    common_layout = dict(
        autosize=False,
        width=spec["w"],
        height=spec["h"],
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(
            family="Calibri",
            size=16,
            color="#1f1f1f",
        ),
        margin=dict(l=80, r=40, t=70, b=75),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=12),
        ),
    )

    fig2.update_layout(**common_layout)

    # Ajustes finos por familia
    if family == "phase2_time_series":
        fig2.update_layout(
            margin=dict(l=75, r=35, t=70, b=65),
            xaxis=dict(tickangle=0, nticks=8, showgrid=True),
            yaxis=dict(showgrid=True),
        )

    elif family == "phase2_profile":
        fig2.update_layout(
            margin=dict(l=80, r=40, t=60, b=75),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.01,
                xanchor="center",
                x=0.5,
                font=dict(size=11),
            ),
        )

    elif family in {"phase2_comparison", "phase35_probability_curve", "phase4_comparison", "phase4_energy", "phase5_sector_chart"}:
        fig2.update_layout(
            margin=dict(l=80, r=40, t=60, b=70),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.01,
                xanchor="center",
                x=0.5,
                font=dict(size=11),
            ),
        )

    elif family in {"phase3_wind_rose", "phase4_polar", "phase5_loss_distribution"}:
        fig2.update_layout(
            margin=dict(l=50, r=50, t=60, b=50),
        )

    elif family in {"phase4_layout", "phase4_direction_detail"}:
        fig2.update_layout(
            margin=dict(l=70, r=40, t=60, b=65),
        )

    return fig2


# ---------------------------------------------------------------------
# Exportación Plotly -> PNG de alta calidad para Word
# ---------------------------------------------------------------------

def export_plotly_figure_for_word(fig, output_path: str | Path, family: str | None = None) -> str:
    """
    Exporta una figura Plotly a PNG de alta calidad para incrustar en Word.
    """
    output_path = str(output_path)
    spec = _spec_for_family(family)
    fig2 = prepare_plotly_figure_for_word(fig, family)

    fig2.write_image(
        output_path,
        format="png",
        width=spec["w"],
        height=spec["h"],
        scale=spec["scale"],
        engine="kaleido",
    )

    trim_white_margins(output_path, padding=16)
    return output_path


# ---------------------------------------------------------------------
# Inserción en Word
# ---------------------------------------------------------------------

def add_figure_to_docx(doc, image_path: str | Path, title: str, description: str = "", family: str | None = None):
    """
    Inserta imagen + título + descripción en un Document de python-docx.
    """
    spec = _spec_for_family(family)

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_title = p_title.add_run(title)
    r_title.bold = True

    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_img = p_img.add_run()
    r_img.add_picture(str(image_path), width=Cm(spec["insert_cm"]))

    if description:
        p_desc = doc.add_paragraph()
        p_desc.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        r_desc = p_desc.add_run(description)
        r_desc.italic = True