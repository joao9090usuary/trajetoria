"""Check the exact staged snapshot without displaying any matched secret."""
from pathlib import PurePosixPath
import re
import subprocess
import sys

ROOT_FILES = {".gitignore", ".gitattributes", "README.md", "SECURITY.md", "CONTRIBUTING.md",
              "VERIFICACAO.md", "CMakeLists.txt", "build.py", "run-core.mjs", "run-tests.py", "iniciar.pyw"}
ROOT_DIRS = {"native", "trajetoria", "tests", "exemplos", "analises", "docs", "scripts", ".github"}
EXTENSIONS = {".py", ".pyw", ".hpp", ".cpp", ".mjs", ".js", ".html", ".css", ".md", ".json", ".csv", ".yml", ".yaml"}
PATTERNS = {
    "chave privada": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "token GitHub": r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b",
    "chave de serviço": r"\b(?:AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{24,})\b",
    "token Slack": r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b",
    "caminho pessoal": r"(?:[A-Za-z]:[\\/]+Users[\\/]+[\w.-]+|/Users/[\w.-]+|/home/[\w.-]+)",
    "credencial em URL": r"https?://[^\s/@:]+:[^\s/@]+@",
    "segredo atribuído": r'''(?i)(?:api_key|api_secret|access_token|password|client_secret)\s*[:=]\s*["'][A-Za-z0-9_./+=-]{16,}["']''',
}


def main():
    result = subprocess.run(["git", "ls-files", "--stage", "-z"], capture_output=True, check=True)
    failures, checked = [], 0
    for entry in result.stdout.decode("utf-8").split("\0"):
        if not entry:
            continue
        meta, name = entry.split("\t", 1)
        mode, sha, stage = meta.split()
        path = PurePosixPath(name)
        allowed = name in ROOT_FILES or (path.parts[0] in ROOT_DIRS and path.suffix in EXTENSIONS)
        forbidden = any(p.startswith(".env") or p in {"node_modules", "__pycache__"} for p in path.parts)
        if not allowed or forbidden or mode != "100644" or stage != "0":
            failures.append(f"{name}: caminho ou modo não permitido")
            continue
        data = subprocess.check_output(["git", "cat-file", "blob", sha])
        if len(data) > 2_000_000 or b"\x00" in data:
            failures.append(f"{name}: arquivo binário ou acima de 2 MB")
            continue
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            failures.append(f"{name}: arquivo não UTF-8")
            continue
        checked += 1
        for label, expression in PATTERNS.items():
            for match in re.finditer(expression, content):
                line = content.count("\n", 0, match.start()) + 1
                failures.append(f"{name}:{line}: possível {label}")
    if not checked:
        failures.append("Nenhum arquivo preparado para publicação.")
    for finding in failures:
        print(finding)
    print(f"Arquivos verificados: {checked}; ocorrências: {len(failures)}.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
