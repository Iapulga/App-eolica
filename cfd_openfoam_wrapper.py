"""CFD OpenFOAM wrapper — subprocess Docker o nativo.

USUARIO PROVEE CLUSTER. Yo solo genero estructura caso + invoco subprocess.
Tiempo cómputo típico: 6-24h por dirección viento sobre 8-32 cores.

Requiere: OpenFOAM v2306+ (nativo Linux/WSL2 o Docker `opencfd/openfoam-default`).
Si no detectado → wrapper marca como N/A.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import numpy as np


def openfoam_disponible():
    """Detecta OpenFOAM: WM_PROJECT env var (nativo) o `docker` con imagen."""
    # Nativo
    if os.environ.get("WM_PROJECT") or shutil.which("simpleFoam"):
        return {"backend": "native", "exe": shutil.which("simpleFoam") or "simpleFoam"}
    # Docker
    if shutil.which("docker"):
        try:
            res = subprocess.run(["docker", "images", "-q", "opencfd/openfoam-default"],
                                  capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                return {"backend": "docker", "image": "opencfd/openfoam-default"}
        except Exception:
            pass
    return None


CONTROLDICT_TEMPLATE = """\
FoamFile {{ version 2.0; format ascii; class dictionary; object controlDict; }}
application     simpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time};
deltaT          1;
writeControl    timeStep;
writeInterval   {write_interval};
purgeWrite      2;
writeFormat     ascii;
writePrecision  6;
runTimeModifiable true;
"""


def _crear_estructura_caso(case_dir, end_time=1000, write_interval=200):
    """Crea estructura mínima OpenFOAM (0/, constant/, system/)."""
    for sub in ("0", "constant", "system", "constant/polyMesh"):
        os.makedirs(os.path.join(case_dir, sub), exist_ok=True)
    # controlDict
    with open(os.path.join(case_dir, "system", "controlDict"), "w") as f:
        f.write(CONTROLDICT_TEMPLATE.format(end_time=end_time, write_interval=write_interval))
    # fvSchemes mínimo
    with open(os.path.join(case_dir, "system", "fvSchemes"), "w") as f:
        f.write("""FoamFile { version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes { default none; div(phi,U) bounded Gauss upwind; div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind; div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
""")
    # fvSolution mínimo
    with open(os.path.join(case_dir, "system", "fvSolution"), "w") as f:
        f.write("""FoamFile { version 2.0; format ascii; class dictionary; object fvSolution; }
solvers { p { solver GAMG; tolerance 1e-6; relTol 0.01; smoother GaussSeidel; } U|k|omega { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-7; relTol 0.1; } }
SIMPLE { nNonOrthogonalCorrectors 0; consistent true; residualControl { p 1e-3; U 1e-4; k 1e-4; omega 1e-4; } }
relaxationFactors { fields { p 0.3; } equations { U 0.7; k 0.7; omega 0.7; } }
""")
    # turbulenceProperties k-omega-SST
    with open(os.path.join(case_dir, "constant", "turbulenceProperties"), "w") as f:
        f.write("""FoamFile { version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType RAS;
RAS { RASModel kOmegaSST; turbulence on; printCoeffs on; }
""")
    # transportProperties (Newtonian air)
    with open(os.path.join(case_dir, "constant", "transportProperties"), "w") as f:
        f.write("""FoamFile { version 2.0; format ascii; class dictionary; object transportProperties; }
transportModel Newtonian;
nu              [0 2 -1 0 0 0 0] 1.5e-05;
""")


def generar_caso_openfoam(
    dem_path,
    wind_speed_input_ms,
    wind_direction_input_deg,
    output_case_dir,
    mesh_resolution_m=100,
    h_hub=80.0,
    end_time=1000,
):
    """Genera caso OpenFOAM listo para ejecutar.

    NOTA: generación mesh desde DEM requiere snappyHexMesh + STL.
    Esta función crea ESTRUCTURA esqueleto. Usuario refina mesh manual o
    usa preprocessing externo (Salome, ParaView).
    """
    os.makedirs(output_case_dir, exist_ok=True)
    _crear_estructura_caso(output_case_dir, end_time=end_time)

    # BC iniciales en 0/
    u_x = float(wind_speed_input_ms) * np.sin(np.deg2rad(float(wind_direction_input_deg) + 180))
    u_y = float(wind_speed_input_ms) * np.cos(np.deg2rad(float(wind_direction_input_deg) + 180))
    u_z = 0.0
    with open(os.path.join(output_case_dir, "0", "U"), "w") as f:
        f.write(f"""FoamFile {{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions      [0 1 -1 0 0 0 0];
internalField   uniform ({u_x:.3f} {u_y:.3f} {u_z:.3f});
boundaryField {{ inlet {{ type fixedValue; value uniform ({u_x:.3f} {u_y:.3f} {u_z:.3f}); }} outlet {{ type zeroGradient; }} top {{ type slip; }} ground {{ type noSlip; }} sides {{ type slip; }} }}
""")
    # p, k, omega placeholder
    with open(os.path.join(output_case_dir, "0", "p"), "w") as f:
        f.write("""FoamFile { version 2.0; format ascii; class volScalarField; object p; }
dimensions [0 2 -2 0 0 0 0]; internalField uniform 0;
boundaryField { inlet { type zeroGradient; } outlet { type fixedValue; value uniform 0; } top { type slip; } ground { type zeroGradient; } sides { type slip; } }
""")
    TI = 0.10
    k_val = 1.5 * (TI * wind_speed_input_ms) ** 2
    omega_val = k_val ** 0.5 / 0.4 / max(h_hub, 1)  # rough estimate
    with open(os.path.join(output_case_dir, "0", "k"), "w") as f:
        f.write(f"""FoamFile {{ version 2.0; format ascii; class volScalarField; object k; }}
dimensions [0 2 -2 0 0 0 0]; internalField uniform {k_val:.4f};
boundaryField {{ inlet {{ type fixedValue; value uniform {k_val:.4f}; }} outlet {{ type zeroGradient; }} top {{ type slip; }} ground {{ type kqRWallFunction; value uniform {k_val:.4f}; }} sides {{ type slip; }} }}
""")
    with open(os.path.join(output_case_dir, "0", "omega"), "w") as f:
        f.write(f"""FoamFile {{ version 2.0; format ascii; class volScalarField; object omega; }}
dimensions [0 0 -1 0 0 0 0]; internalField uniform {omega_val:.4f};
boundaryField {{ inlet {{ type fixedValue; value uniform {omega_val:.4f}; }} outlet {{ type zeroGradient; }} top {{ type slip; }} ground {{ type omegaWallFunction; value uniform {omega_val:.4f}; }} sides {{ type slip; }} }}
""")
    with open(os.path.join(output_case_dir, "0", "nut"), "w") as f:
        f.write("""FoamFile { version 2.0; format ascii; class volScalarField; object nut; }
dimensions [0 2 -1 0 0 0 0]; internalField uniform 0;
boundaryField { inlet { type calculated; value uniform 0; } outlet { type calculated; value uniform 0; } top { type slip; } ground { type nutkWallFunction; value uniform 0; } sides { type slip; } }
""")

    readme_path = os.path.join(output_case_dir, "README_SMA.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(f"""# Caso OpenFOAM generado por SMA 2.0

DEM: {dem_path}
Wind: {wind_speed_input_ms} m/s @ {wind_direction_input_deg}°
Hub height: {h_hub} m
Mesh resolution: {mesh_resolution_m} m

## Pasos manuales pendientes

1. Convertir DEM ({dem_path}) a STL del terreno:
   - Usar `gdal_translate`, ParaView o Salome.
   - Salida: `constant/triSurface/terrain.stl`

2. Generar mesh con snappyHexMesh:
   ```
   blockMesh
   snappyHexMesh -overwrite
   ```

3. Ejecutar solver:
   ```
   decomposePar              # Si paralelo
   mpirun -np 8 simpleFoam -parallel
   reconstructPar
   ```

4. Post-procesar:
   ```
   sample        # Extrae perfil vertical en puntos de turbina
   paraFoam      # Visualización
   ```

5. Importar resultados de vuelta a SMA via UI Fase 2 → Botón "Importar resultados CFD".
""")

    return {
        "case_dir": output_case_dir,
        "readme": readme_path,
        "wind_input": {"speed_ms": wind_speed_input_ms, "direction_deg": wind_direction_input_deg},
    }


def ejecutar_cfd_subprocess(case_dir, n_cores=8, timeout_h=24, use_docker=True):
    """Lanza OpenFOAM solver. Returns dict con returncode + stdout/stderr."""
    backend = openfoam_disponible()
    if backend is None:
        raise RuntimeError("OpenFOAM no detectado. Instalar nativo o Docker `opencfd/openfoam-default`.")

    timeout_s = int(timeout_h) * 3600

    if backend["backend"] == "docker" and use_docker:
        case_abs = os.path.abspath(case_dir)
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{case_abs}:/case",
            "-w", "/case",
            backend["image"],
            "bash", "-c",
            "source /opt/openfoam*/etc/bashrc && blockMesh && simpleFoam"
        ]
    else:
        cmd = ["simpleFoam", "-case", case_dir]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        return {
            "returncode": res.returncode,
            "stdout": res.stdout[-2000:],
            "stderr": res.stderr[-2000:],
            "ok": res.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "ok": False, "stderr": f"Timeout {timeout_h}h excedido"}


def parsear_resultados_cfd_punto(case_dir, x_m, y_m, z_m_hub=80):
    """Extrae U_eff en un punto del dominio (x,y,z hub).
    Requiere OpenFOAM tools sample, foamLog o paraview. Aprox: lee último timestep como ASCII.
    """
    # Encuentra último timestep dir
    case_path = Path(case_dir)
    time_dirs = [d for d in case_path.iterdir() if d.is_dir() and d.name.replace(".", "").isdigit()]
    if not time_dirs:
        return None
    last_time = max(time_dirs, key=lambda d: float(d.name))
    u_file = last_time / "U"
    if not u_file.exists():
        return None
    # Placeholder: real parsing requiere parser OpenFOAM format
    # Para MVP: devuelve mensaje
    return {
        "case": str(case_dir),
        "last_time": last_time.name,
        "U_file": str(u_file),
        "warning": "Parser OpenFOAM ASCII no implementado MVP. Usar paraFoam o pyvista.",
    }
