"""Check the rapid-mass regression against an independent analytical reference.

Run from the project root: python -m analises.revisao_numerica
The scenarios are synthetic, not experimental flight data.
"""
from dataclasses import replace
import json
import math
from pathlib import Path

from trajetoria.physics import Config, simulate


def main():
    config = Config(dry_mass=.05, propellant_mass=.5, thrust=100, burn_time=.1,
                    elevation=90, air_density=0, wind_east=0, wind_north=0,
                    time_step=.1)
    initial_mass = config.dry_mass + config.propellant_mass
    flow = config.propellant_mass / config.burn_time
    exhaust_equivalent = config.thrust / flow
    log_ratio = math.log(initial_mass / config.dry_mass)
    exact_speed = exhaust_equivalent * log_ratio - 9.80665 * config.burn_time
    exact_altitude = exhaust_equivalent * (
        config.burn_time - config.dry_mass / flow * log_ratio
    ) - .5 * 9.80665 * config.burn_time**2
    cases = []
    for step in [.1, .01, .001]:
        result = simulate(replace(config, time_step=step))
        burnout = min(result["samples"], key=lambda s: abs(s["time"] - config.burn_time))
        cases.append({
            "step_s": step,
            "burnout_time_s": burnout["time"],
            "velocity_up_m_s": burnout["velocity_up"],
            "altitude_m": burnout["altitude"],
            "velocity_relative_error_percent": 100 * (burnout["velocity_up"] / exact_speed - 1),
            "altitude_relative_error_percent": 100 * (burnout["altitude"] / exact_altitude - 1),
        })
    report = {
        "purpose": "Synthetic verification of step sensitivity, not physical validation",
        "config": simulate(config)["config"],
        "reference": {"velocity_up_m_s": exact_speed, "altitude_m": exact_altitude},
        "cases": cases,
        "conclusion": "Synthetic numerical regression; inspect errors against the analytical reference. This is not experimental validation.",
    }
    output = Path("output/revisao-massa-variavel.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
