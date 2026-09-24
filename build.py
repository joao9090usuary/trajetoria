"""Build with an available C++17 compiler, or the locally extracted Zig toolchain."""
from pathlib import Path
import os
import shutil
import subprocess
import argparse

ROOT = Path(__file__).resolve().parent


def build(wasm=False):
    os.chdir(ROOT)
    destination = ROOT / "build"
    destination.mkdir(exist_ok=True)
    compiler = next((shutil.which(c) for c in ("g++", "clang++") if shutil.which(c)), None)
    zig = next((ROOT / ".tools").glob("zig*/zig.exe"), None)
    if wasm and zig:
        command = [str(zig), "c++", "-target", "wasm32-wasi", "-fno-exceptions"]
    elif wasm:
        raise SystemExit("Build WASI requer o compilador Zig em .tools/zig*/zig.exe nesta configuração.")
    elif compiler:
        command = [compiler]
    elif zig:
        command = [str(zig), "c++"]
    else:
        raise SystemExit("Instale um compilador C++17 (GCC/Clang) ou use CMake com Visual Studio. Veja README.md.")
    for source, target in [("main.cpp", "flight_cli"), ("tests.cpp", "flight_tests")]:
        output = destination / (target + (".wasm" if wasm else ".exe" if os.name == "nt" else ""))
        subprocess.run(command + ["-std=c++17", "-O2", "-Wall", "-Wextra", "-Wpedantic",
                       str(ROOT / "native" / source), "-o", str(output)], check=True)
        print(f"Compilado: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wasm", action="store_true", help="Compilar C++ para WASI/Node")
    build(parser.parse_args().wasm)
