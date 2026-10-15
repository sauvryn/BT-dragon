"""No he/him/his on the dragon's screen, in the Den or on its pages: the dragon can be any
gender, so displayed text uses the dragon's own name or "your dragon". (Code comments and
docstrings don't show anywhere, so they're not checked; nor is the README, which says the
default name and its pronouns are assumed there.)"""
import ast
import os
import re

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bt_dragon")
WORDS = re.compile(r"\b(he|him|his|himself|he's|he'll|he'd)\b", re.I)
found = []

for name in ("den.html", "map.html", "shopping.html", "calendar.html", "art.html",
             "garden/mode.js", "garden/hook.js", "lang.js"):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"<!--.*?-->|/\*.*?\*/", "", text, flags=re.S)        # comments
    text = re.sub(r"(?m)(^|\s)//.*$", "", text)
    text = text.replace('value="he"', "")                                # a weather-warning region's code
    for i, line in enumerate(text.splitlines(), 1):
        if WORDS.search(line):
            found.append(f"{name}: {line.strip()[:100]}")

for name in sorted(os.listdir(HERE)):
    if not name.endswith(".py"):
        continue
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            if n.value.strip().lower() == "he":                           # region codes in weather_warnings
                continue
            if WORDS.search(n.value):
                found.append(f"{name}:{n.lineno}: {n.value[:100]!r}")

assert not found, "\n".join(found)
print("pronouns ok")
