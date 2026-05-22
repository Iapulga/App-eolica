"""Performance instrumentation helpers.

Lightweight `timed()` context manager used to log timing of key code paths
to the console (`[PERF] label: N.N ms`) and to `st.session_state["_perf"]`
so a sidebar debug panel can read it. Zero cost when not entered.
"""
import time
from contextlib import contextmanager

import streamlit as st


@contextmanager
def timed(label: str):
    """Time a block of code. Prints to stdout + appends to session_state['_perf']."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000.0
        try:
            st.session_state.setdefault("_perf", []).append((label, ms))
        except Exception:
            pass
        print(f"[PERF] {label}: {ms:.1f} ms")
