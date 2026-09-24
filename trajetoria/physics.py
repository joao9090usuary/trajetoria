"""Point-mass educational flight model. SI units; ENU coordinate frame."""

from dataclasses import asdict, dataclass, fields, field
import math

G = 9.80665


@dataclass(frozen=True)
class Config:
    dry_mass: float = 0.35
    propellant_mass: float = 0.08
    thrust: float = 12.0
    burn_time: float = 2.0
    diameter: float = 0.05
    drag_coefficient: float = 0.55
    elevation: float = 85.0
    azimuth: float = 30.0
    wind_east: float = 2.0
    wind_north: float = 0.5
    air_density: float = 1.225
    time_step: float = 0.02
    max_time: float = 120.0
    motor_mode: str = "constant"
    thrust_curve: list = field(default_factory=list)
    recovery_enabled: bool = False
    recovery_trigger: str = "apogee"
    recovery_delay: float = 0.0
    recovery_inflation: float = 1.0
    recovery_area: float = 0.3
    recovery_cd: float = 1.5
    recovery_altitude: float = 50.0
    recovery_time: float = 5.0

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("A configuração deve ser um objeto JSON.")
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError("Parâmetros desconhecidos: " + ", ".join(sorted(unknown)))
        for key, value in data.items():
            if key in ("motor_mode", "recovery_trigger"):
                if not isinstance(value, str):
                    raise ValueError(f"{key}: use uma string.")
            elif key == "thrust_curve":
                if not isinstance(value, list):
                    raise ValueError(f"{key}: use uma lista.")
            elif key == "recovery_enabled":
                if not isinstance(value, bool):
                    raise ValueError("recovery_enabled: use verdadeiro ou falso.")
            elif isinstance(value, bool) or not isinstance(value, (float, int)):
                raise ValueError(f"{key}: use um número finito.")
        cfg = cls(**data)
        cfg.validate()
        return cfg

    def validate(self):
        bounds = {
            "dry_mass": (0.01, 100), "propellant_mass": (0.001, 100),
            "thrust": (0, 10000), "burn_time": (0.01, 100),
            "diameter": (0.01, 1.0), "drag_coefficient": (0, 2),
            "elevation": (60, 90), "azimuth": (0, 360),
            "wind_east": (-30, 30), "wind_north": (-30, 30),
            "air_density": (0, 1.5), "time_step": (0.001, 0.1),
            "max_time": (10, 1000),
            "recovery_delay": (0, 60), "recovery_inflation": (0.01, 30),
            "recovery_area": (0.001, 20), "recovery_cd": (0.1, 3),
            "recovery_altitude": (0, 10000), "recovery_time": (0, 180),
        }
        for key, (low, high) in bounds.items():
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{key}: valor entre {low} e {high}.")
        if self.motor_mode not in ("constant", "curve"):
            raise ValueError("motor_mode deve ser 'constant' ou 'curve'.")
        if self.recovery_trigger not in ("apogee", "time", "altitude"):
            raise ValueError("recovery_trigger deve ser 'apogee', 'time' ou 'altitude'.")
        if not isinstance(self.recovery_enabled, bool):
            raise ValueError("recovery_enabled deve ser booleano.")
        if not isinstance(self.thrust_curve, list):
            raise ValueError("thrust_curve deve ser uma lista.")
        if self.motor_mode == "constant" and self.thrust_curve:
            raise ValueError("O modo constante não deve conter curva de empuxo.")
        if self.motor_mode == "curve":
            validate_curve(self.thrust_curve)


def validate_curve(points):
    if not isinstance(points, list) or not 2 <= len(points) <= 10000:
        raise ValueError("A curva exige de 2 a 10.000 pontos.")
    previous = -1
    impulse = 0
    for i, point in enumerate(points):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("Cada ponto deve conter [tempo, empuxo].")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point):
            raise ValueError("A curva deve conter números finitos.")
        t, thrust = point
        if not previous < t <= 100 or t < 0 or not 0 <= thrust <= 10000:
            raise ValueError("Tempos crescentes entre 0 e 100 s; empuxo entre 0 e 10.000 N.")
        if i:
            impulse += (t - previous) * (thrust + points[i-1][1]) / 2
        previous = t
    if points[0][0] != 0 or points[-1][1] != 0 or points[-1][0] < .01 or impulse <= 0:
        raise ValueError("A curva deve começar em t=0, terminar com empuxo zero e ter impulso positivo.")
    return {"total_impulse": impulse, "burn_duration": points[-1][0],
            "peak_thrust": max(p[1] for p in points), "mean_thrust": impulse / points[-1][0]}


def core_command():
    import os
    from pathlib import Path
    import shutil
    root = Path(__file__).resolve().parent.parent
    name = "flight_cli.exe" if os.name == "nt" else "flight_cli"
    node = shutil.which("node")
    if os.name == "nt" and node and (root / "build" / "flight_cli.wasm").exists():
        return [node, "--disable-warning=ExperimentalWarning", str(root / "run-core.mjs")]
    binary = next((p for p in [root / "build" / name, root / "build" / "Release" / name] if p.exists()), None)
    if binary is None:
        raise ValueError("Núcleo C++ não compilado. Execute: python build.py")
    return [str(binary)]


def simulate(cfg):
    """Every computation is delegated to the same native executable used by CLI."""
    import json
    import subprocess
    cfg.validate()
    args = core_command() + ["--stdin", "--json-stdout"]

    lines = []
    for key, value in asdict(cfg).items():
        if key == "thrust_curve":
            lines.append(f"thrust_curve {len(value)}")
            for pt in value:
                lines.append(f"{pt[0]} {pt[1]}")
        elif isinstance(value, bool):
            lines.append(f"{key} {1 if value else 0}")
        else:
            lines.append(f"{key} {value}")

    payload = ("\n".join(lines) + "\n").encode("utf-8")

    try:
        run = subprocess.run(args, input=payload, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("O cálculo excedeu o limite de 30 segundos.") from exc
    except OSError as exc:
        raise ValueError("Não foi possível executar o núcleo C++. Verifique a compilação e as políticas de execução. " + str(exc)) from exc
    if run.returncode:
        # Decode stderr properly to avoid encoding issues with Portuguese characters
        err = run.stderr.decode("utf-8", errors="replace").strip() if isinstance(run.stderr, bytes) else run.stderr.strip()
        raise ValueError(err)

    # Same for stdout
    out = run.stdout.decode("utf-8", errors="replace") if isinstance(run.stdout, bytes) else run.stdout
    return json.loads(out)
