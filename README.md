# MacsAutoBridge 1.0.0

*by Mac Dawson (MDVFX). Quick-start version: `README.txt`.*

One-click Substance Painter → Maya. It finds each object's exported textures, builds a
material (Arnold `aiStandardSurface` by default), wires every map, and assigns it to the
object.

**Needs:** Maya 2025 or newer (made and tested on Maya 2026). Arnold (MtoA, ships with
Maya) for the Arnold shaders. No other plug-ins.

---

## Install (about 10 seconds)

1. Unzip the download anywhere.
2. Open Maya and **drag `install.py` into the viewport**.
3. A new **MacsAutoBridge** shelf appears. Click its button to open the tool.

To upgrade, drag a newer `install.py` in the same way. Settings are kept.
To uninstall, run this in the Script Editor (Python tab):
`import macs_autobridge; macs_autobridge.uninstall()`

---

## Folder setup

Give each object its own folder, named after the object, and export the Substance
textures into it:

```
sourceimages/
  MyTextures/                 <- you point the tool at this folder
    Ball/
      Ball_Rubber_BaseColor.1001.png
      Ball_Rubber_Roughness.1001.png
      Ball_Rubber_Normal.1001.png
      ...
    Crate/
      Crate_Wood_BaseColor.png
      Crate_Metal_BaseColor.png
      ...
```

* **The names don't have to match exactly.** Case, namespaces (`char:Ball`), suffixes such
  as `_GEO`, `_MESH`, `_LOW` and trailing numbers (`Ball1`) are ignored.
* **Group folders:** a folder named after a *group* is used by every mesh inside it.
* **One material per texture set:** each Substance texture set becomes
  `<Object>_<TextureSet>_MTL`.
* **Several texture sets on one object:** each material goes onto the faces that already
  use a material with the texture set's name. Substance names texture sets after your FBX's
  materials, so this works automatically. If nothing matches, the first set goes on the
  whole object and the log tells you.
* **Loose files:** textures dropped straight into the picked folder still work if their
  file names start with the object name.

### Substance Painter export settings

Any preset that names files `$mesh_$textureSet_$channel` works, for example the
*Arnold (AiStandard)* or *Autodesk Maya OpenPBR* presets. Recognised maps:

| Map | File name endings it understands |
|---|---|
| Base color | BaseColor, Base_Color, Albedo, Diffuse, Color |
| Metalness | Metalness, Metallic, Metal |
| Roughness | Roughness, Rough (or Glossiness/Smoothness, inverted automatically) |
| Normal | Normal, Normal_OpenGL, Normal_DirectX (green flipped automatically) |
| Height | Height, Displacement, Bump |
| Emissive | Emissive, Emission |
| Opacity | Opacity, Alpha |
| Packed ORM | OcclusionRoughnessMetallic, ORM |
| AO | AO, AmbientOcclusion, Mixed_AO (found but not used; shaders don't take AO) |

UDIMs (`.1001.png`) are detected automatically. Supported formats: png, exr, tif, tga,
jpg, psd, bmp, hdr, tx.

---

## Using it

1. **Texture folder:** click **Browse...** and pick the folder that holds the per-object
   folders.
2. **Settings:**
   * **Material:** Arnold Standard Surface (default), OpenPBR Surface, Standard Surface
     or Arnold Toon.
   * **Height map:** Bump (default), Displacement (also turns on Arnold subdivision if it
     was off) or Ignore.
   * **Height strength:** the bump depth, or the displacement scale.
   * **Normal map:** Auto, OpenGL or DirectX.
3. **What will be bridged:** a preview of every object → folder match. Double-click a row
   to select those objects.
4. **Bridge Selected** or **Bridge All**.

**Running it again** (after re-exporting from Substance) updates the same materials. Nothing
is duplicated, and your manual shader tweaks stay. Choosing a different Material type and
re-running swaps the shader but keeps the textures and assignments.

**Ctrl+Z** undoes a whole bridge in one step.

Colour spaces are set for you: Base Color and Emissive use sRGB, everything else uses Raw.

### Scripting

```python
import macs_autobridge
macs_autobridge.bridge(r"D:/MyProject/sourceimages/MyTextures",
                       shader="aiStandardSurface", height_mode="bump",
                       selected_only=False)
```

---

## Troubleshooting

* **"None of the selected objects have a matching texture folder"**: check the preview
  list. The folder name must resemble the object's name (or one of its parent groups).
* **Arnold shaders missing from the dropdown**: enable `mtoa` in
  Windows > Settings/Preferences > Plug-in Manager.
* **Normal map looks inverted (dents look like bumps)**: set Normal map to DirectX (or
  OpenGL) and run again.
* **aiToon:** it has no metalness or opacity input, so those maps are skipped (the log says
  so).
