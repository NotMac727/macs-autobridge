"""MacsAutoBridge: Substance Painter textures -> Maya materials, one click.

Shelf button command:
    import macs_autobridge; macs_autobridge.show()
"""

__version__ = "1.0.0"


def show():
    """Open (or re-open) the MacsAutoBridge window."""
    from . import ui
    return ui.show()


def uninstall():
    """Remove the shelf, the .mod file and the installed module folder."""
    import os
    import shutil
    import maya.cmds as cmds
    import maya.mel as mel
    if cmds.shelfLayout("MacsAutoBridge", exists=True):
        cmds.deleteUI("MacsAutoBridge", layout=True)
        shelf_file = os.path.join(cmds.internalVar(userPrefDir=True), "shelves",
                                  "shelf_MacsAutoBridge.mel")
        if os.path.isfile(shelf_file):
            os.remove(shelf_file)
        mel.eval("saveAllShelves $gShelfTopLevel")
    modules = os.path.join(cmds.internalVar(userAppDir=True), "modules")
    mod_file = os.path.join(modules, "MacsAutoBridge.mod")
    if os.path.isfile(mod_file):
        os.remove(mod_file)
    shutil.rmtree(os.path.join(modules, "MacsAutoBridge"), ignore_errors=True)
    print("MacsAutoBridge uninstalled. Restart Maya to finish.")


def bridge(root, shader="aiStandardSurface", height_mode="bump", height_strength=0.1,
           normal_mode="auto", selected_only=True):
    """Run without the window (for scripts). Returns the log text."""
    from . import builder
    opts = builder.Options(shader, height_mode, height_strength, normal_mode)
    return builder.run(root, opts, selected_only=selected_only).text()
