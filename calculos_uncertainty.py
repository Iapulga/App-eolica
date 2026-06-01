"""Incertidumbre IEC 61400-15-2 + Monte Carlo P50/P75/P90/P99.

Modelo combinado:
    sigma_total = sqrt(sum sigma_i^2)
    Categorias estandar:
      A: medicion y adquisicion         (default 3.0 %)
      B: long-term & climate            (default 4.5 %)
      C: extrapolacion vertical         (default 2.0 %)
      D: modelado de flujo y wake       (default 4.0 %)
      E: plant performance / disp.      (default 3.0 %)

Pcrit = AEP_mu * (1 - z(p) * sigma_total/100)
con z(p) = norma estandar inversa (P50=0, P75=0.6745, P90=1.2816, P99=2.3263)
"""

from __future__ import annotations

import math

DEFAULT_SIGMAS_PCT = {
    "meas":  3.0,
    "lt":    4.5,
    "vert":  2.0,
    "flow":  4.0,
    "plant": 3.0,
    "pcv":   1.5,   # IEC 61400-12-1 power curve verification (opt-in)
}

CATEGORY_LABELS = {
    "meas":  "A - Medicion y adquisicion",
    "lt":    "B - Long-term & climate",
    "vert":  "C - Extrapolacion vertical",
    "flow":  "D - Modelado de flujo y wake",
    "plant": "E - Plant performance",
    "pcv":   "F - Power curve verification (IEC 61400-12-1)",
}

PERCENTIL_Z = {
    "P50": 0.0,
    "P75": 0.6745,
    "P90": 1.2816,
    "P99": 2.3263,
}


def combined_sigma_pct(sigmas_pct: dict[str, float] | None = None) -> float:
    """sigma combinado = sqrt(sum sigma_i^2). Acepta dict parcial."""
    s = dict(DEFAULT_SIGMAS_PCT)
    if isinstance(sigmas_pct, dict):
        for k, v in sigmas_pct.items():
            try:
                f = float(v)
                if math.isfinite(f) and f >= 0:
                    s[k] = f
            except (TypeError, ValueError):
                continue
    return math.sqrt(sum(v * v for v in s.values()))


def percentiles_gaussian(aep_mu: float, sigmas_pct: dict[str, float] | None = None) -> dict:
    """Calcula P50/P75/P90/P99 usando Gaussiana cerrada (sin MC).

    Para uso rapido y reproducible. Devuelve dict con percentiles + sigma_total + categorias.
    """
    sigma_total = combined_sigma_pct(sigmas_pct)
    pct = sigma_total / 100.0
    out = {
        "sigma_total_pct": sigma_total,
        "P50": aep_mu,
        "P75": aep_mu * (1 - PERCENTIL_Z["P75"] * pct),
        "P90": aep_mu * (1 - PERCENTIL_Z["P90"] * pct),
        "P99": aep_mu * (1 - PERCENTIL_Z["P99"] * pct),
    }
    base = dict(DEFAULT_SIGMAS_PCT)
    if isinstance(sigmas_pct, dict):
        base.update({k: float(v) for k, v in sigmas_pct.items() if v is not None})
    out["categorias_pct"] = base
    out["categorias_labels"] = CATEGORY_LABELS
    return out


def monte_carlo_aep(aep_mu: float, sigmas_pct: dict[str, float] | None = None, n_iter: int = 10000, seed: int | None = 42) -> dict:
    """Monte Carlo Gaussiano para AEP. Devuelve P50/P75/P90/P99 + media MC + std MC.

    Si numpy no esta disponible, cae a percentiles_gaussian().
    """
    try:
        import numpy as np
    except ImportError:
        return percentiles_gaussian(aep_mu, sigmas_pct)

    sigma_total = combined_sigma_pct(sigmas_pct)
    if seed is not None:
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng()
    samples = rng.normal(loc=aep_mu, scale=aep_mu * sigma_total / 100.0, size=int(max(100, n_iter)))
    out = {
        "sigma_total_pct": float(sigma_total),
        "mc_mean": float(np.mean(samples)),
        "mc_std": float(np.std(samples)),
        "P50": float(np.percentile(samples, 50)),
        "P75": float(np.percentile(samples, 25)),
        "P90": float(np.percentile(samples, 10)),
        "P99": float(np.percentile(samples, 1)),
        "n_iter": int(len(samples)),
    }
    base = dict(DEFAULT_SIGMAS_PCT)
    if isinstance(sigmas_pct, dict):
        base.update({k: float(v) for k, v in sigmas_pct.items() if v is not None})
    out["categorias_pct"] = base
    out["categorias_labels"] = CATEGORY_LABELS
    return out


def air_density_correction(v_ms: float, rho_site: float, rho_ref: float = 1.225) -> float:
    """IEC 61400-12-1 Ed.3 Eq.4 — correccion vel para curva potencia ref.

    V_norm = V * (rho_site / rho_ref) ** (1/3)
    Usar para reescalar velocidad horaria del sitio antes de aplicar curva ref @ 1.225 kg/m3.
    """
    try:
        v = float(v_ms)
        rs = float(rho_site)
        rr = float(rho_ref) if rho_ref else 1.225
        if rs <= 0 or rr <= 0:
            return v
        return v * (rs / rr) ** (1.0 / 3.0)
    except (TypeError, ValueError):
        return float("nan")


def aep_uncertainty_pcv(aep_mwh: float, ce_pct: float = 1.5) -> dict:
    """Categoria F — Power Curve Verification segun IEC 61400-12-1.

    Args:
        aep_mwh: AEP base.
        ce_pct: tolerancia categoria del fabricante (default 1.5% Cat A IEC).

    Returns:
        dict con incertidumbre absoluta + relativa.
    """
    try:
        a = float(aep_mwh)
        c = float(ce_pct)
        return {
            "aep_mwh": a,
            "ce_pct": c,
            "sigma_aep_abs_mwh": a * c / 100.0,
        }
    except (TypeError, ValueError):
        return {"aep_mwh": float("nan"), "ce_pct": float("nan"), "sigma_aep_abs_mwh": float("nan")}


__all__ = [
    "DEFAULT_SIGMAS_PCT",
    "CATEGORY_LABELS",
    "PERCENTIL_Z",
    "combined_sigma_pct",
    "percentiles_gaussian",
    "monte_carlo_aep",
    "air_density_correction",
    "aep_uncertainty_pcv",
]
