import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "MacsAutoBridge", "scripts"))
from PySide6 import QtWidgets, QtGui, QtCore
app = QtWidgets.QApplication([])
import maya.standalone; maya.standalone.initialize()
import maya.cmds as cmds

# (icons are built by dev/make_icons.py)

# ---- UI smoke test
cmds.loadPlugin("mtoa", quiet=True)
PROJECT = os.path.normpath(os.path.join(HERE, "..", "..", "AutoBridgeTestBall")).replace("\\", "/")
cmds.optionVar(sv=("macsAutoBridge_root", PROJECT + "/sourceimages/Materials_textures"))
cmds.workspace(PROJECT, openWorkspace=True)
cmds.file(PROJECT + "/scenes/AutobridgeTestScene.ma", open=True, force=True)
import faulthandler; faulthandler.enable()
from macs_autobridge import ui; print("IMPORTED", flush=True)
import maya.OpenMayaUI as omui; print("MAINWIN", omui.MQtUtil.mainWindow(), flush=True)
print("BEFORE", flush=True)
try:
    w = ui.AutoBridgeWindow()
except BaseException as e:
    import traceback; traceback.print_exc(); sys.stdout.flush(); sys.stderr.flush(); os._exit(1)
print("AFTER", flush=True)
print("SHADERS", [w.shader_combo.itemData(i) for i in range(w.shader_combo.count())])
print("PREVIEW", w.preview_label.text())
it = w.tree.topLevelItem(0); print("ROW", [it.text(c) for c in range(4)])
w.show(); app.processEvents()
cmds.select("AutoBridgeTestBall"); w._bridge(True); print("LOG", w.log.toPlainText())
cmds.optionVar(remove="macsAutoBridge_root")
sys.stdout.flush(); os._exit(0)
