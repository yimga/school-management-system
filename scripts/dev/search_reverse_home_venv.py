# Ad-hoc: search .venv for reverse('home') etc. in .py/.html/.txt. Run from project root.
import os

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.normpath(os.path.join(_script_dir, "..", ".."))
root = os.path.join(_project_root, ".venv")
if not os.path.isdir(root):
    root = os.path.join(os.path.dirname(_project_root), ".venv")
for dirpath, dirnames, filenames in os.walk(root):
    for name in filenames:
        if name.endswith((".py", ".html", ".txt")):
            path = os.path.join(dirpath, name)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                continue
            if (
                "reverse_lazy('home'" in text
                or 'reverse_lazy("home"' in text
                or "reverse('home'" in text
                or 'reverse("home"' in text
            ):
                print(path)
