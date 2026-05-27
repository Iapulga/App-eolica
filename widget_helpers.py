"""
Helper functions for consistent widget state management in Streamlit.

This module provides utilities to ensure:
1. Stable widget keys across reruns
2. Proper session_state initialization before widget creation
3. No conflicts between visual widget state and persisted database values
4. Single-click/input registration (no double-clicking needed)

Pattern usage:
    # At the top of each phase
    _init_widget_state(key, default_from_db)
    
    # Create widget with key
    value = st.number_input(..., key=key, ...)
    
    # Use the value directly - it's already in session_state
    # Save only when user explicitly clicks "Save"
"""

import streamlit as st


def _init_widget_state(key, value):
    """
    Initialize a session_state key with a value if it doesn't exist.
    
    Should be called BEFORE creating the widget that uses this key.
    
    Args:
        key: The session_state key (must match widget's key parameter)
        value: Default value from database or configuration
    """
    if key not in st.session_state:
        st.session_state[key] = value


def _init_widget_state_batch(config_dict):
    """
    Initialize multiple session_state keys at once.
    
    Args:
        config_dict: Dict of {key: default_value} pairs
    """
    for key, value in config_dict.items():
        _init_widget_state(key, value)


def _safe_index(options, value, default_index=0):
    """
    Safely find the index of a value in a list, with fallback.
    
    Use this for selectbox 'index=' parameter to avoid crashes
    when the value is not in the options list.
    
    Args:
        options: List of available options
        value: Value to find
        default_index: Index to return if value not found
        
    Returns:
        The index of value in options, or default_index
    """
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return default_index


def _get_widget_value(key, default=None):
    """
    Get the current value of a widget from session_state.
    
    Use this when you need to read the widget value for calculations
    instead of using a local variable.
    
    Args:
        key: The session_state key
        default: Fallback value if key doesn't exist
        
    Returns:
        The value from session_state, or default
    """
    return st.session_state.get(key, default)


def _sync_widget_to_db(key, config_key_mapping):
    """
    Sync a widget's current value to the database via guardar_config_values.
    
    Call this in a button callback when you want to save changes.
    
    Args:
        key: The session_state key of the widget
        config_key_mapping: Dict of {db_key: session_state_key} or just {db_key: key}
                           if they're the same
    
    Example:
        # In a "Save parameters" button callback
        _sync_widget_to_db("f3_modelo", {"f3_modelo_altura": "f3_modelo"})
    """
    from db import guardar_config_values

    values_to_save = {}
    for db_key, ss_key in config_key_mapping.items():
        value = st.session_state.get(ss_key)
        if value is not None:
            values_to_save[db_key] = value

    if values_to_save:
        guardar_config_values(values_to_save)


def _create_number_input_stable(label, min_value=None, max_value=None, step=1.0, format="%.2f",
                                 key=None, config_db_key=None, config_fallback_keys=None,
                                 default=None, on_change=None):
    """
    Create a st.number_input with stable state management.
    
    Automatically initializes session_state from database if needed.
    
    Args:
        label: Widget label
        min_value, max_value, step, format: st.number_input parameters
        key: Session state key (must be stable)
        config_db_key: Primary database config key to load from
        config_fallback_keys: List of fallback keys if primary not found
        default: Fallback default if no config found
        on_change: Callback function (note: this gets called after widget update)
        
    Returns:
        The current value of the number input
    """
    if key is None:
        raise ValueError("key parameter is required for stable state management")

    # Initialize from config if first time
    if key not in st.session_state and (config_db_key or config_fallback_keys or default is not None):
        from db import cargar_config
        config = cargar_config()

        value = None
        if config_db_key and config_db_key in config:
            value = config[config_db_key]
        elif config_fallback_keys:
            for fallback_key in config_fallback_keys:
                if fallback_key in config:
                    value = config[fallback_key]
                    break

        try:
            _init_widget_state(key, float(value) if value not in [None, ""] else (float(default) if default is not None else 0.0))
        except (ValueError, TypeError):
            _init_widget_state(key, float(default) if default is not None else 0.0)

    # Create widget - value from session_state because key is stable
    return st.number_input(
        label,
        min_value=min_value,
        max_value=max_value,
        step=step,
        format=format,
        key=key,
        on_change=on_change
    )


def _create_selectbox_stable(label, options, key=None, config_db_key=None, config_fallback_keys=None,
                              default=None, on_change=None):
    """
    Create a st.selectbox with stable state management.
    
    Automatically initializes session_state from database if needed.
    
    Args:
        label: Widget label
        options: List of options
        key: Session state key (must be stable)
        config_db_key: Primary database config key to load from
        config_fallback_keys: List of fallback keys if primary not found
        default: Fallback default if no config found
        on_change: Callback function
        
    Returns:
        The selected value
    """
    if key is None:
        raise ValueError("key parameter is required for stable state management")

    # Initialize from config if first time
    if key not in st.session_state and (config_db_key or config_fallback_keys or default is not None):
        from db import cargar_config
        config = cargar_config()

        value = None
        if config_db_key and config_db_key in config:
            value = config[config_db_key]
        elif config_fallback_keys:
            for fallback_key in config_fallback_keys:
                if fallback_key in config:
                    value = config[fallback_key]
                    break

        final_value = value if value not in [None, ""] else default
        if final_value and final_value not in options:
            final_value = default if default in options else options[0]

        _init_widget_state(key, final_value if final_value in options else options[0])

    # Find the index for display
    current_value = st.session_state.get(key, options[0] if options else None)
    index = _safe_index(options, current_value, 0)

    # Create widget - uses session_state but we override index for initial display
    return st.selectbox(
        label,
        options,
        index=index,
        key=key,
        on_change=on_change
    )


def _create_checkbox_stable(label, key=None, config_db_key=None, config_fallback_keys=None,
                            default=False, on_change=None):
    """
    Create a st.checkbox with stable state management.
    
    Args:
        label: Widget label
        key: Session state key (must be stable)
        config_db_key: Primary database config key to load from
        config_fallback_keys: List of fallback keys if primary not found
        default: Fallback default if no config found
        on_change: Callback function
        
    Returns:
        The checkbox value (True/False)
    """
    if key is None:
        raise ValueError("key parameter is required for stable state management")

    # Initialize from config if first time
    if key not in st.session_state and (config_db_key or config_fallback_keys):
        from db import cargar_config
        config = cargar_config()

        value = False
        if config_db_key and config_db_key in config:
            value = str(config[config_db_key]).lower() == "true"
        elif config_fallback_keys:
            for fallback_key in config_fallback_keys:
                if fallback_key in config:
                    value = str(config[fallback_key]).lower() == "true"
                    break
        else:
            value = default

        _init_widget_state(key, value)

    return st.checkbox(
        label,
        key=key,
        on_change=on_change
    )


def _ensure_project_change(project_name_key="project_name"):
    """
    Check if the project has changed and invalidate widget state if needed.
    
    Use this at the beginning of a phase to detect project switches.
    Call this ONCE at module level, not inside conditional blocks.
    
    Example:
        _ensure_project_change("project_name")
        # Then initialize widgets
    
    Args:
        project_name_key: The config key that identifies the current project
    """
    from db import cargar_config

    config = cargar_config()
    current_project = config.get(project_name_key, "default")

    ss_key = f"_last_project_{project_name_key}"
    if ss_key not in st.session_state:
        st.session_state[ss_key] = current_project
    elif st.session_state[ss_key] != current_project:
        # Project changed - optionally invalidate widget states here
        st.session_state[ss_key] = current_project


# Example usage in a phase:
"""
# At the top of a phase file

from widget_helpers import (
    _init_widget_state,
    _init_widget_state_batch,
    _create_number_input_stable,
    _create_selectbox_stable,
    _create_checkbox_stable,
    _ensure_project_change,
)

# Detect project changes
_ensure_project_change()

# Create stable widgets:
altura = _create_number_input_stable(
    "Altura deseada (m)",
    min_value=0.10,
    step=0.10,
    format="%.2f",
    key="f3_altura_deseada",
    config_db_key="perfil_hhub",
    config_fallback_keys=["f2_altura_deseada"],
    default=80.0
)

modelo = _create_selectbox_stable(
    "Modelo",
    MODEL_OPTIONS,
    key="f3_modelo",
    config_db_key="f3_modelo_altura",
    default="Exponencial"
)

# When user clicks "Save":
def guardar_parametros():
    from db import guardar_config_values
    guardar_config_values({
        "f3_altura_deseada": st.session_state["f3_altura_deseada"],
        "f3_modelo_altura": st.session_state["f3_modelo"],
    })

st.button("Guardar", on_click=guardar_parametros)
"""
