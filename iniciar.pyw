"""Windows double-click launcher. Errors appear in a dialog, without a terminal."""
from pathlib import Path
import os
import tkinter.messagebox

os.chdir(Path(__file__).resolve().parent)
try:
    from trajetoria.server import serve
    serve(open_browser=True)
except Exception as exc:
    tkinter.messagebox.showerror("Trajetória", f"Não foi possível iniciar: {exc}\n\nConsulte README.md.")
