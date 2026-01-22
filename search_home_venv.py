import os
root = '..\\..\\.venv'
for dirpath, dirnames, filenames in os.walk(root):
    for name in filenames:
        if name.endswith(('.html','.py')):
            path = os.path.join(dirpath, name)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except Exception:
                continue
            if "url 'home'" in text or 'url \"home\"' in text:
                print(path)
