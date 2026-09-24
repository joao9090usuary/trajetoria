"""Experimental residuals, with strict time alignment and no extrapolation."""
from bisect import bisect_left
import math

QUANTITIES = {"altitude": "m", "east": "m", "north": "m", "speed": "m/s"}


def compare(data, observations):
    if not isinstance(observations, list) or not 2 <= len(observations) <= 10000:
        raise ValueError("Forneça entre 2 e 10.000 medições.")
    samples = data["samples"]
    times = [s["time"] for s in samples]
    previous = -1
    residuals = {key: [] for key in QUANTITIES}
    details = []
    for row in observations:
        if not isinstance(row, dict) or "time" not in row:
            raise ValueError("Cada medição deve conter time em segundos.")
        if set(row) - {"time", *QUANTITIES}:
            raise ValueError("Colunas aceitas: time, altitude, east, north, speed.")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in row.values()):
            raise ValueError("Todas as medições devem conter números finitos.")
        t = row["time"]
        if t <= previous or not times[0] <= t <= times[-1]:
            raise ValueError("Tempos devem ser crescentes, sem duplicatas e dentro do intervalo simulado.")
        previous = t
        if len(row) < 2:
            raise ValueError("Cada linha precisa de pelo menos uma grandeza medida.")
        idx = max(1, bisect_left(times, t))
        a, b = samples[idx-1], samples[min(idx, len(samples)-1)]
        fraction = (t-a["time"])/(b["time"]-a["time"]) if b["time"]>a["time"] else 0
        detail = {"time": t}
        for key in QUANTITIES:
            if key not in row:
                continue
            predicted = a[key] + fraction * (b[key]-a[key])
            error = predicted-row[key]
            residuals[key].append(error)
            detail[key] = {"measured": row[key], "predicted": predicted, "residual": error}
        details.append(detail)
    metrics = {}
    for key, errors in residuals.items():
        if errors:
            metrics[key] = {"count": len(errors), "unit": QUANTITIES[key],
                            "rmse": math.sqrt(sum(e*e for e in errors)/len(errors)),
                            "mae": sum(abs(e) for e in errors)/len(errors),
                            "bias": sum(errors)/len(errors), "max_abs": max(abs(e) for e in errors)}
    return {"metrics": metrics, "residuals": details,
            "note": "Comparação por interpolação linear; não inclui incerteza dos sensores, sincronização automática ou calibração. Não certifica precisão."}
