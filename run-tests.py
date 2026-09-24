"""Run the C++ analytical suite and Python/API integration suite."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
os.chdir(root)
if (root / "build/flight_tests.wasm").exists() and shutil.which("node"):
    command = [shutil.which("node"), "--disable-warning=ExperimentalWarning", str(root / "run-core.mjs"), "--tests"]
else:
    filename = "flight_tests.exe" if os.name == "nt" else "flight_tests"
    executable = next((p for p in [root / "build" / filename, root / "build/Release" / filename] if p.exists()), None)
    if executable is None:
        raise SystemExit("Compile o projeto antes de executar os testes.")
    command = [str(executable)]
subprocess.run(command, check=True)
subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], check=True)
