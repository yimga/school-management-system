import os
root = '..\\..\\.venv'
for dirpath, dirnames, filenames in os.walk(root):
    for name in filenames:
        if name.endswith(('.py', '.html', '.txt')):
            path = os.path.join(dirpath, name)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except Exception:
                continue
            if "reverse_lazy('home'" in text or 'reverse_lazy("home"' in text or "reverse('home'" in text or 'reverse("home"' in text:
                print(path)
