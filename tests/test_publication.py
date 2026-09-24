from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCANNER = Path(__file__).resolve().parents[1] / "scripts" / "verificar_publicacao.py"


class PublicationTests(unittest.TestCase):
    def scan(self, name, content, working_content=None):
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
            path=Path(folder)/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content,encoding="utf-8")
            subprocess.run(["git","add","--",name],cwd=folder,check=True,capture_output=True)
            if working_content is not None: path.write_text(working_content,encoding="utf-8")
            return subprocess.run([sys.executable,str(SCANNER)],cwd=folder,capture_output=True,text=True)

    def test_allowed_source(self):
        self.assertEqual(self.scan("README.md","# Exemplo público\n").returncode,0)

    def test_private_path_blocked(self):
        result=self.scan(".env","LOCAL_VALUE=example\n")
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn("LOCAL_VALUE",result.stdout)

    def test_staged_secret_blocked_without_disclosure(self):
        synthetic="gh"+"p_"+"A"*36
        result=self.scan("README.md",synthetic,"# Conteúdo corrigido apenas no disco\n")
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn(synthetic,result.stdout)
        self.assertIn("token GitHub",result.stdout)
