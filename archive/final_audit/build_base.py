import os
import json
import shutil
import re

out_dir = 'GEMINI_PROJECT_KNOWLEDGE'
ref_dir = os.path.join(out_dir, 'GEMINI_REFERENCE')
opt_dir = os.path.join(out_dir, 'OPTIONAL_DEEP_REFERENCE')

for d in [out_dir, ref_dir, opt_dir]:
    os.makedirs(d, exist_ok=True)

# 1. Project file inventory
with open(os.path.join(out_dir, '01_PROJECT_FILE_INVENTORY.md'), 'w', encoding='utf-8') as f:
    f.write("# Project File Inventory\n\n")
    f.write("| Path | Type | Notes |\n|---|---|---|\n")
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build', 'GEMINI_PROJECT_KNOWLEDGE')]
        for file in files:
            path = os.path.join(root, file).replace('\\', '/')
            ext = os.path.splitext(file)[1]
            if not ext: ext = 'file'
            f.write(f"| {path} | {ext} | |\n")

# Copy interesting files
def is_interesting(path):
    p = path.lower()
    return 'dmfe' in p or 'framework.py' in p or 'readme' in p or 'evaluation' in p or '.json' in p or '.yaml' in p or '.toml' in p or 'verify' in p

def is_optional(path):
    p = path.lower()
    return p.endswith('.py') or p.endswith('.tsx') or p.endswith('.ts')

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build', 'GEMINI_PROJECT_KNOWLEDGE', '.next')]
    for file in files:
        path = os.path.join(root, file)
        try:
            if is_interesting(path) and os.path.getsize(path) < 1000000:
                shutil.copy2(path, ref_dir)
            elif is_optional(path) and os.path.getsize(path) < 500000:
                shutil.copy2(path, opt_dir)
        except Exception:
            pass
