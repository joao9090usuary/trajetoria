from dataclasses import replace
import json
import math
import subprocess
import unittest

from trajetoria.physics import Config, simulate
from trajetoria.motors import import_motor_file


class MotorRecoveryTests(unittest.TestCase):
    def test_curve_csv_and_roundtrip(self):
        imported = import_motor_file("motor.csv", "time,thrust\n0,0\n1,20\n2,0\n")
        motor = imported["motors"][0]
        self.assertEqual(motor["summary"]["total_impulse"], 20)
        cfg = replace(Config(), motor_mode="curve", thrust_curve=motor["thrust_curve"])
        first = simulate(cfg)
        self.assertEqual(first, simulate(Config.from_dict(first["config"])))
        self.assertEqual(first["summary"]["burn_duration"], 2)
        self.assertEqual(first["summary"]["total_impulse"], 20)
        self.assertEqual(first["summary"]["initial_thrust_to_weight"], 0)
        self.assertTrue(all(s["thrust"] == 0 for s in first["samples"] if s["time"] >= 2))

    def test_rasp_separate_motors_and_units(self):
        eng = "; Synthetic motors\nA 18 70 3 .01 .03 TEST\n.1 10\n1 0\n;\nB 24 80 P .02 .04 TEST\n.2 20\n2 0\n"
        motors = import_motor_file("synthetic.eng", eng)["motors"]
        self.assertEqual(len(motors), 2)
        self.assertEqual(motors[0]["thrust_curve"][0], [0, 0])
        self.assertAlmostEqual(motors[0]["summary"]["total_impulse"], 5)
        self.assertEqual(motors[1]["metadata"]["propellant_mass_kg"], .02)

    def test_invalid_curves_are_not_repaired(self):
        cases = [[[0,0],[1,10],[1,0]], [[0,0],[2,10],[1,0]], [[0,0],[1,10]],
                 [[0,0],[1,-1],[2,0]], [[0,0],[1,math.inf],[2,0]], [[0,0],[1,0]],
                 [[0,0],[True,20],[2,0]], [[0,0],[1,"20"],[2,0]], [[0,0],[1,20,3],[2,0]]]
        for curve in cases:
            with self.subTest(curve=curve), self.assertRaises(ValueError):
                simulate(replace(Config(), motor_mode="curve", thrust_curve=curve))

    def test_invalid_import(self):
        for name, text in [("a.csv", "time,thrust\n0,0\n1,12oops\n2,0"),
                           ("a.csv", "time,thrust\n0,0\n2,10\n1,0"),
                           ("a.eng", "A 18 70 3 .01 .03 TEST\n.1 10\n1 4"),
                           ("a.rse", "<engine/>")]:
            with self.subTest(name=name, text=text), self.assertRaises(ValueError):
                import_motor_file(name, text)

    def test_recovery_at_apogee_with_delay(self):
        cfg = replace(Config(), recovery_enabled=True, recovery_delay=.3, recovery_inflation=.8)
        result = simulate(cfg)
        events = {e["name"]:e for e in result["events"]}
        self.assertEqual(len(events),len(result["events"]))
        self.assertAlmostEqual(events["recovery_trigger"]["time"],events["apogee"]["time"],places=10)
        self.assertAlmostEqual(events["ejection"]["time"]-events["recovery_trigger"]["time"],.3,places=10)
        self.assertAlmostEqual(events["parachute_open"]["time"]-events["ejection"]["time"],.8,places=10)
        self.assertEqual(result["status"],"landed")
        self.assertLess(abs(result["samples"][-1]["velocity_up"]),5)
        self.assertEqual(result["samples"][-1]["opening_fraction"],1)
        opening = [s for s in result["samples"] if 0 < s["opening_fraction"] < 1]
        self.assertGreater(len(opening),2)
        for s in result["samples"]:
            self.assertAlmostEqual(s["effective_cda"],cfg.recovery_cd*cfg.recovery_area*s["opening_fraction"],places=12)
            if s["time"]<events["ejection"]["time"]:
                self.assertEqual(s["parachute_drag"],0)
        ejected = min(result["samples"],key=lambda s:abs(s["time"]-events["ejection"]["time"]))
        self.assertEqual(ejected["opening_fraction"],0)
        self.assertGreater(ejected["speed"],0)

    def test_recovery_time_and_altitude_triggers(self):
        for trigger in ["time", "altitude"]:
            cfg = replace(Config(), recovery_enabled=True, recovery_trigger=trigger,
                          recovery_time=3, recovery_altitude=50)
            result = simulate(cfg)
            event = next(e for e in result["events"] if e["name"]=="recovery_trigger")
            if trigger=="time":
                self.assertAlmostEqual(event["time"],3,places=10)
            else:
                self.assertAlmostEqual(event["altitude"],50,places=8)
                self.assertGreater(event["time"],next(e["time"] for e in result["events"] if e["name"]=="apogee"))

    def test_threshold_above_apogee_and_no_deployment_on_pad(self):
        result = simulate(replace(Config(),recovery_enabled=True,recovery_trigger="altitude",recovery_altitude=1000))
        events={e["name"]:e["time"] for e in result["events"]}
        self.assertEqual(events["recovery_trigger"],events["apogee"])
        pad=simulate(replace(Config(),thrust=0,recovery_enabled=True,recovery_trigger="time",recovery_time=0))
        self.assertEqual(pad["status"],"no_liftoff")
        self.assertEqual(pad["samples"][0]["acceleration"],0)
        self.assertFalse(any(e["name"]=="ejection" for e in pad["events"]))

    def test_curve_recovery_convergence_and_finite_history(self):
        cfg=replace(Config(),motor_mode="curve",thrust_curve=[[0,0],[.05,25],[1,15],[2,0]],recovery_enabled=True,time_step=.05)
        a,b=simulate(cfg),simulate(replace(cfg,time_step=.025))
        self.assertAlmostEqual(a["summary"]["apogee"],b["summary"]["apogee"],places=7)
        self.assertAlmostEqual(a["summary"]["duration"],b["summary"]["duration"],places=6)
        self.assertLessEqual(a["summary"]["max_error_ratio"],1)
        previous=-1
        for s in a["samples"]:
            self.assertGreater(s["time"],previous);previous=s["time"]
            self.assertGreaterEqual(s["mass"],cfg.dry_mass)
            self.assertTrue(all(math.isfinite(v) for v in s.values() if isinstance(v,(int,float))))

    def test_boolean_types(self):
        for data in [{"dry_mass":True},{"recovery_enabled":1},{"thrust_curve":"bad"}]:
            with self.assertRaises(ValueError): Config.from_dict(data)
