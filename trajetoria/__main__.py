import argparse
import csv
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

from .physics import Config, simulate


def main():
    parser = argparse.ArgumentParser(description="Trajetória · laboratório educacional de foguetes")
    sub = parser.add_subparsers(dest="command", required=True)
    app = sub.add_parser("app", help="Abrir aplicativo local")
    app.add_argument("--port", type=int, default=8765)
    app.add_argument("--no-browser", action="store_true")
    run = sub.add_parser("simulate", help="Executar simulação pelo terminal")
    run.add_argument("--config", type=Path)
    run.add_argument("--output", type=Path, help="Exportar resultado JSON")
    run.add_argument("--csv", type=Path, help="Exportar amostras CSV")
    validation = sub.add_parser("validate", help="Comparar medições CSV com o modelo")
    validation.add_argument("--config", type=Path)
    validation.add_argument("--data", type=Path, required=True)
    validation.add_argument("--output", type=Path, required=True)
    convergence = sub.add_parser("convergence", help="Comparar passos h, h/2 e h/4")
    convergence.add_argument("--config", type=Path)
    sub.add_parser("config", help="Imprimir configuração padrão em JSON")
    args = parser.parse_args()
    try:
        if args.command == "app":
            from .server import serve
            serve(args.port, not args.no_browser)
        elif args.command == "config":
            print(json.dumps(asdict(Config()), indent=2))
        else:
            cfg = Config.from_dict(json.loads(args.config.read_text(encoding="utf-8-sig"))) if args.config else Config()
            data = simulate(cfg)
            if args.command == "validate":
                from .validation import compare
                if data["status"] == "no_liftoff":
                    raise ValueError("Não há voo para comparar.")
                with args.data.open(encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                        raise ValueError("Cabeçalho CSV ausente ou duplicado.")
                    rows = []
                    for row in reader:
                        if len(rows) >= 10000 or None in row or any(v is None for v in row.values()):
                            raise ValueError("CSV inválido ou acima de 10.000 medições.")
                        rows.append({k: float(v) for k, v in row.items()})
                report = compare(data, rows)
                report.update(config=asdict(cfg), observations=rows)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
                return 0
            if args.command == "convergence":
                if cfg.time_step < .004:
                    raise ValueError("Use passo de pelo menos 0,004 s.")
                for divisor in (1, 2, 4):
                    current = data if divisor == 1 else simulate(replace(cfg, time_step=cfg.time_step/divisor))
                    print(f"h={cfg.time_step/divisor:.6f} s | apogeu={current['summary']['apogee']:.10f} m")
                print("Convergência numérica não mede precisão experimental.")
                return 0
            if args.output:
                args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            if args.csv:
                with args.csv.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(data["samples"][0]))
                    writer.writeheader()
                    writer.writerows(data["samples"])
            s = data["summary"]
            print(f"TRAJETÓRIA | {data['status']}\nApogeu: {s['apogee']:.2f} m\n"
                  f"Velocidade máxima: {s['max_speed']:.2f} m/s\n"
                  f"Duração simulada: {s['duration']:.2f} s\n"
                  f"Deslocamento horizontal: {s['horizontal_distance']:.2f} m\n"
                  "Modelo educacional. Precisão física não validada experimentalmente.")
    except (ValueError, OSError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
