"""MacsAutoBridge installer.

HOW TO INSTALL: drag this file from your file browser into the Maya viewport.

What it does:
  1. copies the MacsAutoBridge folder into  Documents/maya/modules/
  2. writes MacsAutoBridge.mod there so Maya loads it on every launch
  3. adds a "MacsAutoBridge" shelf with a button that opens the tool
It works right away, no restart needed. Dragging a newer version in upgrades it.
"""

import importlib
import os
import shutil
import sys

import maya.cmds as cmds
import maya.mel as mel

NAME = "MacsAutoBridge"
VERSION = "1.0.0"
SHELF = "MacsAutoBridge"
# The shelf button finds the tool by itself even if Maya's paths aren't set up yet.
COMMAND_TEMPLATE = (
    "import sys\n"
    "try:\n"
    "    import macs_autobridge\n"
    "except ImportError:\n"
    "    sys.path.insert(0, r'{scripts}')\n"
    "    import macs_autobridge\n"
    "macs_autobridge.show()\n"
)


def onMayaDroppedPythonFile(*args):
    """Maya calls this when the file is dropped into the viewport."""
    try:
        install()
    except Exception as e:
        cmds.confirmDialog(title="MacsAutoBridge install failed", message=str(e), button=["OK"])
        raise


def install(modules_dir=None, make_shelf=True):
    if int(cmds.about(apiVersion=True)) < 20250000:
        raise RuntimeError("MacsAutoBridge needs Maya 2025 or newer.")

    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, NAME)
    if not os.path.isdir(os.path.join(src, "scripts", "macs_autobridge")):
        raise RuntimeError("Can't find the '%s' folder next to install.py.\n"
                           "Unzip the whole download first, then drag install.py in." % NAME)

    modules_dir = modules_dir or os.path.join(cmds.internalVar(userAppDir=True), "modules")
    dest = os.path.join(modules_dir, NAME)
    if not os.path.isdir(modules_dir):
        os.makedirs(modules_dir)
    if os.path.normcase(os.path.normpath(src)) != os.path.normcase(os.path.normpath(dest)):
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    with open(os.path.join(modules_dir, NAME + ".mod"), "w") as f:
        f.write("+ %s %s ./%s\n" % (NAME, VERSION, NAME))

    # Make it usable in this Maya session without a restart.
    scripts = os.path.normpath(os.path.join(dest, "scripts"))
    known = [os.path.normcase(os.path.normpath(p)) for p in sys.path if p]
    if os.path.normcase(scripts) not in known:
        sys.path.insert(0, scripts)
    for mod in [m for m in sys.modules if m == "macs_autobridge" or m.startswith("macs_autobridge.")]:
        del sys.modules[mod]                  # so an upgrade loads the new code
    importlib.invalidate_caches()             # Python caches folder contents; make it look again
    try:
        importlib.import_module("macs_autobridge")
    except ImportError as e:
        raise RuntimeError("Files were copied to %s but Python can't import them yet (%s).\n"
                           "Restart Maya and the tool will load." % (dest, e))
    icons = os.path.join(dest, "icons")
    os.environ["XBMLANGPATH"] = os.environ.get("XBMLANGPATH", "") + os.pathsep + icons

    if make_shelf and not cmds.about(batch=True):
        _make_shelf(os.path.join(icons, "macsAutoBridge.png").replace("\\", "/"), scripts)
        cmds.confirmDialog(
            title="MacsAutoBridge installed",
            message="MacsAutoBridge %s is installed.\n\nClick the button on the new "
                    "'%s' shelf to open it." % (VERSION, SHELF),
            button=["Nice"])
    print("MacsAutoBridge %s installed to %s" % (VERSION, dest))
    return dest


def _make_shelf(icon, scripts):
    top = mel.eval("$tmp = $gShelfTopLevel")
    if cmds.shelfLayout(SHELF, exists=True):
        for child in cmds.shelfLayout(SHELF, q=True, childArray=True) or []:
            cmds.deleteUI(child)
    else:
        mel.eval('addNewShelfTab "%s"' % SHELF)
    cmds.shelfButton(parent=SHELF, label="MacsAutoBridge", image=icon, image1=icon,
                     annotation="MacsAutoBridge: Substance Painter textures -> Maya materials",
                     command=COMMAND_TEMPLATE.format(scripts=scripts), sourceType="python",
                     imageOverlayLabel="")
    cmds.tabLayout(top, edit=True, selectTab=SHELF)
    mel.eval("saveAllShelves $gShelfTopLevel")
