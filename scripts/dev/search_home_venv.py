# Ad-hoc: search .venv for url 'home' in .html/.py. Run from project root.
import os

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.normpath(os.path.join(_script_dir, "..", ".."))
root = os.path.join(_project_root, ".venv")
if not os.path.isdir(root):
    root = os.path.join(os.path.dirname(_project_root), ".venv")
for dirpath, dirnames, filenames in os.walk(root):
    for name in filenames:
        if name.endswith((".html", ".py")):
            path = os.path.join(dirpath, name)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                continue
            if "url 'home'" in text or 'url "home"' in text:
                print(path)
