from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
import http.client
import re
import urllib.error
import urllib.request

from trajetoria.physics import Config, simulate, core_command
from trajetoria.validation import compare


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = simulate(Config())
        cls.process = subprocess.Popen([sys.executable, "-m", "trajetoria", "app", "--port", "0", "--no-browser"],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        line = cls.process.stdout.readline()
        cls.port = int(re.search(r"127\.0\.0\.1:(\d+)", line).group(1))
        cls.url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.process.stdout.close()

    def post(self, path, payload, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("POST", path, json.dumps(payload).encode(), headers)
            response = connection.getresponse()
            content = response.read()
            if response.status >= 400:
                raise urllib.error.HTTPError(self.url+path, response.status, response.reason, response.headers, None)
            return json.loads(content)
        finally:
            connection.close()

    def test_native_cli_parity(self):
        native = json.loads(subprocess.check_output(core_command() + ["--json-stdout"]))
        self.assertEqual(native, self.data)

    def test_defaults_match_native_schema(self):
        self.assertEqual(asdict(Config()), self.data["config"])

    def test_http_uses_identical_core(self):
        self.assertEqual(self.post("/api/simulate", {}), self.data)

    def test_reference_residuals(self):
        rows = [{"time": s["time"], "altitude": s["altitude"]-2, "speed": s["speed"]}
                for s in self.data["samples"][::25]]
        metrics = compare(self.data, rows)["metrics"]
        self.assertAlmostEqual(metrics["altitude"]["rmse"], 2, places=12)
        self.assertAlmostEqual(metrics["altitude"]["bias"], 2, places=12)
        self.assertEqual(metrics["speed"]["rmse"], 0)

    def test_reference_linear_interpolation(self):
        a, b = self.data["samples"][10:12]
        row = {"time": (a["time"]+b["time"])/2, "altitude": (a["altitude"]+b["altitude"])/2}
        result = compare(self.data, [{"time": 0, "altitude": 0}, row])
        self.assertLess(result["metrics"]["altitude"]["rmse"], 1e-12)

    def test_invalid_observations(self):
        for rows in [[{"time": 0, "altitude": 0}]*2,
                     [{"time": 0, "altitude": 0}, {"time": 999, "altitude": 0}],
                     [{"time": 0, "altitude": 0}, {"time": 1, "altitude": math.nan}]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                compare(self.data, rows)

    def test_malformed_config(self):
        for cfg in [{"time_step": 0}, {"dry_mass": True}, {"thrust": math.inf}, {"unknown": 1}, []]:
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                Config.from_dict(cfg)

    def test_http_invalid_input(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("/api/simulate", {"time_step": 0})
        self.assertEqual(error.exception.code, 400)
        error.exception.close()

    def test_http_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("/api/simulate", {}, "https://example.com")
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_http_validation(self):
        rows = [{"time": s["time"], "altitude": s["altitude"]} for s in self.data["samples"][::50]]
        result = self.post("/api/validate", {"config": {}, "observations": rows})
        self.assertEqual(result["metrics"]["altitude"]["rmse"], 0)

    def test_convergence_endpoint(self):
        result = self.post("/api/convergence", {"config": {}})
        self.assertEqual(result["steps"], [.02, .01, .005])
        self.assertLess(abs(result["apogees"][0]-result["apogees"][2]), 1e-5)

    def test_truncation(self):
        data = simulate(replace(Config(), max_time=10, thrust=30))
        self.assertEqual(data["status"], "time_limit")
        self.assertAlmostEqual(data["summary"]["duration"], 10)

    def test_static_and_traversal(self):
        for path in ("/", "/app.js", "/style.css"):
            with urllib.request.urlopen(self.url+path) as response:
                self.assertEqual(response.status, 200)
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.url+"/../native/main.cpp")
        self.assertEqual(error.exception.code, 404)
        error.exception.close()

    def test_core_rejects_invalid_values(self):
        for args in [["--time_step", "0"], ["--thrust", "nan"], ["--wrong", "1"], ["--thrust", "12oops"]]:
            run = subprocess.run(core_command()+args, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(run.returncode, 0)

    def test_high_drag_stability(self):
        data = simulate(replace(Config(), dry_mass=.05, propellant_mass=.001, thrust=100,
                                diameter=.2, drag_coefficient=2, time_step=.1))
        self.assertEqual(data["status"], "landed")
        self.assertTrue(all(math.isfinite(v) for s in data["samples"] for v in s.values() if isinstance(v, (int, float))))
        self.assertTrue(all(s["state_motion"] in {"Supported", "Ascending", "Descending", "Landed"} for s in data["samples"]))

    def test_export_and_download(self):
        result = self.post("/api/export", {"filename": "trajetoria-parametros.json", "content": '{"thrust":12}'})
        try:
            with urllib.request.urlopen(self.url+result["url"]) as response:
                self.assertEqual(response.read(), b'{"thrust":12}')
                self.assertIn("attachment", response.headers["Content-Disposition"])
        finally:
            Path(result["path"]).unlink()

    def test_export_path_rejection(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("/api/export", {"filename": "../unsafe.py", "content": "invalid"})
        self.assertEqual(error.exception.code, 400)
        error.exception.close()

    def test_motor_import_and_config_endpoints(self):
        data=self.post("/api/motor-import",{"filename":"motor.csv","content":"time,thrust\n0,0\n1,20\n2,0\n"})
        cfg=self.post("/api/config",{"motor_mode":"curve","thrust_curve":data["motors"][0]["thrust_curve"]})
        self.assertEqual(self.post("/api/simulate",cfg)["summary"]["total_impulse"],20)

    def test_host_and_content_type_rejected(self):
        for headers,expected in [({"Host":"example.com","Content-Type":"application/json"},403),
                                 ({"Content-Type":"text/plain"},415)]:
            connection=http.client.HTTPConnection("127.0.0.1",self.port,timeout=10)
            try:
                connection.request("POST","/api/simulate",b"{}",headers)
                response=connection.getresponse();response.read()
                self.assertEqual(response.status,expected)
            finally: connection.close()


if __name__ == "__main__":
    unittest.main()
