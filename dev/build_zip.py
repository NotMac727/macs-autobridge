"""Build dist/MacsAutoBridge_v<version>.zip, the file you share."""
import os, re, zipfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
version = re.search(r'__version__ = "([^"]+)"',
                    open(os.path.join(ROOT, "MacsAutoBridge/scripts/macs_autobridge/__init__.py")).read()).group(1)
top = "MacsAutoBridge_v" + version
out = os.path.join(ROOT, "dist", top + ".zip")
os.makedirs(os.path.dirname(out), exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in ("install.py", "README.txt", "README.md"):
        z.write(os.path.join(ROOT, f), top + "/" + f)
    for d, dirs, files in os.walk(os.path.join(ROOT, "MacsAutoBridge")):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in files:
            if f.endswith(".pyc"):
                continue
            full = os.path.join(d, f)
            z.write(full, top + "/" + os.path.relpath(full, ROOT).replace("\\", "/"))
print(out)
for n in zipfile.ZipFile(out).namelist(): print("  ", n)
