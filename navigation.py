import textwrap
from pathlib import Path

import streamlit as st
from streamlit.source_util import page_icon_and_name

from assets_loader import (
    load_global_css as _load_global_css_cached,
)
from assets_loader import (
    preload_all_phases_css as _preload_all_phases_css,
)


def _icon_svg(name: str, size: int = 18, color: str = "#2563eb") -> str:
    stroke = f'stroke="{color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" fill="none"'
    if name == "turbine":
        body = (
            f'<line x1="12" y1="11" x2="12" y2="20" {stroke}/>'
            f'<circle cx="12" cy="9" r="1.8" fill="{color}"/>'
            f'<path d="M12 9 L12 3 L13.8 7.4 Z" fill="{color}" opacity="0.95"/>'
            f'<path d="M12 9 L5 12.5 L9.7 11.9 Z" fill="{color}" opacity="0.9"/>'
            f'<path d="M12 9 L19 12.5 L14.3 11.9 Z" fill="{color}" opacity="0.9"/>'
        )
    elif name == "globe":
        body = (
            f'<circle cx="12" cy="12" r="8.2" {stroke}/>'
            f'<path d="M12 3.8c2.3 2.1 3.6 5 3.6 8.2s-1.3 6.1-3.6 8.2c-2.3-2.1-3.6-5-3.6-8.2s1.3-6.1 3.6-8.2Z" {stroke}/>'
            f'<path d="M4.7 9.2h14.6M4.7 14.8h14.6" {stroke}/>'
        )
    elif name == "curve":
        body = (
            f'<path d="M4 18.5H20" {stroke}/>'
            f'<path d="M5.2 17.8V5" {stroke}/>'
            f'<path d="M7 16c2.4-4.5 4.6-7 6.8-7 1.7 0 3.1 1.2 5.2 4" {stroke}/>'
            f'<circle cx="7" cy="16" r="1.3" fill="{color}"/>'
            f'<circle cx="13.8" cy="9" r="1.3" fill="{color}"/>'
            f'<circle cx="19" cy="13" r="1.3" fill="{color}"/>'
        )
    elif name == "chart":
        body = (
            f'<path d="M4 18.5H20" {stroke}/>'
            f'<path d="M5.2 17.8V5" {stroke}/>'
            f'<path d="M7 14l3-3 2.8 2.2 4.2-5.2" {stroke}/>'
            f'<circle cx="7" cy="14" r="1.2" fill="{color}"/>'
            f'<circle cx="10" cy="11" r="1.2" fill="{color}"/>'
            f'<circle cx="12.8" cy="13.2" r="1.2" fill="{color}"/>'
            f'<circle cx="17" cy="8" r="1.2" fill="{color}"/>'
        )
    elif name == "rotor":
        body = (
            f'<circle cx="12" cy="12" r="7.5" {stroke}/>'
            f'<path d="M12 12L12 5.2M12 12L6.4 15.2M12 12L17.6 15.2" {stroke}/>'
            f'<circle cx="12" cy="12" r="1.6" fill="{color}"/>'
        )
    elif name == "bolt":
        body = (
            f'<path d="M13.4 2.8 6.6 12h5.1L9.6 21.2 17.4 11h-5.1Z" fill="{color}" stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>'
        )
    elif name == "wind":
        body = (
            f'<path d="M4 9.5h9.8c1.8 0 2.9-.8 2.9-2.1 0-1.2-.8-2-1.9-2-.9 0-1.6.4-2 1.2" {stroke}/>'
            f'<path d="M4 14h12.2c1.7 0 2.8.8 2.8 2.1s-.9 2.2-2.1 2.2c-1 0-1.8-.5-2.2-1.3" {stroke}/>'
            f'<path d="M4 18.5h7.6c1.5 0 2.4.7 2.4 1.8 0 1.1-.8 1.9-1.8 1.9-.8 0-1.4-.3-1.8-1" {stroke}/>'
        )
    elif name == "profile":
        body = (
            f'<path d="M4 19h16" {stroke}/>'
            f'<path d="M6 19V8" {stroke}/>'
            f'<rect x="8" y="11" width="2.6" height="8" rx="1" fill="{color}"/>'
            f'<rect x="12" y="7" width="2.6" height="12" rx="1" fill="{color}" opacity="0.75"/>'
            f'<rect x="16" y="4.5" width="2.6" height="14.5" rx="1" fill="{color}" opacity="0.95"/>'
        )
    elif name == "upload":
        body = (
            f'<path d="M12 16V5.2" {stroke}/>'
            f'<path d="m8.2 8.9 3.8-3.9 3.8 3.9" {stroke}/>'
            f'<path d="M5 16.6v1.2A1.2 1.2 0 0 0 6.2 19h11.6a1.2 1.2 0 0 0 1.2-1.2v-1.2" {stroke}/>'
        )
    elif name == "cloud-upload":
        body = (
            f'<path d="M7.2 18.5H17.4C19.4 18.5 21 16.95 21 15.05C21 13.25 19.6 11.75 17.8 11.62C17.35 8.68 14.82 6.5 11.78 6.5C9.35 6.5 7.25 7.9 6.25 9.95C4.42 10.25 3 11.85 3 13.78C3 16.38 4.9 18.5 7.2 18.5Z" {stroke}/>'
            f'<path d="M12 16V10.5" {stroke}/>'
            f'<path d="M9.6 12.9 12 10.5 14.4 12.9" {stroke}/>'
        )
    elif name == "database":
        body = (
            f'<ellipse cx="12" cy="5.6" rx="6.6" ry="2.6" {stroke}/>'
            f'<path d="M5.4 5.6v6.7c0 1.4 3 2.6 6.6 2.6s6.6-1.2 6.6-2.6V5.6" {stroke}/>'
            f'<path d="M5.4 12.1c0 1.4 3 2.6 6.6 2.6s6.6-1.2 6.6-2.6" {stroke}/>'
            f'<path d="M5.4 16.1c0 1.4 3 2.6 6.6 2.6s6.6-1.2 6.6-2.6" {stroke}/>'
        )
    elif name == "database-stack":
        body = (
            f'<ellipse cx="12" cy="5.4" rx="6.8" ry="2.7" {stroke}/>'
            f'<path d="M5.2 5.4v9.4c0 1.55 3.05 2.8 6.8 2.8s6.8-1.25 6.8-2.8V5.4" {stroke}/>'
            f'<path d="M5.2 9.9c0 1.55 3.05 2.8 6.8 2.8s6.8-1.25 6.8-2.8" {stroke}/>'
            f'<path d="M5.2 14.4c0 1.55 3.05 2.8 6.8 2.8s6.8-1.25 6.8-2.8" {stroke}/>'
            f'<path d="M8.4 7.1c1 .45 2.2.68 3.6.68s2.6-.23 3.6-.68" {stroke}/>'
        )
    elif name == "database-records":
        body = (
            f'<ellipse cx="12" cy="5.5" rx="7" ry="3" {stroke}/>'
            f'<path d="M5 5.5v9c0 1.65 3.13 3 7 3s7-1.35 7-3v-9" {stroke}/>'
            f'<path d="M5 10c0 1.65 3.13 3 7 3s7-1.35 7-3" {stroke}/>'
            f'<path d="M5 14.5c0 1.65 3.13 3 7 3s7-1.35 7-3" {stroke}/>'
            f'<path d="M9 8.4c.9.25 1.9.38 3 .38s2.1-.13 3-.38" {stroke}/>'
        )
    elif name == "target":
        body = (
            f'<circle cx="12" cy="12" r="7.8" {stroke}/>'
            f'<circle cx="12" cy="12" r="3.4" {stroke}/>'
            f'<path d="M12 2.9v3M12 18.1v3M2.9 12h3M18.1 12h3" {stroke}/>'
            f'<circle cx="12" cy="12" r="1.2" fill="{color}"/>'
        )
    elif name == "target-height":
        body = (
            f'<path d="M7 19h10" {stroke}/>'
            f'<path d="M12 19V5" {stroke}/>'
            f'<path d="M9.6 7.4 12 5l2.4 2.4" {stroke}/>'
            f'<path d="M8.4 10.2h7.2" {stroke}/>'
            f'<path d="M8.4 14.6h7.2" {stroke}/>'
            f'<circle cx="12" cy="10.2" r="1" fill="{color}"/>'
        )
    elif name == "info":
        body = (
            f'<circle cx="12" cy="12" r="8.2" {stroke}/>'
            f'<path d="M12 10.4v5.1" {stroke}/>'
            f'<circle cx="12" cy="7.3" r="1.1" fill="{color}"/>'
        )
    elif name == "controls":
        body = (
            f'<path d="M4 7h16M4 12h16M4 17h16" {stroke}/>'
            f'<circle cx="9" cy="7" r="1.9" fill="{color}"/>'
            f'<circle cx="15" cy="12" r="1.9" fill="{color}" opacity="0.9"/>'
            f'<circle cx="11" cy="17" r="1.9" fill="{color}" opacity="0.85"/>'
        )
    elif name == "arrow":
        body = (
            f'<path d="M12 19V5.4" {stroke}/>'
            f'<path d="m7.9 9.5 4.1-4.1 4.1 4.1" {stroke}/>'
        )
    elif name == "sector":
        body = (
            f'<path d="M12 4a8 8 0 1 1-5.7 2.3" {stroke}/>'
            f'<path d="M12 12V4" {stroke}/>'
            f'<path d="M12 12 18.1 8.5" {stroke}/>'
            f'<circle cx="12" cy="12" r="1.4" fill="{color}"/>'
        )
    elif name == "sector-pie":
        body = (
            f'<circle cx="12" cy="12" r="8" {stroke}/>'
            f'<path d="M12 12V4" {stroke}/>'
            f'<path d="M12 12h8" {stroke}/>'
            f'<path d="M12 4a8 8 0 0 1 8 8h-8Z" fill="{color}" opacity="0.18"/>'
            f'<path d="M12 4a8 8 0 0 1 8 8" {stroke}/>'
        )
    elif name == "pie-sectors":
        body = (
            f'<circle cx="12" cy="12" r="7.6" {stroke}/>'
            f'<path d="M12 12V4.4" {stroke}/>'
            f'<path d="M12 12 18.6 15.8" {stroke}/>'
            f'<path d="M12 4.4a7.6 7.6 0 0 1 6.6 11.4L12 12Z" fill="{color}" opacity="0.18"/>'
            f'<path d="M12 4.4a7.6 7.6 0 0 1 6.6 11.4" {stroke}/>'
            f'<circle cx="12" cy="12" r="1.15" fill="{color}"/>'
        )
    elif name == "sigma":
        body = (
            f'<path d="M17.6 5.2H8.1l5 6.8-5 6.8h9.5" {stroke}/>'
        )
    elif name == "trending-down":
        body = (
            f'<path d="M4.5 7.2v11.3h15" {stroke}/>'
            f'<path d="m6.6 9.2 4.1 4.1 3.4-3.4 3.3 3.3" {stroke}/>'
            f'<path d="M17.4 13.2h-3.3v-3.3" {stroke}/>'
        )
    elif name == "activity":
        body = (
            f'<path d="M3.8 12h3.3l2.2-4.1 4.1 8.1 2.2-4h4.6" {stroke}/>'
        )
    elif name == "map-pin":
        body = (
            f'<path d="M12 20.2s5.4-5.4 5.4-9.2a5.4 5.4 0 1 0-10.8 0c0 3.8 5.4 9.2 5.4 9.2Z" {stroke}/>'
            f'<circle cx="12" cy="10.8" r="2.1" {stroke}/>'
        )
    elif name == "bar-chart-2":
        body = (
            f'<path d="M4 19h16" {stroke}/>'
            f'<rect x="6.2" y="11.2" width="2.6" height="5.8" rx="0.9" fill="{color}"/>'
            f'<rect x="10.7" y="7.8" width="2.6" height="9.2" rx="0.9" fill="{color}" opacity="0.82"/>'
            f'<rect x="15.2" y="4.8" width="2.6" height="12.2" rx="0.9" fill="{color}" opacity="0.96"/>'
        )
    elif name == "clock":
        body = (
            f'<circle cx="12" cy="12" r="8.2" {stroke}/>'
            f'<path d="M12 7.4v5.1l3.4 2" {stroke}/>'
        )
    elif name == "table":
        body = (
            f'<rect x="4.5" y="5.5" width="15" height="13" rx="2" {stroke}/>'
            f'<path d="M4.5 9.5h15M9.3 5.5v13M14.2 5.5v13" {stroke}/>'
            f'<path d="M6.8 13h1M11.6 13h1M16.5 13h1M6.8 16h1M11.6 16h1M16.5 16h1" {stroke}/>'
        )
    elif name == "probability-table":
        body = (
            f'<rect x="4.4" y="5" width="15.2" height="14" rx="2.2" {stroke}/>'
            f'<path d="M4.4 9h15.2" {stroke}/>'
            f'<path d="M9 9v10" {stroke}/>'
            f'<path d="M14.2 9v10" {stroke}/>'
            f'<path d="M6.7 16.5h1.1" {stroke}/>'
            f'<path d="M11.2 15v1.5" {stroke}/>'
            f'<path d="M16 12.8v3.7" {stroke}/>'
            f'<path d="M6.8 12.7c2.5 1.3 5.1 1 7.2-.2 1.3-.8 2.4-1.1 3.3-.8" {stroke}/>'
        )
    elif name == "operation-table":
        body = (
            f'<rect x="4.5" y="5.2" width="15" height="13.6" rx="2.2" {stroke}/>'
            f'<path d="M4.5 9.2h15" {stroke}/>'
            f'<path d="M9 9.2v9.6" {stroke}/>'
            f'<path d="M14.4 9.2v9.6" {stroke}/>'
            f'<circle cx="12" cy="14" r="2.1" {stroke}/>'
            f'<path d="M12 11.9V9.9" {stroke}/>'
            f'<path d="M12 14l1.8 1.1" {stroke}/>'
            f'<path d="M12 14l-1.8 1.1" {stroke}/>'
        )
    elif name == "hourly-data-table":
        body = (
            f'<rect x="4.4" y="5.4" width="14.8" height="13.2" rx="2.2" {stroke}/>'
            f'<path d="M4.4 9.4h14.8" {stroke}/>'
            f'<path d="M8.7 9.4v9.2" {stroke}/>'
            f'<path d="M6.5 12.6h.1M6.5 15.8h.1M11.3 12.6h1.7M11.3 15.8h1.7" {stroke}/>'
            f'<circle cx="17" cy="7" r="3" fill="white" stroke="{color}" stroke-width="1.7"/>'
            f'<path d="M17 5.4v1.8l1.2.7" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
        )
    elif name == "table-intervals":
        body = (
            f'<rect x="4.2" y="4.8" width="15.6" height="14.4" rx="2.2" {stroke}/>'
            f'<path d="M4.2 8.9h15.6" {stroke}/>'
            f'<path d="M8.4 8.9v10.3" {stroke}/>'
            f'<path d="M13.4 8.9v10.3" {stroke}/>'
            f'<path d="M4.2 12.3h15.6" {stroke}/>'
            f'<path d="M4.2 15.7h15.6" {stroke}/>'
            f'<path d="M6.1 17.4h2.1" {stroke}/>'
            f'<path d="M10.1 14.1h2.4" {stroke}/>'
            f'<path d="M15 10.8h2.7" {stroke}/>'
        )
    elif name == "table-zones":
        body = (
            f'<rect x="4.2" y="4.8" width="15.6" height="14.4" rx="2.2" {stroke}/>'
            f'<path d="M4.2 8.9h15.6" {stroke}/>'
            f'<path d="M8.7 8.9v10.3" {stroke}/>'
            f'<path d="M14.1 8.9v10.3" {stroke}/>'
            f'<path d="M4.2 13.6h15.6" {stroke}/>'
            f'<path d="M14.1 13.6h5.7v5.6h-5.7Z" fill="{color}" opacity="0.16"/>'
            f'<path d="M15.9 16.4h2.1" {stroke}/>'
        )
    elif name == "table-hourly":
        body = (
            f'<rect x="4.2" y="5.2" width="14.8" height="13.6" rx="2.2" {stroke}/>'
            f'<path d="M4.2 9.2H19" {stroke}/>'
            f'<path d="M8.2 9.2v9.6" {stroke}/>'
            f'<path d="M12.6 9.2v9.6" {stroke}/>'
            f'<path d="M6.2 12.5h.1M10.3 12.5h.1M6.2 15.8h.1M10.3 15.8h.1" {stroke}/>'
            f'<circle cx="17" cy="6.8" r="3.2" fill="white" stroke="{color}" stroke-width="1.8"/>'
            f'<path d="M17 5.1v1.9l1.3.7" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
        )
    elif name == "table-grid":
        body = (
            f'<rect x="5" y="4.5" width="14" height="15" rx="2.2" {stroke}/>'
            f'<path d="M5 8.5H19" {stroke}/>'
            f'<path d="M9.5 8.5V19.5" {stroke}/>'
            f'<path d="M14.5 8.5V19.5" {stroke}/>'
            f'<path d="M5 12.2H19" {stroke}/>'
            f'<path d="M5 15.8H19" {stroke}/>'
        )
    elif name == "columns-3":
        body = (
            f'<rect x="5" y="5" width="14" height="14" rx="2.2" {stroke}/>'
            f'<path d="M9 5V19" {stroke}/>'
            f'<path d="M15 5V19" {stroke}/>'
        )
    elif name == "calendar-grid":
        body = (
            f'<rect x="4.8" y="6.2" width="14.4" height="13" rx="2.2" {stroke}/>'
            f'<path d="M8 4.5V8" {stroke}/>'
            f'<path d="M16 4.5V8" {stroke}/>'
            f'<path d="M4.8 10H19.2" {stroke}/>'
            f'<path d="M8.2 13.2H8.25" {stroke}/>'
            f'<path d="M12 13.2H12.05" {stroke}/>'
            f'<path d="M15.8 13.2H15.85" {stroke}/>'
            f'<path d="M8.2 16.2H8.25" {stroke}/>'
            f'<path d="M12 16.2H12.05" {stroke}/>'
        )
    elif name == "wind-10m":
        body = (
            f'<path d="M5 19.2h7" {stroke}/>'
            f'<path d="M8.2 19.2V10.4" {stroke}/>'
            f'<path d="M6 11h9.3c1.3 0 2.1-.6 2.1-1.6 0-.9-.7-1.5-1.6-1.5-.7 0-1.2.3-1.6.9" {stroke}/>'
            f'<path d="M6 14.4h10.9c1.2 0 1.9.6 1.9 1.5s-.7 1.6-1.6 1.6c-.7 0-1.3-.3-1.6-.9" {stroke}/>'
            f'<path d="M10.1 16.9H6" {stroke}/>'
            f'<circle cx="8.2" cy="10.4" r="1" fill="{color}"/>'
        )
    elif name == "wind-50m":
        body = (
            f'<path d="M5 19.2h7" {stroke}/>'
            f'<path d="M8.2 19.2V6.2" {stroke}/>'
            f'<path d="M6 7.2h9.5c1.5 0 2.4-.7 2.4-1.8 0-1-.7-1.7-1.8-1.7-.8 0-1.4.4-1.8 1" {stroke}/>'
            f'<path d="M6 12.3h11.5c1.3 0 2.1.6 2.1 1.7 0 1-.7 1.7-1.7 1.7-.8 0-1.4-.4-1.8-1" {stroke}/>'
            f'<path d="M11.4 17.2H6" {stroke}/>'
            f'<circle cx="8.2" cy="6.2" r="1" fill="{color}"/>'
        )
    elif name == "alpha-profile":
        body = (
            f'<path d="M5 19h14" {stroke}/>'
            f'<path d="M6 17.3 18 6.8" {stroke}/>'
            f'<circle cx="8.2" cy="15.4" r="1.15" fill="{color}"/>'
            f'<circle cx="15.8" cy="8.7" r="1.15" fill="{color}"/>'
            f'<path d="M7.2 10.1c1.7-2.2 3.8-2.2 5.4 0 1.6 2.2 3.6 2.2 5.2 0" {stroke}/>'
        )
    elif name == "friction-velocity":
        body = (
            f'<path d="M4.5 18.4h15" {stroke}/>'
            f'<path d="M5.2 15.8l1.4-1.1 1.4 1.1 1.4-1.1 1.4 1.1 1.4-1.1 1.4 1.1 1.4-1.1 1.4 1.1 1.4-1.1 1.4 1.1" {stroke}/>'
            f'<path d="M6 7.4h8.7c1.5 0 2.4-.7 2.4-1.8 0-1-.7-1.7-1.8-1.7-.8 0-1.4.4-1.8 1" {stroke}/>'
            f'<path d="M6 11.2h10.8c1.3 0 2.1.6 2.1 1.6s-.7 1.7-1.7 1.7c-.8 0-1.4-.4-1.8-1" {stroke}/>'
            f'<path d="M10.2 17.6c1.2-2 2.6-3 4.4-3.4" {stroke}/>'
            f'<path d="m14.2 12.5.4 1.7-1.8-.2" {stroke}/>'
            f'<circle cx="10.2" cy="17.6" r="1" fill="{color}"/>'
        )
    elif name == "roughness-z0":
        body = (
            f'<path d="M4.5 18.5h15" {stroke}/>'
            f'<path d="M5.2 15.8l1.4-1.1 1.4 1.1 1.4-1.1 1.4 1.1 1.4-1.1 1.4 1.1 1.4-1.1 1.4 1.1 1.4-1.1 1.4 1.1" {stroke}/>'
            f'<path d="M12 18.2V8.1" {stroke}/>'
            f'<path d="M9.8 10.3 12 8.1l2.2 2.2" {stroke}/>'
            f'<circle cx="12" cy="8.1" r="1" fill="{color}"/>'
        )
    elif name == "profile-average":
        body = (
            f'<path d="M5.2 18.8h14" {stroke}/>'
            f'<path d="M5.2 18.8V5.2" {stroke}/>'
            f'<path d="M6.8 17.4c4.9-.5 8.1-3.6 10.4-10.7" {stroke}/>'
            f'<path d="M6.8 15.5c2.1-5.2 5.8-7.7 10.4-7.9" {stroke}/>'
            f'<path d="M6.8 16.5c3.3-4.8 6.8-6.9 10.4-8.4" stroke="{color}" stroke-width="2.55" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
            f'<circle cx="12.2" cy="12.1" r="1.15" fill="{color}"/>'
            f'<path d="M10.5 12.1h3.4" {stroke}/>'
        )
    elif name == "log-exp-average":
        body = (
            f'<path d="M4 19V5" {stroke}/>'
            f'<path d="M4 19H20" {stroke}/>'
            f'<path d="M6 16.8C8.2 13 10.7 10.8 14.5 9.8C16.4 9.3 18 8.7 19.5 7.2" {stroke}/>'
            f'<path d="M6 17.3C8.8 16 11.6 14 14.2 11.2C16.2 9 17.8 6.8 19.2 4.8" {stroke}/>'
            f'<path d="M6 17C8.6 14.6 11.2 12.4 14.4 10.5C16.3 9.35 17.8 8.25 19.35 6.1" stroke="{color}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
            f'<circle cx="13.9" cy="10.7" r="1.15" fill="{color}"/>'
        )
    elif name == "model-combo":
        body = (
            f'<path d="M5 19h14" {stroke}/>'
            f'<path d="M6 8.1c3.7 0 5.7 1.7 7.9 5.1" {stroke}/>'
            f'<path d="M6 16.4c3.7 0 5.7-1.7 7.9-5.1" {stroke}/>'
            f'<path d="M13.8 12.2c1.7 2.5 3.1 3.9 4.9 4.4" {stroke}/>'
            f'<path d="M13.8 12.2c1.7-2.5 3.1-3.9 4.9-4.4" {stroke}/>'
            f'<circle cx="13.8" cy="12.2" r="1.2" fill="{color}"/>'
        )
    elif name == "exp-profile":
        body = (
            f'<path d="M5.2 18.8h14" {stroke}/>'
            f'<path d="M5.2 18.8V5.2" {stroke}/>'
            f'<path d="M6.8 17.4c4.9-.5 8.2-3.8 10.5-10.6" stroke="{color}" stroke-width="2.35" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
            f'<path d="m15.1 7.2 2.2-.4-.2 2.2" {stroke}/>'
            f'<circle cx="8.3" cy="16.9" r=".95" fill="{color}"/>'
            f'<circle cx="12.6" cy="13.4" r=".95" fill="{color}"/>'
            f'<circle cx="16.5" cy="8.6" r=".95" fill="{color}"/>'
        )
    elif name == "log-profile":
        body = (
            f'<path d="M5.2 18.8h14" {stroke}/>'
            f'<path d="M5.2 18.8V5.2" {stroke}/>'
            f'<path d="M6.8 17.2c1.4-5.8 5.4-9.3 10.8-9.9" stroke="{color}" stroke-width="2.35" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
            f'<path d="M8 15.3c2.7-2 5.9-3 9.3-2.8" {stroke}/>'
            f'<path d="m16.2 6.2 1.4 1.1-1.5 1" {stroke}/>'
            f'<circle cx="8.1" cy="15.3" r=".95" fill="{color}"/>'
        )
    elif name == "avg-profile":
        body = (
            f'<path d="M5.2 18.8h14" {stroke}/>'
            f'<path d="M5.2 18.8V5.2" {stroke}/>'
            f'<path d="M6.8 17.4c4.8-.5 8.1-3.6 10.4-10.1" {stroke}/>'
            f'<path d="M6.8 16.4c1.9-5.4 5.8-8.3 10.4-8.7" {stroke}/>'
            f'<path d="M6.8 16.9c3.4-4.6 6.8-6.9 10.4-8.4" stroke="{color}" stroke-width="2.35" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
            f'<circle cx="12.2" cy="12.2" r="1" fill="{color}"/>'
        )
    elif name == "waves":
        body = (
            f'<path d="M3.8 13.5c1.8-3.5 3.5-4.8 5.2-4.8 1.5 0 2.4.9 3.2 2 .8 1 1.6 2 2.9 2 1.3 0 2.4-.9 4-3" {stroke}/>'
            f'<path d="M4.2 18c1.2-1.8 2.3-2.6 3.5-2.6 1 0 1.7.6 2.3 1.3.7.7 1.3 1.4 2.4 1.4 1 0 1.8-.6 3-2" {stroke}/>'
            f'<circle cx="18.2" cy="18.1" r="1.35" fill="{color}"/>'
        )
    elif name == "layout":
        body = (
            f'<circle cx="12" cy="12" r="2" fill="{color}"/>'
            f'<path d="M12 4.2v4.9M12 14.9v4.9M4.2 12h4.9M14.9 12h4.9M6.7 6.7l3.1 3.1M14.2 14.2l3.1 3.1M17.3 6.7l-3.1 3.1M9.8 14.2l-3.1 3.1" {stroke}/>'
        )
    elif name == "document":
        body = (
            f'<path d="M7 4h7l4 4v11a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z" {stroke}/>'
            f'<path d="M14 4v4h4" {stroke}/>'
            f'<path d="M9 16.5 11.6 12l1.6 2.2h2l-2.4 4.2-1.5-2.2-2.3-.1Z" stroke="{color}" stroke-width="1.7" stroke-linejoin="round" fill="none"/>'
        )
    elif name == "export":
        body = (
            f'<path d="M12 4v9" {stroke}/>'
            f'<path d="m8.6 10.5 3.4 3.5 3.4-3.5" {stroke}/>'
            f'<path d="M5 16.5v1.2A1.3 1.3 0 0 0 6.3 19h11.4a1.3 1.3 0 0 0 1.3-1.3v-1.2" {stroke}/>'
        )
    elif name == "home":
        body = (
            f'<path d="M4.5 10.2 12 4l7.5 6.2" {stroke}/>'
            f'<path d="M6.5 9.4V19h11V9.4" {stroke}/>'
            f'<path d="M10 19v-5h4v5" {stroke}/>'
        )
    elif name == "turbine-simple":
        body = (
            f'<path d="M12 20V10V4M12 10L6.5 14M12 10l5.5 4" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
        )
    elif name == "file-text":
        body = (
            f'<path d="M14 3v4a1 1 0 0 0 1 1h4" {stroke}/>'
            f'<path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z" {stroke}/>'
            f'<path d="M9 13h6" {stroke}/>'
            f'<path d="M9 17h6" {stroke}/>'
        )
    elif name == "dollar":
        body = (
            f'<circle cx="12" cy="12" r="8" {stroke}/>'
            f'<path d="M12 6.5v11" {stroke}/>'
            f'<path d="M14.5 9.5c0-1.1-.9-2-2.5-2-1.6 0-2.5.9-2.5 2s.9 2 2.5 2c1.6 0 2.5.9 2.5 2s-.9 2-2.5 2c-1.6 0-2.5-.9-2.5-2" {stroke}/>'
        )
    elif name == "bar-chart":
        body = (
            f'<path d="M18 20V10" {stroke}/>'
            f'<path d="M12 20V4" {stroke}/>'
            f'<path d="M6 20v-4" {stroke}/>'
        )
    elif name == "database":
        body = (
            f'<ellipse cx="12" cy="5" rx="9" ry="3" {stroke}/>'
            f'<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" {stroke}/>'
            f'<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" {stroke}/>'
        )
    elif name == "calendar":
        body = (
            f'<rect width="18" height="18" x="3" y="4" rx="2" ry="2" {stroke}/>'
            f'<line x1="16" x2="16" y1="2" y2="6" {stroke}/>'
            f'<line x1="8" x2="8" y1="2" y2="6" {stroke}/>'
            f'<line x1="3" x2="21" y1="10" y2="10" {stroke}/>'
        )
    elif name == "file":
        body = (
            f'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" {stroke}/>'
            f'<polyline points="14 2 14 8 20 8" {stroke}/>'
        )
    elif name == "download":
        body = (
            f'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" {stroke}/>'
            f'<polyline points="7 10 12 15 17 10" {stroke}/>'
            f'<line x1="12" x2="12" y1="15" y2="3" {stroke}/>'
        )
    else:
        body = f'<circle cx="12" cy="12" r="8" {stroke}/>'

    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true" '
        f'style="display:block; overflow:visible;">{body}</svg>'
    )

def _sidebar_href(script_path: str) -> str:
    if script_path == "Inicio.py":
        return "/"
    _, page_name = page_icon_and_name(Path(script_path))
    return f"/{page_name}"

def get_sidebar_css() -> str:
    return """
    <style>
    section[data-testid="stSidebar"],
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div:first-child,
    [data-testid="stSidebarContent"] {
        background: linear-gradient(185deg, #ffffff 60%, #f3f8ff) !important;
        border-right: 1px solid #dce7f5 !important;
    }

    section[data-testid="stSidebar"] {
        width: 252px !important;
        min-width: 252px !important;
        max-width: 252px !important;
    }

    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
        display: none !important;
    }

    /* Main como el mockup Aurora: header fuera, contenido 1480px a la izquierda */
    header[data-testid="stHeader"] {
        display: none !important;
    }

    [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }

    .main .block-container,
    section[data-testid="stMain"] .block-container,
    div[data-testid="stMainBlockContainer"] {
        width: 100% !important;
        max-width: 1480px !important;
        margin-left: 0 !important;
        margin-right: auto !important;
        padding-left: 28px !important;
        padding-right: 28px !important;
        padding-top: 22px !important;
        padding-bottom: 60px !important;
    }

    @media (max-width: 1100px) {
        .main .block-container,
        section[data-testid="stMain"] .block-container,
        div[data-testid="stMainBlockContainer"] {
            padding-left: 0.9rem !important;
            padding-right: 0.9rem !important;
        }
    }

    section[data-testid="stSidebar"] .block-container {
        padding-top: 20px !important;
        padding-left: 14px !important;
        padding-right: 14px !important;
        padding-bottom: 20px !important;
    }

    /* Sin cabecera fantasma del sidebar (el mockup arranca en el brand) */
    [data-testid="stSidebarHeader"] {
        display: none !important;
    }
    [data-testid="stSidebarUserContent"] {
        padding-top: 20px !important;
    }

    .sidebar-brand {
        margin: 0 0.55rem 1rem 0.55rem;
        padding: 0.2rem 0.1rem 0.95rem 0.1rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.16);
    }

    .sidebar-brand__row {
        display: flex;
        align-items: center;
        gap: 0.9rem;
    }

    .sidebar-brand__logo {
        width: 40px;
        height: 40px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid rgba(191, 219, 254, 0.9);
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 10px 20px rgba(37, 99, 235, 0.08);
        flex-shrink: 0;
    }

    .sidebar-brand__title {
        font-size: 1.42rem;
        line-height: 1.05;
        font-weight: 800;
        color: #102A4C !important;
    }

    .sidebar-brand__subtitle {
        font-size: 0.88rem;
        font-weight: 500;
        color: #000000 !important;
    }

    .sidebar-nav {
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
        margin: 0 0.35rem 1rem 0.35rem;
    }

    .sidebar-link {
        display: flex;
        align-items: center;
        gap: 0.8rem;
        padding: 0.78rem 0.72rem;
        border-radius: 18px;
        border: 1px solid transparent !important;
        text-decoration: none !important;
        color: inherit !important;
        transition: all 0.18s ease;
    }

    .sidebar-link,
    .sidebar-link:link,
    .sidebar-link:visited,
    .sidebar-link:hover,
    .sidebar-link:active,
    .sidebar-link * {
        text-decoration: none !important;
    }

    .sidebar-link:hover {
        background: #F4F8FF !important;
        border-color: #CFE0F5 !important;
    }

    .sidebar-link.is-active {
        background: #EAF3FF !important;
        border: 1px solid #80B4FF !important;
        border-radius: 18px !important;
        box-shadow: 0 12px 28px rgba(11, 99, 246, 0.10) !important;
    }

    .sidebar-link__icon {
        width: 48px;
        height: 48px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid rgba(203, 213, 225, 0.95);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }

    .sidebar-link.is-active .sidebar-link__icon {
        background: #EAF3FF !important;
        border: 1px solid #5FA8FF !important;
        color: #0057E7 !important;
    }

    .sidebar-link.is-active .sidebar-link__phase,
    .sidebar-link.is-active .sidebar-link__name {
        color: #0B63F6 !important;
        font-weight: 800 !important;
        text-decoration: none !important;
    }

    .sidebar-link.is-active .sidebar-link__name {
        color: #1E5FBF !important;
        font-weight: 700 !important;
    }

    .sidebar-link__copy {
        display: flex;
        flex-direction: column;
        gap: 0.08rem;
        min-width: 0;
    }

    .sidebar-link__phase {
        font-size: 0.95rem;
        font-weight: 800;
        color: #000000 !important;
    }

    .sidebar-link__name {
        font-size: 0.97rem;
        font-weight: 400;
        color: #000000 !important;
    }

    .sidebar-link:hover .sidebar-link__phase,
    .sidebar-link:hover .sidebar-link__name {
        color: #0B63F6 !important;
    }
    </style>
    """

def _load_global_css(current_script: str = "") -> None:
    """Load the shared SMA 2.0 stylesheet with anti-FOUC animation, AND
    preload the CSS of every phase in a single <style> block.

    Esto último es clave para evitar el "flash del diseño anterior" al cambiar
    de fase: las reglas que estilizan `.st-key-fN_*` de todas las fases ya
    están presentes desde el primer render, así el navegador no tiene que
    esperar a que el script de la nueva fase emita su <style>.

    Delegates to assets_loader.* which cache by mtime so repeated reruns
    skip disk I/O entirely.
    """
    _load_global_css_cached(include_anti_fouc=True)
    # Excluir la página actual del bloque combinado: ya inyecta su propio
    # <style> en el cuerpo, así evitamos duplicar su CSS en cada rerun.
    _preload_all_phases_css(Path(current_script).name if current_script else "")


# ─────────────────────────────────────────────────────────────────────────────
# Rediseño "Aurora": color de acento por fase + sidebar pills + stepper global.
# Todo es HTML/CSS (sin JS): compatible con QtWebEngine (Chromium) y con el
# mecanismo anti-FOUC existente (assets_loader recolecta los <style>).
# ─────────────────────────────────────────────────────────────────────────────
_PHASE_META = [
    # (script, etiqueta, nombre, emoji, acento, acento_oscuro)
    ("Inicio.py", "Inicio", "Panel inicial", "🏠", "#2563eb", "#1e40af"),
    ("pages/1_Fase_1_Aerogenerador.py", "Fase 1", "Aerogenerador", "🌀", "#0284c7", "#075985"),
    ("pages/2_Fase_2_Perfiles_de_viento.py", "Fase 2", "Perfiles de viento", "🌬️", "#0891b2", "#155e75"),
    ("pages/3_Fase_3_Velocidad_promedio.py", "Fase 3", "Rosa y velocidad", "🧭", "#4f46e5", "#3730a3"),
    ("pages/4_Fase_4_Estelas_y_arreglo.py", "Fase 4", "Estelas y arreglo", "🌪️", "#7c3aed", "#5b21b6"),
    ("pages/5_Fase_5_AEP_bruta_y_neta.py", "Fase 5", "AEP y economía", "⚡", "#059669", "#065f46"),
    ("pages/6_Fase_6_Estudios_avanzados.py", "Fase 6", "Estudios avanzados", "🔬", "#0d9488", "#115e59"),
    ("pages/7_Fase_7_Exportar_y_guardar.py", "Fase 7", "Exportar y guardar", "📦", "#d97706", "#92400e"),
]


def _phase_index(current_script: str) -> int:
    for i, meta in enumerate(_PHASE_META):
        if meta[0] == current_script:
            return i
    return 0


# Skin global Aurora para el contenido (hero con gradiente del acento, franja
# de acento en cards, pulido de KPIs). Usa !important porque el CSS local de
# cada página se inyecta DESPUÉS de este bloque.
_AURORA_MAIN_CSS = """
<style id="aurora-main">
/* Tipografía del mockup (Segoe UI Variable). Excluye los iconos material. */
html body *:not([data-testid="stIconMaterial"]):not([class*="material-symbols"]){
  font-family:'Segoe UI Variable Display','Segoe UI',system-ui,sans-serif;
}

/* Fondo del mockup: radiales del acento + degradado vertical suave */
[data-testid="stAppViewContainer"]{
  background:
    radial-gradient(1100px 420px at 90% -120px, color-mix(in srgb, var(--ac) 16%, transparent), transparent 70%),
    radial-gradient(900px 500px at -150px 45%, color-mix(in srgb, var(--ac) 7%, transparent), transparent 70%),
    linear-gradient(180deg,#f7fbff 0%, #eef5fd 60%, #f4f8fe 100%) !important;
}
[data-testid="stMain"]{background:transparent !important}

.hero-card{
  background:linear-gradient(118deg,var(--ac) 0%, var(--ac2) 80%) !important;
  border:none !important;
  box-shadow:0 18px 38px color-mix(in srgb, var(--ac) 30%, transparent), inset 0 1px 0 rgba(255,255,255,.25) !important;
}
.hero-card::after{
  background:
    radial-gradient(circle at 86% 14%, rgba(255,255,255,.20) 0 52px, transparent 53px),
    radial-gradient(circle at 95% 64%, rgba(255,255,255,.12) 0 84px, transparent 85px) !important;
  opacity:1 !important;
}
.fase-hero-title{color:#ffffff !important;text-shadow:0 1px 2px rgba(0,0,0,.14)}
.fase-hero-subtitle{color:rgba(255,255,255,.93) !important}
.hero-card .fase-hero-subtitle b, .hero-card .fase-hero-title b{color:#fff !important}

/* Hero de Inicio (clases propias de la página de inicio) */
.home-ref-hero{
  background:linear-gradient(118deg,var(--ac) 0%, var(--ac2) 80%) !important;
  border:none !important;
  box-shadow:0 22px 44px color-mix(in srgb, var(--ac) 32%, transparent), inset 0 1px 0 rgba(255,255,255,.25) !important;
}
.home-ref-hero-title{color:#ffffff !important;text-shadow:0 1px 2px rgba(0,0,0,.12) !important}
.home-ref-hero-sub{color:rgba(255,255,255,.94) !important}

/* Cápsulas de icono KPI con tinte de acento (estilo mockup Aurora) */
[class*="-kpi-icon"], [class*="-sc-icon"], [class*="-icon-soft"]{
  background:linear-gradient(135deg, color-mix(in srgb, var(--ac) 13%, #fff), color-mix(in srgb, var(--ac) 4%, #fff)) !important;
}

/* Franja de acento superior en las cards grandes (st.container con key).
   La clase st-key-*card* cae en el propio stVerticalBlock → la franja va ahí. */
div[data-testid="stVerticalBlock"][class*="st-key-"][class*="card"]{position:relative !important}
div[data-testid="stVerticalBlock"][class*="st-key-"][class*="card"]::before{
  content:"";position:absolute;left:0;right:0;top:0;height:4px;z-index:5;
  border-radius:26px 26px 0 0;
  background:linear-gradient(90deg, var(--ac), color-mix(in srgb, var(--ac) 25%, #fff) 70%, transparent);
}

/* Pulido global de los KPI e iconos de sección (todas las fases comparten sufijos) */
[class*="-icon-soft"]{
  border-radius:14px !important;
  background:linear-gradient(135deg, color-mix(in srgb, var(--ac) 16%, #fff), color-mix(in srgb, var(--ac) 7%, #fff)) !important;
  border:1.5px solid color-mix(in srgb, var(--ac) 35%, #fff) !important;
  box-shadow:0 5px 12px color-mix(in srgb, var(--ac) 16%, transparent) !important;
}
[class*="-kpi-icon"], [class*="-sc-icon"]{
  background:linear-gradient(135deg, color-mix(in srgb, var(--ac) 14%, #fff), color-mix(in srgb, var(--ac) 5%, #fff)) !important;
  box-shadow:0 5px 12px color-mix(in srgb, var(--ac) 16%, transparent) !important;
}
[class*="-kpi-card"]{transition:box-shadow .18s !important;border-radius:18px !important}
[class*="-kpi-card"]:hover{box-shadow:0 12px 26px color-mix(in srgb, var(--ac) 16%, transparent) !important}

/* Botones Streamlit con el acento de la fase */
div[data-testid="stButton"] > button[kind="primary"],
div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"]{
  background:linear-gradient(120deg, var(--ac), var(--ac2)) !important;
  border:none !important;
  box-shadow:0 8px 18px color-mix(in srgb, var(--ac) 30%, transparent) !important;
}
div[data-testid="stButton"] > button, div[data-testid="stDownloadButton"] > button{
  border-radius:12px !important;
}

/* Stepper de fases (emitido por navigation en todas las páginas) */
.aurora-stepper{display:flex;align-items:center;background:#fff;border:1px solid #dce7f5;border-radius:19px;
  padding:11px 18px;margin:0 0 20px 0;box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06)}
.aurora-step{display:flex;align-items:center;gap:8px;flex:1;min-width:0;text-decoration:none !important}
.aurora-step .sdot{width:33px;height:33px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-size:14.5px;background:#f3f8ff;border:2px solid #dce7f5;flex-shrink:0}
.aurora-step span{font-size:10px;font-weight:800;color:#5a6b85;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:.01em}
.aurora-step .sbar{flex:1;height:3.5px;border-radius:2px;background:#dce7f5;margin:0 7px}
.aurora-step.done .sdot{background:#f0fdf4;border-color:#86efac}
.aurora-step.done .sbar{background:linear-gradient(90deg,#86efac,#bbf7d0)}
.aurora-step.current .sdot{background:linear-gradient(135deg,var(--ac),var(--ac2));border-color:var(--ac);color:#fff;
  animation:aurorapulse 2s infinite}
.aurora-step.current span{color:var(--ac)}
@keyframes aurorapulse{0%,100%{box-shadow:0 0 0 4px color-mix(in srgb,var(--ac) 22%,transparent)}50%{box-shadow:0 0 0 8px color-mix(in srgb,var(--ac) 8%,transparent)}}
</style>
"""

# Sidebar Aurora: re-estiliza las clases existentes del sidebar (se inyecta
# DESPUÉS de get_sidebar_css(), así sus reglas ganan en cascada).
_AURORA_SIDEBAR_CSS = """
<style id="aurora-sidebar">
/* Brand del mockup: logo α en squircle con gradiente azul→violeta */
.sidebar-brand{margin:0 0 14px 0 !important;padding:4px 8px 18px 8px !important;border-bottom:1px solid #e9f0fa !important}
.sidebar-brand__row{gap:12px !important}
.sidebar-brand__logo{
  width:46px !important;height:46px !important;border-radius:15px !important;
  background:linear-gradient(135deg,#3b82f6,#8b5cf6 90%) !important;border:none !important;
  color:#fff !important;font-weight:900 !important;font-size:22px !important;
  box-shadow:0 10px 22px rgba(59,130,246,.35), inset 0 1px 0 rgba(255,255,255,.4) !important;
}
.sidebar-brand__title{font-size:17.5px !important;font-weight:900 !important;letter-spacing:-.02em !important;color:#0b2447 !important}
.sidebar-brand__subtitle{
  font-size:10.5px !important;font-weight:700 !important;color:#5a6b85 !important;
  letter-spacing:.02em !important;text-transform:uppercase !important;white-space:nowrap !important;
}
.sidebar-nav{gap:5px !important;margin:0 0 14px 0 !important}
.sidebar-link{padding:8px 10px !important;border-radius:15px !important;gap:11px !important}
.sidebar-link__icon{
  width:37px !important;height:37px !important;border-radius:12px !important;font-size:17px !important;
  background:#ffffff !important;border:1px solid #dce7f5 !important;
  box-shadow:0 2px 5px rgba(11,36,71,.05) !important;
}
.sidebar-link.is-active{
  background:linear-gradient(120deg, color-mix(in srgb, var(--ic) 12%, #fff), color-mix(in srgb, var(--ic) 5%, #fff)) !important;
  border:1px solid color-mix(in srgb, var(--ic) 45%, #fff) !important;
  box-shadow:0 10px 22px color-mix(in srgb, var(--ic) 20%, transparent) !important;
}
.sidebar-link.is-active .sidebar-link__icon{
  background:linear-gradient(135deg, var(--ic), var(--ic2)) !important;
  border-color:transparent !important;
  box-shadow:0 6px 14px color-mix(in srgb, var(--ic) 40%, transparent) !important;
}
.sidebar-link.is-active .sidebar-link__phase{color:var(--ic) !important}
.sidebar-link.is-active .sidebar-link__name{color:color-mix(in srgb, var(--ic) 80%, #000) !important}
.sidebar-link.is-done .sidebar-link__icon{background:#f0fdf4 !important;border-color:#bbf7d0 !important}
.sidebar-link__check{
  margin-left:auto;width:18px;height:18px;border-radius:50%;background:#dcfce7;color:#15803d;
  font-size:11px;font-weight:900;display:flex;align-items:center;justify-content:center;flex-shrink:0;
}
.sidebar-link__phase{font-size:12.5px !important;font-weight:800 !important;letter-spacing:-.01em !important}
.sidebar-link__name{font-size:10px !important;font-weight:600 !important;color:#5a6b85 !important}
.aurora-progress{margin:16px 0 0 0;padding:14px 12px;border-radius:16px;background:#fff;
  border:1px solid #dce7f5;text-align:center;box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06)}
.aurora-progress small{color:#5a6b85;font-weight:800;font-size:9.5px;text-transform:uppercase;letter-spacing:.08em}
</style>
"""


def _render_aurora_accent(idx: int) -> str:
    ac, ac2 = _PHASE_META[idx][4], _PHASE_META[idx][5]
    return f"<style id='aurora-accent'>:root{{--ac:{ac};--ac2:{ac2};}}</style>"


def _render_stepper(idx: int) -> str:
    pasos = []
    for i, (script, label, _nombre, emoji, _ac, _ac2) in enumerate(_PHASE_META):
        clase = "current" if i == idx else ("done" if i < idx else "")
        barra = '<div class="sbar"></div>' if i < len(_PHASE_META) - 1 else ""
        pasos.append(
            f'<a class="aurora-step {clase}" href="{_sidebar_href(script)}" target="_self">'
            f'<div class="sdot">{emoji}</div><span>{label}</span>{barra}</a>'
        )
    return f'<div class="aurora-stepper">{"".join(pasos)}</div>'


def _render_progress_ring(idx: int) -> str:
    pct = int(idx / (len(_PHASE_META) - 1) * 100)
    dash = pct * 2.073  # circunferencia r=33 ≈ 207.3
    return f"""
    <div class="aurora-progress"><small>Progreso del proyecto</small>
      <svg viewBox="0 0 84 84" width="78" style="margin:9px auto 2px;display:block">
        <circle cx="42" cy="42" r="33" fill="none" stroke="#e9f0fa" stroke-width="10"/>
        <circle cx="42" cy="42" r="33" fill="none" stroke="url(#aurorapg)" stroke-width="10" stroke-linecap="round"
          stroke-dasharray="{dash:.0f} 999" transform="rotate(-90 42 42)"/>
        <defs><linearGradient id="aurorapg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="var(--ac)"/><stop offset="1" stop-color="var(--ac2)"/></linearGradient></defs>
        <text x="42" y="48" text-anchor="middle" font-size="17" font-weight="900" fill="#0b2447">{pct}%</text>
      </svg>
    </div>"""


def render_dropdown_visibility_fix() -> None:
    """Late CSS override for Streamlit expanders and dropdown menus.

    Some phase-level cards use overflow/height rules for fixed dashboard cards.
    This override must be injected after local page CSS so expanded panels and
    BaseWeb dropdown popovers are visible instead of being clipped.
    """
    st.markdown(
        """
        <style id="sma-dropdown-expander-visibility-fix">
        html body [data-testid="stAppViewContainer"] div[class*="st-key-"]:has([data-testid="stExpander"]),
        html body [data-testid="stAppViewContainer"] div[data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stExpander"]),
        html body [data-testid="stAppViewContainer"] div[data-testid="stVerticalBlock"]:has([data-testid="stExpander"]),
        html body [data-testid="stAppViewContainer"] div[data-testid="stElementContainer"]:has([data-testid="stExpander"]),
        html body [data-testid="stAppViewContainer"] div[data-testid="stHorizontalBlock"]:has([data-testid="stExpander"]),
        html body [data-testid="stAppViewContainer"] div[data-testid="column"]:has([data-testid="stExpander"]) {
            overflow: visible !important;
            height: auto !important;
            max-height: none !important;
            contain: none !important;
        }

        html body [data-testid="stAppViewContainer"] [data-testid="stExpander"],
        html body [data-testid="stAppViewContainer"] [data-testid="stExpander"] details,
        html body [data-testid="stAppViewContainer"] [data-testid="stExpanderDetails"] {
            display: block !important;
            overflow: visible !important;
            height: auto !important;
            max-height: none !important;
            min-height: 0 !important;
            visibility: visible !important;
            opacity: 1 !important;
            clip: auto !important;
            clip-path: none !important;
            transform: none !important;
            contain: none !important;
        }

        html body [data-testid="stAppViewContainer"] [data-testid="stExpander"] {
            position: relative !important;
            z-index: 20 !important;
            background: #ffffff !important;
        }

        html body [data-testid="stAppViewContainer"] [data-testid="stExpander"] details[open],
        html body [data-testid="stAppViewContainer"] [data-testid="stExpander"] details[open] > div,
        html body [data-testid="stAppViewContainer"] [data-testid="stExpander"] details[open] [data-testid="stExpanderDetails"] {
            display: block !important;
            position: relative !important;
            z-index: 30 !important;
            overflow: visible !important;
            height: auto !important;
            max-height: none !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            background: #ffffff !important;
        }

        html body [data-baseweb="popover"],
        html body [data-baseweb="popover"] > div,
        html body [role="listbox"] {
            z-index: 2147483647 !important;
            opacity: 1 !important;
            visibility: visible !important;
            overflow: visible !important;
            max-height: none !important;
            contain: none !important;
        }

        html body [data-testid="stAppViewContainer"] div[data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stSelectbox"]),
        html body [data-testid="stAppViewContainer"] div[data-testid="stVerticalBlock"]:has([data-testid="stSelectbox"]),
        html body [data-testid="stAppViewContainer"] div[data-testid="stElementContainer"]:has([data-testid="stSelectbox"]) {
            overflow: visible !important;
            contain: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_stepper(current_script: str) -> None:
    """Pinta el stepper de fases en el punto de llamada.

    Lo usa Inicio para colocarlo DEBAJO del hero (orden del mockup Aurora);
    el resto de páginas lo recibe arriba vía render_sidebar_navigation.
    """
    st.markdown(_render_stepper(_phase_index(current_script)), unsafe_allow_html=True)


def render_sidebar_navigation(current_script: str, stepper: bool = True):
    # ── Inject global CSS first to prevent FOUC ──
    _load_global_css(current_script)

    try:
        from session_helpers import clear_other_phase_state

        previous = st.session_state.get("_current_phase_script", None)
        if previous != current_script:
            clear_other_phase_state(current_script)
            st.session_state["_current_phase_script"] = current_script
    except Exception:
        # No interrumpir la navegación si el helper no está disponible
        pass
    idx_actual = _phase_index(current_script)

    sidebar_brand_html = textwrap.dedent(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand__row">
                <div class="sidebar-brand__logo">α</div>
                <div class="sidebar-brand__copy">
                    <div class="sidebar-brand__title">SMA 2.0</div>
                    <div class="sidebar-brand__subtitle">Wind Project Analyzer</div>
                </div>
            </div>
        </div>
        """
    ).strip()

    nav_items = []
    for i, (page_path, phase_label, phase_name, emoji, ac, ac2) in enumerate(_PHASE_META):
        is_active = page_path == current_script
        estado = " is-active" if is_active else (" is-done" if i < idx_actual else "")
        check = '<span class="sidebar-link__check">✓</span>' if i < idx_actual else ""
        nav_items.append(
            textwrap.dedent(
                f"""
                <a class="sidebar-link{estado}" href="{_sidebar_href(page_path)}" target="_self" style="--ic:{ac};--ic2:{ac2}">
                    <span class="sidebar-link__icon">{emoji}</span>
                    <span class="sidebar-link__copy">
                        <span class="sidebar-link__phase">{phase_label}</span>
                        <span class="sidebar-link__name">{phase_name}</span>
                    </span>{check}
                </a>
                """
            ).strip()
        )
    sidebar_nav_html = f'<div class="sidebar-nav">{"".join(nav_items)}</div>'

    # Acento de la fase + skin Aurora + stepper en el contenido principal.
    st.markdown(_render_aurora_accent(idx_actual), unsafe_allow_html=True)
    st.markdown(_AURORA_MAIN_CSS, unsafe_allow_html=True)
    if stepper:
        st.markdown(_render_stepper(idx_actual), unsafe_allow_html=True)

    st.sidebar.markdown(get_sidebar_css(), unsafe_allow_html=True)
    st.sidebar.markdown(_AURORA_SIDEBAR_CSS, unsafe_allow_html=True)
    st.sidebar.markdown(sidebar_brand_html, unsafe_allow_html=True)
    st.sidebar.markdown(sidebar_nav_html, unsafe_allow_html=True)
    st.sidebar.markdown(_render_progress_ring(idx_actual), unsafe_allow_html=True)

