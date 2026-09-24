"""Strict CSV and RASP/ENG import. No network, implicit sorting or smoothing."""
import csv
import io
import math
from pathlib import PurePath

from .physics import validate_curve


def import_motor_file(filename, content):
    if not isinstance(filename, str) or not isinstance(content, str):
        raise ValueError("Informe nome e conteúdo do arquivo de motor.")
    if len(filename) > 255 or len(content.encode("utf-8")) > 2_000_000:
        raise ValueError("Arquivo de motor acima do limite de 2 MB.")
    suffix = PurePath(filename).suffix.lower()
    content = content.lstrip("\ufeff")
    motors = []

    def add(name, points, metadata):
        summary = validate_curve(points)
        motors.append({"name": name, "thrust_curve": points, "summary": summary, "metadata": metadata})
        if len(motors) > 100:
            raise ValueError("No máximo 100 motores por arquivo.")

    def numbers(parts):
        try:
            result = [float(p) for p in parts]
        except ValueError as exc:
            raise ValueError("O arquivo contém um número inválido.") from exc
        if not all(math.isfinite(x) for x in result):
            raise ValueError("O arquivo contém um número não finito.")
        return result

    if suffix == ".csv":
        try:
            rows = list(csv.reader(io.StringIO(content), strict=True))
        except csv.Error as exc:
            raise ValueError("Estrutura CSV inválida.") from exc
        if not rows or [x.strip() for x in rows[0]] != ["time", "thrust"]:
            raise ValueError("CSV de motor: cabeçalho time,thrust; segundos e newtons.")
        points = []
        for row in rows[1:]:
            if len(row) != 2:
                raise ValueError("Cada linha deve conter exatamente tempo e empuxo.")
            points.append(numbers(row))
        add("Motor CSV", points, {})
    elif suffix == ".eng":
        name, points, metadata = None, [], {}

        def finish():
            if name is not None:
                # RASP defines an implicit (0, 0), but explicit origin is accepted.
                normalized = ([[0., 0.]] if points and points[0][0] > 0 else []) + points
                if any(p[1] == 0 for p in normalized[1:-1]):
                    raise ValueError("ENG: empuxo zero só é permitido na origem e no término.")
                add(name, normalized, metadata)

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            parts = line.split()
            if len(parts) == 7:
                finish()
                diameter, length, propellant, loaded = numbers([parts[1], parts[2], parts[4], parts[5]])
                if diameter <= 0 or length <= 0 or not 0 < propellant < loaded:
                    raise ValueError("ENG: dimensões ou massas inválidas.")
                name, points = parts[0] + " / " + parts[6], []
                metadata = {"diameter_mm": diameter, "length_mm": length,
                            "propellant_mass_kg": propellant, "loaded_motor_mass_kg": loaded,
                            "delays": parts[3], "manufacturer": parts[6]}
            elif len(parts) == 2 and name is not None:
                points.append(numbers(parts))
                if len(points) > 10000:
                    raise ValueError("Curva acima de 10.000 pontos.")
            else:
                raise ValueError("ENG: cabeçalho de sete campos e pontos tempo–empuxo esperados.")
        finish()
    else:
        raise ValueError("Formatos de motor aceitos: CSV e ENG (RASP).")
    if not motors:
        raise ValueError("Nenhum motor encontrado.")
    return {"motors": motors}
