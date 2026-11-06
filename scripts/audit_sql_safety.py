"""Audit SQL statements in careerorbit/database/db.py for parameterization safety."""
import ast
import re

with open("careerorbit/database/db.py", "r", encoding="utf-8") as f:
    code = f.read()

tree = ast.parse(code)
dynamic_executes = []

for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ("execute", "executemany"):
            if node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.JoinedStr):  # f-string
                    dynamic_executes.append((node.lineno, "f-string in execute"))
                elif isinstance(first_arg, ast.BinOp) and isinstance(first_arg.op, ast.Mod):  # % format
                    dynamic_executes.append((node.lineno, "% format in execute"))
                elif isinstance(first_arg, ast.Call) and isinstance(first_arg.func, ast.Attribute) and first_arg.func.attr == "format":
                    dynamic_executes.append((node.lineno, ".format() in execute"))

print("Dynamic execute calls found:", len(dynamic_executes))
for lineno, desc in dynamic_executes:
    print(f"Line {lineno}: {desc}")
