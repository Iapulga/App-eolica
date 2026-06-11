import io
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

APP_DIR_NAME = "AppEolica"
DB_BASENAME = "app_eolica.db"


def _get_persistent_base_dir() -> Path:
    """
    En modo ejecutable (.exe) guarda la BD en AppData/Local/AppEolica.
    En modo desarrollo, la guarda junto a este archivo db.py.
    """
    if getattr(sys, "frozen", False):
        local_appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local_appdata:
            base_dir = Path(local_appdata) / APP_DIR_NAME
        else:
            base_dir = Path.home() / APP_DIR_NAME
    else:
        base_dir = Path(__file__).resolve().parent

    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _get_db_path() -> Path:
    return _get_persistent_base_dir() / DB_BASENAME


def _migrate_legacy_db_if_needed(db_path: Path) -> None:
    """
    Si existe una BD antigua junto al .exe o en el directorio de trabajo,
    la copia una sola vez a la ruta persistente nueva.
    """
    if db_path.exists():
        return

    candidates = []

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / DB_BASENAME)

    candidates.append(Path.cwd() / DB_BASENAME)

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.resolve() != db_path.resolve():
                shutil.copy2(candidate, db_path)
                return
        except Exception:
            pass


DB_FILE = _get_db_path()
_migrate_legacy_db_if_needed(DB_FILE)

DEFAULT_CONFIG = {
    "project_mode": "free",
    "project_profile": "",
    "diametro": "100.00",
    "densidad": "1.22",
    "perfil_vref": "8.00",
    "perfil_href": "10.00",
    "perfil_hhub": "80.00",
    "perfil_alpha": "0.14",
    "perfil_alpha_usuario": "",
    "perfil_z0": "0.03",
    "perfil_z0_teorica": "",
    "perfil_ustar": "",
    "perfil_ustar_usuario": "",
    "perfil_v50": "",
    "perfil_metodo": "",
    "perfil_roughness_label": "",
    "vel_prom_lista": "",
    "nasa_lat": "",
    "nasa_lon": "",
    "nasa_inicio": "",
    "nasa_fin": "",
    "nasa_fuente": "",
    "site_map_zoom": "9",
    "site_map_tiles": "OpenStreetMap",
    "site_map_image_name": "",
    "site_map_image_mime": "",
    "site_map_image_b64": "",
    "project_name": "Proyecto_eolico_1",
    "f2_altura_deseada": "80.00",
    "f2_roughness_label": "Grass / Césped",

    "f3_modelo_altura": "Exponencial",
    "f3_direccion_fuente": "WD50M",
    "f3_roughness_label": "Grass / Césped",
    "f3_selected_sector": "N",
    "f3_prob_vmax": "25.0",
    "f3_prob_bin_width": "0.5",
    "f3_prob_show_cdf": "False",
    "f3_prob_cutin": "3.0",
    "f3_prob_nominal": "12.0",
    "f3_prob_cutout": "25.0",

    # Claves legacy de la antigua Fase 3.5. Se conservan para abrir proyectos viejos.
    "f35_modelo": "Exponencial",
    "f35_direccion_fuente": "WD50M",
    "f35_roughness_label": "Grass / Césped",
    "f35_selected_sector": "N",
    "f35_vmax": "25.0",
    "f35_bin_width": "0.5",
    "f35_show_cdf": "False",
    "f35_cutin": "3.0",
    "f35_nominal": "12.0",
    "f35_cutout": "25.0",

    "f4_layout_type": "En línea",
    "f4_num_turbinas": "4",
    "f4_dx_D": "5.0",
    "f4_dy_D": "5.0",
    "f4_rotation_deg": "0.0",
    "f4_ct": "0.80",
    "f4_kw": "0.05",
    "f4_selected_sector": "N",
    "f4_selected_turbine": "",
    "f4_base_viento": "50 m",
    "f4_dir_altura": "WD50M",
    "f4_roughness_label": "Grass / Césped",
    "f4_geom_speed": "8.0",
    "f4_weighted_wake_loss_pct": "",
    "f4_worst_sector": "",
    "f4_worst_sector_loss_pct": "",
    "f4_energia_bruta_mwh": "",
    "f4_energia_wake_mwh": "",
    "f4_energia_perdida_mwh": "",
    "f4_geom_critical_sectors": "",
    "f4_geom_max_loss_pct": "",

    "f5_base_viento": "50 m",
    "f5_modo_estadistico": "Weibull",
    "f5_metodo_detalle": "Weibull",
    "f5_dir_altura": "WD50M",
    "f5_roughness_label": "Grass / Césped",
    "f5_wake_mode": "Automática desde Fase 4",
    "f5_wake_manual_pct": "5.0",
    "f5_disp_pct": "3.0",
    "f5_elec_pct": "2.0",
    "f5_otras_pct": "1.5",
    "f5_sens_variable": "Disponibilidad",
    "f5_altura_deseada": "",
    "f5_n_turbinas": "",
    "f5_aep_bruta_total_mwh": "",
    "f5_aep_con_estela_total_mwh": "",
    "f5_perdida_estela_total_mwh": "",
    "f5_aep_neta_total_mwh": "",
    "f5_factor_planta_bruto_pct": "",
    "f5_factor_planta_neto_pct": "",
    "f5_capex_total": "0",
    "f5_capex_mode": "semi_auto_mw",
    "f5_capex_turbina_por_mw": "1100000",
    "f5_capex_bop_por_mw": "450000",
    "f5_capex_red_por_mw": "150000",
    "f5_capex_pct_desarrollo": "5.0",
    "f5_capex_pct_contingencia": "10.0",
    "f5_capex_componentes_json": "",
    "f5_opex_fijo_anual": "0",
    "f5_opex_mode": "fixed_variable",
    "f5_opex_total_anual": "0",
    "f5_opex_fijo_por_mw_anio": "45000",
    "f5_opex_variable_por_mwh": "0",
    "f5_seguros_anuales": "0",
    "f5_terreno_anual": "0",
    "f5_admin_anual": "0",
    "f5_opex_componentes_json": "",
    "f5_vida_util_anios": "20",
    "f5_tasa_descuento_pct": "8.0",
    "f5_degradacion_energia_pct": "0",
    "f5_valor_residual": "0",
    "f5_moneda_base": "USD",
    "f5_moneda_visualizacion": "USD",
    "f5_fx_mode": "manual",
    "f5_fx_rate_cop_per_usd": "4000",
    "f5_fx_timestamp": "",
    "f5_fx_source": "",
    "f5_unidad_monetaria": "USD",
    "f5_potencia_nominal_turbina_mw": "",
    "f5_potencia_instalada_mw": "",
    "f5_aep_neta_mwh_anio": "",
    "f5_vp_costos": "",
    "f5_vp_energia": "",
    "f5_capex_total_display": "",
    "f5_opex_total_anual_display": "",
    "f5_vp_costos_display": "",
    "f5_lcoe_display_mwh": "",
    "f5_lcoe_display_kwh": "",
    "f5_lcoe_mwh": "",
    "f5_lcoe_kwh": "",

    # A1 - Corrección densidad aire
    "f5_altitud_sitio_m": "0",
    "f5_temperatura_media_c": "15.0",
    "f5_densidad_sitio": "",
    "f5_densidad_correccion_aplicada": "True",

    # A2 - Pérdidas desglosadas
    "f5_loss_disp_turb_pct": "",
    "f5_loss_disp_red_pct": "0.0",
    "f5_loss_hielo_pct": "0.0",
    "f5_loss_histeresis_pct": "0.0",
    "f5_loss_curtailment_pct": "0.0",

    # A3 - NPV / IRR / Payback
    "f5_precio_energia_mwh": "60.0",
    "f5_npv": "",
    "f5_irr_pct": "",
    "f5_payback_simple_anios": "",
    "f5_payback_descontado_anios": "",

    # A4 - Sensibilidad tornado
    "f5_sens_delta_pct": "15.0",

    # A5 - Wake models
    "f4_wake_model": "Jensen",
    "f5_wake_model": "Jensen",
    "f5_ambient_ti": "0.10",

    # A6 - TI + IEC
    "f5_iec_clase_declarada": "II",
    "f5_iec_turb_declarada": "B",
    "f5_ti_15ms_calc": "",
    "f5_iec_cumple": "",

    # A7 - Shear desde datos
    "f2_alpha_calc_mediana": "",
    "f2_alpha_calc_p25": "",
    "f2_alpha_calc_p75": "",
    "f2_alpha_calc_n": "",

    # B1 - Monte Carlo P50/P90
    "f5_mc_n_samples": "2000",
    "f5_mc_sigma_k_pct": "3.0",
    "f5_mc_sigma_c_pct": "4.0",
    "f5_mc_sigma_curva_pct": "3.0",
    "f5_mc_sigma_perdidas_pct": "20.0",
    "f5_mc_sigma_wake_pct": "15.0",
    "f5_mc_seed": "42",
    "f5_aep_p50": "",
    "f5_aep_p75": "",
    "f5_aep_p90": "",
    "f5_aep_p99": "",
    "f5_aep_mc_mean": "",
    "f5_aep_mc_std": "",

    # B4 - Serie temporal horaria
    "f5_aep_serie_horaria_total": "",
    "f5_factor_planta_serie_pct": "",
    "f5_serie_horaria_calculada": "False",

    # B5 - Gaussian + TurbOPark
    "f5_gaussian_kstar": "0.038",
    "f5_turbopark_A": "0.04",

    # B7 - Densidad mensual
    "f5_densidad_modo": "anual",

    # B2 - Torre met
    "f2_mast_disponible": "False",
    "f2_mast_source_file": "",
    "f2_mast_recovery_pct": "",
    "f2_mast_altura_sensor": "",

    # B3 - MCP
    "f2_mcp_calculado": "False",
    "f2_mcp_r2": "",
    "f2_mcp_rmse": "",
    "f2_mcp_slope_global": "",
    "f2_serie_uso": "nasa",
    "mcp_coefs_json": "",

    # B6 - Multi-curva
    "f1_curves_activas_count": "1",
    "f1_default_curve_id": "default",

    # Fase 6 - Estudios avanzados
    "f6_receptores_json": "",
    "f6_ruido_lwa_db": "105.0",
    "f6_ruido_lim_diurno": "50.0",
    "f6_ruido_lim_nocturno": "40.0",
    "f6_flicker_limite_h": "30.0",
    "f6_aves_tabla_json": "",
    "f6_cap_inyeccion_mw": "",
    "f6_disp_red_pct": "98.0",
    "f6_opt_maxiter": "5",
    "f6_flow_pixel_m": "30.0",
    "f6_flow_l_hill_m": "",
    "f5_ruido_max_db": "",
    "f5_flicker_max_h": "",
}


def tabla_vacia_curva():
    velocidades = list(range(0, 26))
    potencias_w = [0] * len(velocidades)
    return pd.DataFrame({
        "Velocidad (m/s)": [str(v) for v in velocidades],
        "Potencia (W)": [str(p) for p in potencias_w]
    })


def get_connection():
    conn = sqlite3.connect(str(DB_FILE), check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


@st.cache_resource(show_spinner=False)
def _get_read_connection(db_path: str):
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA cache_size = -32000;")   # 32 MB page cache
    conn.execute("PRAGMA temp_store = MEMORY;")   # temp tables in RAM
    conn.execute("PRAGMA mmap_size = 268435456;") # 256 MB memory-mapped I/O
    return conn


def _db_cache_stamp() -> tuple[int, int, int]:
    paths = [DB_FILE, DB_FILE.with_name(DB_FILE.name + "-wal"), DB_FILE.with_name(DB_FILE.name + "-shm")]
    stamp = []
    for path in paths:
        try:
            stamp.append(path.stat().st_mtime_ns)
        except OSError:
            stamp.append(0)
    return tuple(stamp)


@st.cache_data(show_spinner=False)
def _read_sql_cached(query: str, params: tuple = (), stamp: tuple[int, int, int] | None = None) -> pd.DataFrame:
    conn = _get_read_connection(str(DB_FILE))
    return pd.read_sql_query(query, conn, params=params)


def _read_sql(query: str, params: tuple = ()) -> pd.DataFrame:
    return _read_sql_cached(query, tuple(params), _db_cache_stamp()).copy()


def _clear_cached_reads() -> None:
    _read_sql_cached.clear()


def get_db_file_path():
    return str(DB_FILE)





@st.cache_resource(show_spinner=False)
def _init_db_once():
    """Run schema creation once per process via cache_resource."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS curva_potencia (
            fila INTEGER PRIMARY KEY,
            velocidad TEXT,
            potencia TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS nasa_hourly (
            timestamp TEXT PRIMARY KEY,
            YEAR INTEGER,
            MO INTEGER,
            DY INTEGER,
            HR INTEGER,
            WS10M REAL,
            WS50M REAL,
            WD10M REAL,
            WD50M REAL,
            latitude REAL,
            longitude REAL,
            source TEXT
        )
    """)

    # Migración: añadir T2M, PS, WS_MCP si no existen (Fase B7, B3)
    try:
        cur.execute("PRAGMA table_info(nasa_hourly)")
        cols_nasa = {row[1] for row in cur.fetchall()}
        if "T2M" not in cols_nasa:
            cur.execute("ALTER TABLE nasa_hourly ADD COLUMN T2M REAL")
        if "PS" not in cols_nasa:
            cur.execute("ALTER TABLE nasa_hourly ADD COLUMN PS REAL")
        if "WS_MCP" not in cols_nasa:
            cur.execute("ALTER TABLE nasa_hourly ADD COLUMN WS_MCP REAL")
    except Exception:
        pass

    # B2 - Torre meteorológica
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mast_data (
            timestamp TEXT PRIMARY KEY,
            ws_10min REAL,
            ws_std REAL,
            wd_10min REAL,
            altura_sensor REAL,
            temp_c REAL,
            source_file TEXT,
            sector TEXT
        )
    """)

    # B6 - Multi-curva potencia
    cur.execute("""
        CREATE TABLE IF NOT EXISTS power_curves (
            curve_id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            diametro REAL,
            potencia_nominal_W REAL,
            ct REAL,
            curve_json TEXT NOT NULL,
            created_at TEXT
        )
    """)

    try:
        cur.execute("PRAGMA table_info(park_layout)")
        cols_layout = {row[1] for row in cur.fetchall()}
        if "curve_id" not in cols_layout:
            cur.execute("ALTER TABLE park_layout ADD COLUMN curve_id TEXT")
    except Exception:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS park_layout (
            fila INTEGER PRIMARY KEY,
            turbina_id TEXT,
            x_m REAL,
            y_m REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS park_scenarios (
            name TEXT PRIMARY KEY,
            updated_at TEXT,
            layout_json TEXT,
            settings_json TEXT,
            metrics_json TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_projects (
            name TEXT PRIMARY KEY,
            updated_at TEXT,
            project_json TEXT
        )
    """)

    conn.commit()

    for key, value in DEFAULT_CONFIG.items():
        cur.execute(
            "INSERT OR IGNORE INTO app_config (key, value) VALUES (?, ?)",
            (key, value)
        )

    cur.execute("SELECT COUNT(*) FROM curva_potencia")
    total_curva = cur.fetchone()[0]

    conn.commit()
    conn.close()
    return total_curva


def _seed_empty_curve_if_needed() -> None:
    """Siembra la curva por defecto SOLO si la tabla está vacía.

    Defensa en profundidad contra el bug histórico de wipe-on-stale-cache:
      1) Consulta el COUNT(*) real (no cacheado) cada vez.
      2) Si la tabla está vacía, inserta los 26 valores por defecto
         usando INSERT OR IGNORE — esto NO borra nada existente: si por
         cualquier motivo (race condition, lectura stale, etc.) la condición
         se cumple erróneamente, los INSERT chocarán contra la PK `fila`
         y serán ignorados silenciosamente, dejando los datos del usuario intactos.
      3) NUNCA se llama a guardar_tabla_curva() (que es destructivo: DELETE+INSERT).
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM curva_potencia")
        if cur.fetchone()[0] != 0:
            return
        df_default = tabla_vacia_curva().reset_index(drop=True)
        rows = [
            (i, str(r["Velocidad (m/s)"]).strip(), str(r["Potencia (W)"]).strip())
            for i, r in df_default.iterrows()
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO curva_potencia (fila, velocidad, potencia) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Sistema de auto-backup de la DB del usuario.
#
# Razón: incluso con todas las defensas (INSERT OR IGNORE, schema versioning,
# checks de no-wipe), un bug futuro o una corrupción de SQLite podrían perder
# datos. Mantener N snapshots rotativos es una red de seguridad barata.
# ─────────────────────────────────────────────────────────────────────────────

_BACKUPS_DIR_NAME = ".backups"
_MAX_BACKUPS = 5


def _backups_dir() -> Path:
    d = _get_persistent_base_dir() / _BACKUPS_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _crear_backup_db(motivo: str = "auto") -> None:
    """Crea un snapshot rotativo de la DB antes de operaciones destructivas.

    Mantiene solo los `_MAX_BACKUPS` más recientes para no consumir disco.
    Falla silenciosamente si no hay permisos o disco — no debe bloquear el
    flujo normal de la app.
    """
    try:
        if not DB_FILE.exists() or DB_FILE.stat().st_size == 0:
            return
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"app_eolica_{ts}_{motivo}.db.bak"
        backup_path = _backups_dir() / backup_name
        shutil.copy2(DB_FILE, backup_path)
        # Limpieza rotativa
        backups = sorted(_backups_dir().glob("*.db.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[_MAX_BACKUPS:]:
            try:
                old.unlink()
            except OSError:
                pass
    except Exception:
        # Nunca propagar errores del backup — es defensivo, no crítico
        pass


SCHEMA_VERSION = 3
SCHEMA_VERSION_KEY = "_schema_version"

# Migración v3: la Fase 6 (Exportar y guardar) pasó a ser Fase 7; sus claves
# persistidas cambian de prefijo. WHITELIST exacta — nunca renombrar por
# prefijo: la nueva Fase 6 (Estudios avanzados) usa claves f6_* propias.
_F6_A_F7_KEYS = {
    "f6_bankable_project_name": "f7_bankable_project_name",
    "f6_bankable_autor": "f7_bankable_autor",
    "f6_bankable_cliente": "f7_bankable_cliente",
    "f6_country_code": "f7_country_code",
    "f6_report_lang": "f7_report_lang",
}


def _renombrar_claves_config_f6_a_f7(cur) -> None:
    """Renombra en app_config las claves de la antigua Fase 6 → Fase 7.

    Idempotente: si la clave nueva ya existe, el UPDATE se ignora y el
    DELETE limpia la fila vieja. Se invoca en la migración v3 y también al
    restaurar proyectos (guardados antes de la renumeración reintroducen
    las claves viejas).
    """
    for old, new in _F6_A_F7_KEYS.items():
        cur.execute("UPDATE OR IGNORE app_config SET key = ? WHERE key = ?", (new, old))
        cur.execute("DELETE FROM app_config WHERE key = ?", (old,))


def _aplicar_migraciones_schema() -> None:
    """Sistema de migración versionada.

    Cada vez que se cambie algo del esquema, incrementar SCHEMA_VERSION y
    agregar el branch correspondiente aquí. La versión actual se persiste
    en app_config con la key `_schema_version`.

    Hoy solo registramos la versión; sirve como sentinel para futuros bugs
    del estilo "init me borró los datos" — ahora la condición de seeding
    puede usarla en lugar de COUNT de filas.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT value FROM app_config WHERE key = ?",
            (SCHEMA_VERSION_KEY,),
        )
        row = cur.fetchone()
        current = int(row[0]) if row and row[0] else 0

        if current == SCHEMA_VERSION:
            return

        # Aquí irían migraciones reales en el futuro (1→2, 2→3, etc.)
        # Ejemplo:
        # if current < 2:
        #     cur.execute("ALTER TABLE ... ADD COLUMN ...")

        if current < 3:
            _renombrar_claves_config_f6_a_f7(cur)

        cur.execute(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
            (SCHEMA_VERSION_KEY, str(SCHEMA_VERSION)),
        )
        conn.commit()
    finally:
        conn.close()


def init_db():
    _init_db_once()
    _aplicar_migraciones_schema()
    _seed_empty_curve_if_needed()
    # Backup automático en cada arranque del proceso (cacheado, una sola vez)
    _backup_on_first_init()


@st.cache_resource(show_spinner=False)
def _backup_on_first_init() -> bool:
    """Crea un backup la PRIMERA vez que init_db corre en este proceso.

    Decorado con cache_resource para que solo se ejecute una vez por proceso,
    no en cada rerun de Streamlit. Si la DB acaba de crearse (size pequeño)
    no hace nada — no tiene sentido respaldar una DB vacía.
    """
    _crear_backup_db(motivo="startup")
    return True


@st.cache_data(show_spinner=False)
def _cargar_config_cached(stamp: tuple[int, int, int]) -> dict:
    df = _read_sql_cached("SELECT key, value FROM app_config", (), stamp)
    config = {row["key"]: row["value"] for _, row in df.iterrows()}
    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, value)
    return config


def cargar_config():
    # Devuelve copia defensiva: callers a veces mutan el dict.
    return dict(_cargar_config_cached(_db_cache_stamp()))


def guardar_config_values(values: dict):
    # Diff-check: las páginas llaman esto en cada rerun con los mismos valores.
    # Si nada cambió, NO escribir — una escritura cambia el mtime de la DB e
    # invalida TODO el cache de lecturas (config, curva, NASA, layout), forzando
    # releerlo de SQLite en el siguiente rerun. Saltarla mantiene la app fluida.
    try:
        actual = _cargar_config_cached(_db_cache_stamp())
        cambios = {k: v for k, v in values.items() if str(actual.get(str(k))) != str(v)}
    except Exception:
        cambios = dict(values)
    if not cambios:
        return

    conn = get_connection()
    cur = conn.cursor()

    for key, value in cambios.items():
        cur.execute(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
            (str(key), str(value))
        )

    conn.commit()
    conn.close()
    _clear_cached_reads()


def cargar_tabla_curva():
    df = _read_sql("SELECT fila, velocidad, potencia FROM curva_potencia ORDER BY fila")

    if df.empty:
        return tabla_vacia_curva()

    df = df.rename(columns={
        "velocidad": "Velocidad (m/s)",
        "potencia": "Potencia (W)"
    })

    return df[["Velocidad (m/s)", "Potencia (W)"]].fillna("")


def _df_curva_es_efectivamente_vacio(df) -> bool:
    """Devuelve True si la tabla no tiene ningún valor de POTENCIA > 0.

    La columna de velocidad puede tener placeholders 0..25 sin que eso
    signifique "datos del usuario" (es la curva por defecto vacía). Solo
    importan las potencias: si todas son 0 o vacías, la tabla es vacía.
    """
    if df is None or len(df) == 0:
        return True
    try:
        if "Potencia (W)" in df.columns:
            p_col = "Potencia (W)"
        elif "Potencia (kW)" in df.columns:
            p_col = "Potencia (kW)"
        else:
            return True  # no hay columna de potencia → tabla inválida, tratar como vacía
        p = pd.to_numeric(df[p_col].astype(str).str.replace(",", ".", regex=False), errors="coerce")
        return not (p.fillna(0) > 0).any()
    except Exception:
        return False


def guardar_tabla_curva(df, *, forzar_wipe: bool = False):
    """Persiste la curva de potencia con guard contra wipes accidentales.

    Args:
        df: DataFrame con columnas "Velocidad (m/s)" y "Potencia (W)" (o "kW").
        forzar_wipe: Si True, permite sobrescribir datos no-vacíos con una
            tabla efectivamente vacía. Solo usar desde el botón explícito
            "Limpiar tabla". Por defecto False — el guard rechaza el wipe.

    El guard previene la categoría de bugs que sufrió la app antes (init
    cacheado mal que llamaba a guardar_tabla_curva(tabla_vacia_curva()) en
    cada navegación, borrando datos del usuario).
    """
    # ─ Guard: si el caller intenta guardar una tabla vacía sobre datos
    #   existentes sin forzar, lo bloqueamos.
    if not forzar_wipe and _df_curva_es_efectivamente_vacio(df):
        existente = _read_sql("SELECT COUNT(*) AS n, MAX(CAST(potencia AS REAL)) AS maxp FROM curva_potencia")
        if not existente.empty:
            n_filas = int(existente.iloc[0]["n"] or 0)
            max_p = float(existente.iloc[0]["maxp"] or 0)
            if n_filas > 0 and max_p > 0:
                # Hay datos reales del usuario; no sobreescribir
                return

    # ─ Backup defensivo antes del DELETE
    _crear_backup_db(motivo="pre_guardar_curva")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM curva_potencia")

    datos = []
    for i, row in df.reset_index(drop=True).iterrows():
        velocidad = str(row["Velocidad (m/s)"]).strip()
        potencia = str(row["Potencia (W)"]).strip()
        datos.append((i, velocidad, potencia))

    cur.executemany(
        "INSERT INTO curva_potencia (fila, velocidad, potencia) VALUES (?, ?, ?)",
        datos
    )

    conn.commit()
    conn.close()
    _clear_cached_reads()


def guardar_nasa_hourly(df, latitude, longitude, source, start_date="", end_date=""):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM nasa_hourly")

    columnas_min = ["timestamp", "YEAR", "MO", "DY", "HR", "WS10M", "WS50M", "WD10M", "WD50M"]
    df_in = df.copy()
    for opt in ("T2M", "PS"):
        if opt not in df_in.columns:
            df_in[opt] = np.nan
    df_in = df_in[columnas_min + ["T2M", "PS"]].copy()

    datos = []
    for _, row in df_in.iterrows():
        datos.append((
            str(row["timestamp"]),
            int(row["YEAR"]),
            int(row["MO"]),
            int(row["DY"]),
            int(row["HR"]),
            float(row["WS10M"]) if pd.notna(row["WS10M"]) else None,
            float(row["WS50M"]) if pd.notna(row["WS50M"]) else None,
            float(row["WD10M"]) if pd.notna(row["WD10M"]) else None,
            float(row["WD50M"]) if pd.notna(row["WD50M"]) else None,
            float(latitude),
            float(longitude),
            str(source),
            float(row["T2M"]) if pd.notna(row["T2M"]) else None,
            float(row["PS"]) if pd.notna(row["PS"]) else None,
        ))

    cur.executemany("""
        INSERT INTO nasa_hourly (
            timestamp, YEAR, MO, DY, HR, WS10M, WS50M, WD10M, WD50M, latitude, longitude, source, T2M, PS
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, datos)

    conn.commit()
    conn.close()
    _clear_cached_reads()

    guardar_config_values({
        "nasa_lat": latitude,
        "nasa_lon": longitude,
        "nasa_inicio": start_date,
        "nasa_fin": end_date,
        "nasa_fuente": source
    })


def cargar_nasa_hourly():
    return _read_sql("SELECT * FROM nasa_hourly ORDER BY timestamp")


def guardar_layout_parque(df_layout):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM park_layout")

    datos = []
    df_tmp = df_layout.copy().reset_index(drop=True)

    for i, row in df_tmp.iterrows():
        turbina_id = str(row["turbina_id"]).strip()
        x_m = float(row["x_m"])
        y_m = float(row["y_m"])
        datos.append((i, turbina_id, x_m, y_m))

    cur.executemany(
        "INSERT INTO park_layout (fila, turbina_id, x_m, y_m) VALUES (?, ?, ?, ?)",
        datos
    )

    conn.commit()
    conn.close()
    _clear_cached_reads()


def cargar_layout_parque():
    df = _read_sql("SELECT fila, turbina_id, x_m, y_m FROM park_layout ORDER BY fila")

    if df.empty:
        return pd.DataFrame(columns=["turbina_id", "x_m", "y_m"])

    return df[["turbina_id", "x_m", "y_m"]].copy()


# B2 - Torre meteorológica
def guardar_mast_data(df, source_file=""):
    if df is None or len(df) == 0:
        return
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM mast_data")
    datos = []
    for _, row in df.iterrows():
        datos.append((
            str(row["timestamp"]),
            float(row["ws_10min"]) if pd.notna(row.get("ws_10min")) else None,
            float(row["ws_std"]) if pd.notna(row.get("ws_std")) else None,
            float(row["wd_10min"]) if pd.notna(row.get("wd_10min")) else None,
            float(row["altura_sensor"]) if pd.notna(row.get("altura_sensor")) else None,
            float(row["temp_c"]) if pd.notna(row.get("temp_c")) else None,
            str(source_file),
            None,
        ))
    cur.executemany("""
        INSERT INTO mast_data (timestamp, ws_10min, ws_std, wd_10min, altura_sensor, temp_c, source_file, sector)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, datos)
    conn.commit()
    conn.close()
    _clear_cached_reads()


def cargar_mast_data():
    return _read_sql("SELECT timestamp, ws_10min, ws_std, wd_10min, altura_sensor, temp_c, source_file, sector FROM mast_data ORDER BY timestamp")


def existe_mast_data():
    df = _read_sql("SELECT COUNT(*) AS n FROM mast_data")
    if df.empty:
        return False
    return int(df.iloc[0]["n"]) > 0


def borrar_mast_data():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM mast_data")
    conn.commit()
    conn.close()
    _clear_cached_reads()


# B6 - Multi-curva potencia
def guardar_power_curve(curve_id, nombre, diametro, potencia_nominal_W, ct, df_curva, created_at=None):
    from datetime import UTC, datetime
    if created_at is None:
        created_at = datetime.now(UTC).isoformat()
    curve_json = df_curva[["Velocidad (m/s)", "Potencia (W)"]].to_json(orient="records") if df_curva is not None and len(df_curva) > 0 else "[]"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO power_curves (curve_id, nombre, diametro, potencia_nominal_W, ct, curve_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (str(curve_id), str(nombre), float(diametro) if diametro else None,
          float(potencia_nominal_W) if potencia_nominal_W else None,
          float(ct) if ct else None, curve_json, created_at))
    conn.commit()
    conn.close()
    _clear_cached_reads()


def cargar_power_curves():
    df = _read_sql("SELECT curve_id, nombre, diametro, potencia_nominal_W, ct, curve_json, created_at FROM power_curves ORDER BY created_at")
    result = {}
    for _, row in df.iterrows():
        try:
            curve_records = json.loads(row["curve_json"] or "[]")
            df_curva = pd.DataFrame(curve_records)
        except Exception:
            df_curva = pd.DataFrame(columns=["Velocidad (m/s)", "Potencia (W)"])
        result[row["curve_id"]] = {
            "nombre": row["nombre"],
            "diametro": row["diametro"],
            "potencia_nominal_W": row["potencia_nominal_W"],
            "ct": row["ct"],
            "df_curva": df_curva,
            "created_at": row["created_at"],
        }
    return result


def eliminar_power_curve(curve_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM power_curves WHERE curve_id = ?", (str(curve_id),))
    conn.commit()
    conn.close()
    _clear_cached_reads()


def asignar_curva_turbina(turbina_id, curve_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE park_layout SET curve_id = ? WHERE turbina_id = ?", (str(curve_id) if curve_id else None, str(turbina_id)))
    conn.commit()
    conn.close()
    _clear_cached_reads()


# B3 - MCP guardar WS_MCP en nasa_hourly
def guardar_ws_mcp(serie_mcp):
    """serie_mcp: pd.Series indexada por timestamp (ISO) con velocidad MCP corregida."""
    if serie_mcp is None or len(serie_mcp) == 0:
        return
    conn = get_connection()
    cur = conn.cursor()
    datos = []
    for ts, val in serie_mcp.items():
        try:
            v = float(val) if pd.notna(val) else None
        except Exception:
            v = None
        datos.append((v, str(ts)))
    cur.executemany("UPDATE nasa_hourly SET WS_MCP = ? WHERE timestamp = ?", datos)
    conn.commit()
    conn.close()
    _clear_cached_reads()


def guardar_escenario_parque(name, df_layout, settings_dict, metrics_dict):
    conn = get_connection()
    cur = conn.cursor()

    layout_json = df_layout.to_json(orient="records")
    settings_json = json.dumps(settings_dict, ensure_ascii=False)
    metrics_json = json.dumps(metrics_dict, ensure_ascii=False)

    cur.execute("""
        INSERT OR REPLACE INTO park_scenarios (
            name, updated_at, layout_json, settings_json, metrics_json
        ) VALUES (?, datetime('now'), ?, ?, ?)
    """, (name, layout_json, settings_json, metrics_json))

    conn.commit()
    conn.close()
    _clear_cached_reads()


def listar_escenarios_parque():
    return _read_sql("SELECT name, updated_at FROM park_scenarios ORDER BY updated_at DESC, name ASC")


def cargar_escenario_parque(name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT name, updated_at, layout_json, settings_json, metrics_json FROM park_scenarios WHERE name = ?",
        (name,)
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        return None

    layout_json = row[2] or "[]"
    settings_json = row[3] or "{}"
    metrics_json = row[4] or "{}"

    try:
        if layout_json.strip() in ["", "[]"]:
            df_layout = pd.DataFrame(columns=["turbina_id", "x_m", "y_m"])
        else:
            df_layout = pd.read_json(io.StringIO(layout_json), orient="records")
    except Exception:
        df_layout = pd.DataFrame(columns=["turbina_id", "x_m", "y_m"])

    settings = json.loads(settings_json)
    metrics = json.loads(metrics_json)

    return {
        "name": row[0],
        "updated_at": row[1],
        "layout": df_layout,
        "settings": settings,
        "metrics": metrics,
    }


def eliminar_escenario_parque(name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM park_scenarios WHERE name = ?", (name,))
    conn.commit()
    conn.close()
    _clear_cached_reads()


def exportar_proyecto_actual():
    config_df = _read_sql("SELECT key, value FROM app_config")
    curva_df = _read_sql("SELECT fila, velocidad, potencia FROM curva_potencia ORDER BY fila")
    nasa_df = _read_sql("SELECT * FROM nasa_hourly ORDER BY timestamp")
    layout_df = _read_sql("SELECT fila, turbina_id, x_m, y_m FROM park_layout ORDER BY fila")
    escenarios_df = _read_sql("SELECT * FROM park_scenarios ORDER BY updated_at DESC, name ASC")

    project_data = {
        "app_config": config_df.to_dict(orient="records"),
        "curva_potencia": curva_df.to_dict(orient="records"),
        "nasa_hourly": nasa_df.to_dict(orient="records"),
        "park_layout": layout_df.to_dict(orient="records"),
        "park_scenarios": escenarios_df.to_dict(orient="records"),
    }
    return project_data


def guardar_proyecto(nombre_proyecto):
    if not str(nombre_proyecto).strip():
        raise ValueError("Debe escribir un nombre de proyecto.")

    project_data = exportar_proyecto_actual()
    project_json = json.dumps(project_data, ensure_ascii=False)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO saved_projects (name, updated_at, project_json)
        VALUES (?, datetime('now'), ?)
    """, (str(nombre_proyecto).strip(), project_json))
    conn.commit()
    conn.close()
    _clear_cached_reads()


def listar_proyectos_guardados():
    return _read_sql("SELECT name, updated_at FROM saved_projects ORDER BY updated_at DESC, name ASC")


def cargar_proyecto(nombre_proyecto):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT project_json FROM saved_projects WHERE name = ?",
        (str(nombre_proyecto).strip(),)
    )
    row = cur.fetchone()

    if row is None:
        conn.close()
        raise ValueError("No se encontró el proyecto seleccionado.")

    project_data = json.loads(row[0])

    cur.execute("DELETE FROM app_config")
    cur.execute("DELETE FROM curva_potencia")
    cur.execute("DELETE FROM nasa_hourly")
    cur.execute("DELETE FROM park_layout")
    cur.execute("DELETE FROM park_scenarios")

    for item in project_data.get("app_config", []):
        cur.execute(
            "INSERT INTO app_config (key, value) VALUES (?, ?)",
            (item["key"], item["value"])
        )

    for item in project_data.get("curva_potencia", []):
        cur.execute(
            "INSERT INTO curva_potencia (fila, velocidad, potencia) VALUES (?, ?, ?)",
            (item["fila"], item["velocidad"], item["potencia"])
        )

    for item in project_data.get("nasa_hourly", []):
        cur.execute("""
            INSERT INTO nasa_hourly (
                timestamp, YEAR, MO, DY, HR, WS10M, WS50M, WD10M, WD50M, latitude, longitude, source, T2M, PS, WS_MCP
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("timestamp"),
            item.get("YEAR"),
            item.get("MO"),
            item.get("DY"),
            item.get("HR"),
            item.get("WS10M"),
            item.get("WS50M"),
            item.get("WD10M"),
            item.get("WD50M"),
            item.get("latitude"),
            item.get("longitude"),
            item.get("source"),
            item.get("T2M"),
            item.get("PS"),
            item.get("WS_MCP"),
        ))

    for item in project_data.get("park_layout", []):
        cur.execute(
            "INSERT INTO park_layout (fila, turbina_id, x_m, y_m) VALUES (?, ?, ?, ?)",
            (item["fila"], item["turbina_id"], item["x_m"], item["y_m"])
        )

    for item in project_data.get("park_scenarios", []):
        cur.execute("""
            INSERT INTO park_scenarios (name, updated_at, layout_json, settings_json, metrics_json)
            VALUES (?, ?, ?, ?, ?)
        """, (
            item.get("name"),
            item.get("updated_at"),
            item.get("layout_json"),
            item.get("settings_json"),
            item.get("metrics_json"),
        ))

    # Proyectos guardados antes de la renumeración traen claves f6_* viejas.
    _renombrar_claves_config_f6_a_f7(cur)

    conn.commit()
    conn.close()
    _clear_cached_reads()

    config = cargar_config()
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            guardar_config_values({key: value})


def eliminar_proyecto(nombre_proyecto):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM saved_projects WHERE name = ?", (str(nombre_proyecto).strip(),))
    conn.commit()
    conn.close()
    _clear_cached_reads()


def exportar_proyecto_json_texto():
    return json.dumps(exportar_proyecto_actual(), ensure_ascii=False, indent=2)


def importar_proyecto_desde_json_texto(json_texto):
    project_data = json.loads(json_texto)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM app_config")
    cur.execute("DELETE FROM curva_potencia")
    cur.execute("DELETE FROM nasa_hourly")
    cur.execute("DELETE FROM park_layout")
    cur.execute("DELETE FROM park_scenarios")

    for item in project_data.get("app_config", []):
        cur.execute(
            "INSERT INTO app_config (key, value) VALUES (?, ?)",
            (item["key"], item["value"])
        )

    for item in project_data.get("curva_potencia", []):
        cur.execute(
            "INSERT INTO curva_potencia (fila, velocidad, potencia) VALUES (?, ?, ?)",
            (item["fila"], item["velocidad"], item["potencia"])
        )

    for item in project_data.get("nasa_hourly", []):
        cur.execute("""
            INSERT INTO nasa_hourly (
                timestamp, YEAR, MO, DY, HR, WS10M, WS50M, WD10M, WD50M, latitude, longitude, source, T2M, PS, WS_MCP
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("timestamp"),
            item.get("YEAR"),
            item.get("MO"),
            item.get("DY"),
            item.get("HR"),
            item.get("WS10M"),
            item.get("WS50M"),
            item.get("WD10M"),
            item.get("WD50M"),
            item.get("latitude"),
            item.get("longitude"),
            item.get("source"),
            item.get("T2M"),
            item.get("PS"),
            item.get("WS_MCP"),
        ))

    for item in project_data.get("park_layout", []):
        cur.execute(
            "INSERT INTO park_layout (fila, turbina_id, x_m, y_m) VALUES (?, ?, ?, ?)",
            (item["fila"], item["turbina_id"], item["x_m"], item["y_m"])
        )

    for item in project_data.get("park_scenarios", []):
        cur.execute("""
            INSERT INTO park_scenarios (name, updated_at, layout_json, settings_json, metrics_json)
            VALUES (?, ?, ?, ?, ?)
        """, (
            item.get("name"),
            item.get("updated_at"),
            item.get("layout_json"),
            item.get("settings_json"),
            item.get("metrics_json"),
        ))

    # Proyectos exportados antes de la renumeración traen claves f6_* viejas.
    _renombrar_claves_config_f6_a_f7(cur)

    conn.commit()
    conn.close()
    _clear_cached_reads()

    config = cargar_config()
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            guardar_config_values({key: value})
