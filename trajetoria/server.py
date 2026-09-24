"""Loopback-only application server; Python standard library only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import webbrowser
import re
from uuid import uuid4

from .physics import Config, simulate
from .validation import compare
from dataclasses import asdict, replace
from .motors import import_motor_file

STATIC = Path(__file__).with_name("static")
EXPORTS = STATIC.parent.parent / "output" / "exports"
EXPORT_TYPES = {"trajetoria-estudo.json": "application/json", "trajetoria-parametros.json": "application/json",
                "trajetoria-validacao.json": "application/json", "trajetoria-telemetria.csv": "text/csv"}
FILES = {"/": ("index.html", "text/html; charset=utf-8"),
         "/app.js": ("app.js", "text/javascript; charset=utf-8"),
         "/style.css": ("style.css", "text/css; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, content_type="application/json; charset=utf-8", filename=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        # Bounded writes avoid oversized socket sends on local Windows stacks.
        for start in range(0, len(body), 16384):
            self.wfile.write(body[start:start + 16384])
        self.wfile.flush()
        self.close_connection = True

    def do_GET(self):
        if not self.valid_host():
            self.send(403, b'{"error":"Host rejected"}')
            return
        path = self.path.split("?")[0]
        if path.startswith("/exports/"):
            name = path[len("/exports/"):]
            match = re.fullmatch(r"[0-9a-f]{32}_(trajetoria-[a-z]+\.(?:json|csv))", name)
            if match and match[1] in EXPORT_TYPES and (EXPORTS / name).is_file():
                self.send(200, (EXPORTS / name).read_bytes(), EXPORT_TYPES[match[1]], match[1])
            else:
                self.send(404, b'{"error":"Not found"}')
            return
        if path not in FILES:
            self.send(404, b'{"error":"Not found"}')
            return
        filename, content_type = FILES[path]
        self.send(200, (STATIC / filename).read_bytes(), content_type)

    def valid_host(self):
        return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def do_POST(self):
        if not self.valid_host():
            self.send(403, b'{"error":"Host rejected"}')
            return
        if self.path not in {"/api/simulate", "/api/validate", "/api/convergence", "/api/export", "/api/motor-import", "/api/config"}:
            self.send(404, b'{"error":"Not found"}')
            return
        # Do not allow other browser origins to drive the local calculation API.
        origin = self.headers.get("Origin")
        allowed = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
        if origin and origin not in allowed:
            self.send(403, b'{"error":"Origin rejected"}')
            return
        if self.headers.get_content_type() != "application/json":
            self.send(415, b'{"error":"Expected application/json"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = 128_000_000 if self.path == "/api/export" else 2_000_000
            if not 0 < length <= limit:
                raise ValueError("Configuração vazia ou muito grande.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Esperado objeto JSON.")
            if self.path == "/api/motor-import":
                data = import_motor_file(payload.get("filename"), payload.get("content"))
                self.send(200, json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"))
                return
            if self.path == "/api/config":
                self.send(200, json.dumps(asdict(Config.from_dict(payload)), allow_nan=False).encode("utf-8"))
                return
            if self.path == "/api/export":
                filename, content = payload.get("filename"), payload.get("content")
                if not isinstance(filename, str) or filename not in EXPORT_TYPES or not isinstance(content, str):
                    raise ValueError("Exportação inválida.")
                EXPORTS.mkdir(parents=True, exist_ok=True)
                stored = uuid4().hex + "_" + filename
                (EXPORTS / stored).write_text(content, encoding="utf-8")
                data = {"url": "/exports/" + stored, "path": str(EXPORTS / stored)}
                self.send(200, json.dumps(data).encode("utf-8"))
                return
            cfg = Config.from_dict(payload if self.path == "/api/simulate" else payload.get("config"))
            data = simulate(cfg)
            if self.path == "/api/validate":
                if data["status"] == "no_liftoff":
                    raise ValueError("Não há voo para comparar: empuxo insuficiente.")
                data = compare(data, payload.get("observations"))
            elif self.path == "/api/convergence":
                if cfg.time_step < .004:
                    raise ValueError("Use passo de pelo menos 0,004 s para comparar h, h/2 e h/4.")
                fine = simulate(replace(cfg, time_step=cfg.time_step/2))
                finer = simulate(replace(cfg, time_step=cfg.time_step/4))
                data = {"steps": [cfg.time_step, cfg.time_step/2, cfg.time_step/4],
                        "apogees": [d["summary"]["apogee"] for d in [data, fine, finer]],
                        "note": "Convergência numérica não mede precisão experimental."}
            self.send(200, json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        except (ValueError, OverflowError) as exc:
            self.send(400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"))
        except OSError:
            self.send(500, b'{"error":"Falha de acesso ao arquivo local."}')


def serve(port=8765, open_browser=True):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Trajetória disponível em {url}\nCtrl+C para encerrar.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
