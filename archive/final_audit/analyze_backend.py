import os
import ast
import json
import re

def analyze_backend(base_dir):
    data = {
        "files": [],
        "models": [],
        "routes": [],
        "classes": [],
        "functions": [],
        "todos": [],
        "imports": []
    }
    
    for root, dirs, files in os.walk(base_dir):
        # Skip venv and caches
        dirs[:] = [d for d in dirs if d not in ('venv', '.venv', '__pycache__', '.git', 'node_modules')]
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # Find TODOs and FIXMEs
                        for i, line in enumerate(content.splitlines()):
                            if re.search(r'(TODO|FIXME|XXX)', line, re.IGNORECASE):
                                data["todos"].append({"file": path, "line": i+1, "content": line.strip()})
                            if 'pass' in line.strip() and len(line.strip()) == 4:
                                data["todos"].append({"file": path, "line": i+1, "content": "pass statement"})
                            if 'except Exception:' in line or 'except Exception as e:' in line:
                                data["todos"].append({"file": path, "line": i+1, "content": "Broad exception: " + line.strip()})
                            if 'print(' in line:
                                data["todos"].append({"file": path, "line": i+1, "content": "Print statement: " + line.strip()})

                        # Parse AST
                        try:
                            tree = ast.parse(content)
                            file_data = {"path": path, "classes": [], "functions": [], "imports": []}
                            for node in ast.walk(tree):
                                if isinstance(node, ast.ClassDef):
                                    bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                                    file_data["classes"].append({"name": node.name, "bases": bases})
                                    data["classes"].append({"name": node.name, "file": path, "bases": bases})
                                    if any('Model' in b or 'Base' in b for b in bases):
                                        data["models"].append({"name": node.name, "file": path})
                                elif isinstance(node, ast.FunctionDef):
                                    file_data["functions"].append(node.name)
                                    data["functions"].append({"name": node.name, "file": path})
                                    # Very basic route heuristic for FastAPI/Flask
                                    has_route = False
                                    for decorator in node.decorator_list:
                                        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                                            if decorator.func.attr in ('get', 'post', 'put', 'delete', 'patch', 'route'):
                                                has_route = True
                                    if has_route:
                                        data["routes"].append({"function": node.name, "file": path})
                                elif isinstance(node, ast.Import):
                                    for n in node.names:
                                        file_data["imports"].append(n.name)
                                elif isinstance(node, ast.ImportFrom):
                                    if node.module:
                                        file_data["imports"].append(node.module)
                            data["files"].append(file_data)
                        except SyntaxError:
                            pass
                except Exception as e:
                    print(f"Error reading {path}: {e}")
                    
    with open('backend_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

analyze_backend('d:/rapidoproject/backend')
