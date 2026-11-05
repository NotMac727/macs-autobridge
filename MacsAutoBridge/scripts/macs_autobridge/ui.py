"""MacsAutoBridge window (Maya 2025+ / PySide6)."""

import os

import maya.cmds as cmds
import maya.OpenMayaUI as omui
from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import wrapInstance

from . import __version__
from . import builder
from . import matching

WINDOW_NAME = "MacsAutoBridgeWindow"
OPT = "macsAutoBridge_"          # optionVar prefix (settings remembered between sessions)

HELP_TEXT = """<b>MacsAutoBridge</b> plugs Substance Painter textures into Maya materials.<br><br>
<b>1. Folder layout</b><br>
Make one folder per object, named after the object, and export the Substance textures
into it:<br>
<code>&nbsp;&nbsp;sourceimages/MyTextures/<b>Ball</b>/Ball_Rubber_BaseColor.1001.png</code><br>
<code>&nbsp;&nbsp;sourceimages/MyTextures/<b>Ball</b>/Ball_Rubber_Roughness.1001.png ...</code><br>
The folder name doesn't have to match exactly: case, namespaces, suffixes like _GEO and
trailing numbers are ignored. A folder named after a <i>group</i> applies to every mesh
inside it.<br><br>
<b>2. Texture folder</b>: browse to the folder that holds those per-object folders.<br><br>
<b>3. Bridge Selected / Bridge All</b>: creates one material per Substance texture set
(&lt;Object&gt;_&lt;TextureSet&gt;_MTL) and assigns it. Run it again after re-exporting and
the same materials are updated instead of duplicated; your tweaks to the shader stay.<br><br>
<b>Several texture sets on one object</b>: each set's material goes onto the faces that
currently use a material with the same name as the texture set (Substance names texture sets
after the materials in your FBX).<br><br>
Ctrl+Z undoes a whole bridge in one step."""


def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


def _opt_get(key, default):
    name = OPT + key
    if cmds.optionVar(exists=name):
        return cmds.optionVar(q=name)
    return default


def _opt_set(key, value):
    name = OPT + key
    if isinstance(value, float):
        cmds.optionVar(floatValue=(name, value))
    elif isinstance(value, int):
        cmds.optionVar(intValue=(name, value))
    else:
        cmds.optionVar(stringValue=(name, value))


class AutoBridgeWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(AutoBridgeWindow, self).__init__(parent or maya_main_window())
        self.setObjectName(WINDOW_NAME)
        self.setWindowTitle("MacsAutoBridge %s" % __version__)
        icon = os.path.join(os.path.dirname(__file__), "..", "..", "icons", "macsAutoBridge_256.png")
        if os.path.isfile(icon):
            self.setWindowIcon(QtGui.QIcon(icon))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.resize(640, 640)
        self._build()
        self._load_settings()
        self.refresh_preview()

    # ----------------------------------------------------------------- layout
    def _build(self):
        main = QtWidgets.QVBoxLayout(self)

        # 1. Folder
        box1 = QtWidgets.QGroupBox("1. Texture folder")
        l1 = QtWidgets.QHBoxLayout(box1)
        self.folder_edit = QtWidgets.QLineEdit()
        self.folder_edit.setPlaceholderText("Browse to the folder that holds one folder per object...")
        self.folder_edit.editingFinished.connect(self._folder_changed)
        browse = QtWidgets.QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        l1.addWidget(self.folder_edit, 1)
        l1.addWidget(browse)
        main.addWidget(box1)

        # 2. Settings
        box2 = QtWidgets.QGroupBox("2. Settings")
        form = QtWidgets.QFormLayout(box2)
        self.shader_combo = QtWidgets.QComboBox()
        for st in builder.available_shaders():
            self.shader_combo.addItem(builder.SHADERS[st]["label"], st)
        self.shader_combo.setToolTip("The material type to create. Re-running with a different "
                                     "type swaps the shader and keeps the textures.")
        form.addRow("Material:", self.shader_combo)

        self.height_combo = QtWidgets.QComboBox()
        self.height_combo.addItem("Bump (safe, fast)", "bump")
        self.height_combo.addItem("Displacement (moves the geometry at render time)", "displacement")
        self.height_combo.addItem("Ignore", "ignore")
        form.addRow("Height map:", self.height_combo)

        self.strength_spin = QtWidgets.QDoubleSpinBox()
        self.strength_spin.setRange(0.0, 100.0)
        self.strength_spin.setDecimals(3)
        self.strength_spin.setSingleStep(0.01)
        self.strength_spin.setToolTip("Bump depth, or displacement scale in scene units.")
        form.addRow("Height strength:", self.strength_spin)

        self.normal_combo = QtWidgets.QComboBox()
        self.normal_combo.addItem("Auto (OpenGL unless the file says DirectX)", "auto")
        self.normal_combo.addItem("OpenGL", "opengl")
        self.normal_combo.addItem("DirectX (flip green)", "directx")
        form.addRow("Normal map:", self.normal_combo)
        main.addWidget(box2)

        # 3. Preview
        box3 = QtWidgets.QGroupBox("3. What will be bridged")
        l3 = QtWidgets.QVBoxLayout(box3)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Object(s)", "Folder", "Texture sets", "Maps"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        self.tree.itemDoubleClicked.connect(self._select_from_tree)
        l3.addWidget(self.tree, 1)
        row = QtWidgets.QHBoxLayout()
        self.preview_label = QtWidgets.QLabel("")
        self.preview_label.setWordWrap(True)
        refresh = QtWidgets.QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_preview)
        row.addWidget(self.preview_label, 1)
        row.addWidget(refresh)
        l3.addLayout(row)
        main.addWidget(box3, 2)

        # Buttons
        btns = QtWidgets.QHBoxLayout()
        help_btn = QtWidgets.QPushButton("?")
        help_btn.setFixedWidth(28)
        help_btn.clicked.connect(self._help)
        self.sel_btn = QtWidgets.QPushButton("Bridge Selected")
        self.all_btn = QtWidgets.QPushButton("Bridge All")
        for b in (self.sel_btn, self.all_btn):
            b.setMinimumHeight(36)
        self.sel_btn.setStyleSheet("QPushButton{background:#a33a3a;color:white;font-weight:bold;}"
                                   "QPushButton:hover{background:#c04545;}")
        self.sel_btn.clicked.connect(lambda: self._bridge(True))
        self.all_btn.clicked.connect(lambda: self._bridge(False))
        btns.addWidget(help_btn)
        btns.addWidget(self.sel_btn, 2)
        btns.addWidget(self.all_btn, 1)
        main.addLayout(btns)

        # Log
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Results show up here.")
        self.log.setMaximumBlockCount(2000)
        main.addWidget(self.log, 1)

        for w in (self.shader_combo, self.height_combo, self.normal_combo):
            w.currentIndexChanged.connect(self._save_settings)
        self.strength_spin.valueChanged.connect(self._save_settings)

    # --------------------------------------------------------------- settings
    def _load_settings(self):
        self.folder_edit.setText(_opt_get("root", ""))
        for combo, key, default in ((self.shader_combo, "shader", "aiStandardSurface"),
                                    (self.height_combo, "height", "bump"),
                                    (self.normal_combo, "normal", "auto")):
            i = combo.findData(_opt_get(key, default))
            combo.setCurrentIndex(max(i, 0))
        self.strength_spin.setValue(float(_opt_get("strength", 0.1)))

    def _save_settings(self, *args):
        _opt_set("root", self.folder_edit.text().strip())
        _opt_set("shader", self.shader_combo.currentData() or "")
        _opt_set("height", self.height_combo.currentData())
        _opt_set("normal", self.normal_combo.currentData())
        _opt_set("strength", float(self.strength_spin.value()))

    def options(self):
        return builder.Options(shader=self.shader_combo.currentData(),
                               height_mode=self.height_combo.currentData(),
                               height_strength=float(self.strength_spin.value()),
                               normal_mode=self.normal_combo.currentData())

    def root(self):
        return os.path.normpath(self.folder_edit.text().strip()) if self.folder_edit.text().strip() else ""

    # ---------------------------------------------------------------- actions
    def _browse(self):
        start = self.root()
        if not start or not os.path.isdir(start):
            start = os.path.join(cmds.workspace(q=True, rootDirectory=True), "sourceimages")
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Folder that holds your per-object "
                                                          "texture folders", start)
        if path:
            self.folder_edit.setText(os.path.normpath(path))
            self._folder_changed()

    def _folder_changed(self):
        self._save_settings()
        self.refresh_preview()

    def refresh_preview(self):
        self.tree.clear()
        root = self.root()
        if not root:
            self.preview_label.setText("Pick a texture folder to see which objects it will match.")
            return
        if not os.path.isdir(root):
            self.preview_label.setText("<span style='color:#e66'>That folder doesn't exist.</span>")
            return
        try:
            jobs, unmatched = builder.plan(root, None)
        except Exception as e:
            self.preview_label.setText(str(e))
            return
        for job in jobs:
            names = ", ".join(m.split("|")[-1] for m in job.meshes)
            folder = os.path.relpath(job.folder, root) if job.tier != 5 else "(loose files)"
            sets = ", ".join(s.name or "(single)" for s in job.sets)
            maps = " | ".join(s.describe_maps() for s in job.sets)
            item = QtWidgets.QTreeWidgetItem([names, folder, sets, maps])
            item.setData(0, QtCore.Qt.UserRole, job.meshes)
            tip = "%s\n%s" % (job.folder, matching.TIER_NOTES.get(job.tier, ""))
            for c in range(4):
                item.setToolTip(c, tip)
            self.tree.addTopLevelItem(item)
        for c in range(4):
            self.tree.resizeColumnToContents(c)
        msg = "%d texture folder(s) matched in the scene." % len(jobs)
        if unmatched:
            msg += " %d mesh(es) have no folder and will be skipped." % len(unmatched)
        msg += " Double-click a row to select those objects."
        self.preview_label.setText(msg)

    def _select_from_tree(self, item, col):
        meshes = [m for m in (item.data(0, QtCore.Qt.UserRole) or []) if cmds.objExists(m)]
        if meshes:
            cmds.select(meshes, replace=True)

    def _bridge(self, selected_only):
        self._save_settings()
        if not self.shader_combo.currentData():
            QtWidgets.QMessageBox.warning(self, "MacsAutoBridge", "No supported material types found.")
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            log = builder.run(self.root(), self.options(), selected_only=selected_only)
        except Exception as e:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.log.appendPlainText("ERROR: %s\n" % e)
            QtWidgets.QMessageBox.warning(self, "MacsAutoBridge", str(e))
            return
        finally:
            if QtWidgets.QApplication.overrideCursor():
                QtWidgets.QApplication.restoreOverrideCursor()
        self.log.appendPlainText(log.text() + "\n")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
        msg = "MacsAutoBridge: done" + (" with %d warning(s), see the log" % log.warnings
                                        if log.warnings else "")
        cmds.inViewMessage(amg="<hl>%s</hl>" % msg, pos="topCenter", fade=True)
        self.refresh_preview()

    def _help(self):
        QtWidgets.QMessageBox.information(self, "MacsAutoBridge help", HELP_TEXT)


def show():
    app = QtWidgets.QApplication.instance()
    for w in app.topLevelWidgets() if app else []:
        if w.objectName() == WINDOW_NAME:
            w.close()
            w.deleteLater()
    win = AutoBridgeWindow()
    win.show()
    return win
