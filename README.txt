MacsAutoBridge 1.0.0  -  by Mac Dawson (MDVFX)
Substance Painter textures -> Maya materials in one click.
Needs Maya 2025 or newer (Arnold comes with Maya).

=====================================================
 INSTALL (one time)
=====================================================
1. Unzip this folder anywhere.
2. Open Maya.
3. Drag "install.py" into the Maya viewport.
4. A new "MacsAutoBridge" shelf appears. Click the button.

=====================================================
 SET UP YOUR FOLDERS
=====================================================
Make one folder per object, named the same as the object
in your Outliner, and export your Substance textures into it.

  sourceimages/
     MyTextures/          <- you pick this folder in the tool
        Ball/             <- object called "Ball"
           Ball_Rubber_BaseColor.1001.png
           Ball_Rubber_Roughness.1001.png
           ...
        Crate/            <- object called "Crate"
           ...

Tip: names don't have to be perfect. Upper/lower case,
_GEO endings and numbers like "Ball1" are fine.

=====================================================
 USE IT
=====================================================
1. Click Browse... and pick the folder that holds your
   object folders (MyTextures in the example).
2. Pick a material type (Arnold Standard Surface is default).
3. Check the list: it shows which objects found textures.
4. Select your object(s) and click "Bridge Selected",
   or click "Bridge All" for everything.

Done! The material is made, textures are hooked up and it's
assigned to your object.

Re-exported from Substance? Just click Bridge again.
It updates the same material instead of making a new one.

Messed up? Ctrl+Z undoes the whole thing.

=====================================================
 PROBLEMS?
=====================================================
- "No matching texture folder": the folder name needs to match
  the object name in the Outliner.
- Bumps look like dents: change "Normal map" to DirectX and
  click Bridge again.
- No Arnold materials in the list: turn on mtoa in
  Windows > Settings/Preferences > Plug-in Manager.

More details are in README.md.
