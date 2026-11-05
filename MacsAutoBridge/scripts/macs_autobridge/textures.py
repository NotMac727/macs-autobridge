"""Finding and reading Substance Painter texture exports.

Pure Python (no Maya imports) so it can be tested outside Maya.

Expected export naming (Substance's default "$mesh_$textureSet_$channel"):
    <Mesh>_<TextureSet>_<Map>.<UDIM>.<ext>     e.g. Ball_Rubber_BaseColor.1001.png
    <Mesh>_<TextureSet>_<Map>.<ext>            (no UDIMs)
    <TextureSet>_<Map>.<ext>                   (other presets)
"""

import os
import re

IMAGE_EXTS = (".exr", ".tif", ".tiff", ".png", ".tga", ".jpg", ".jpeg", ".psd", ".bmp", ".hdr", ".tx")
# When the same map exists in several formats, the first one listed here wins.
# .tx is last because Arnold auto-generates it next to the real file.
EXT_PRIORITY = {ext: i for i, ext in enumerate(IMAGE_EXTS)}

# Map role -> names Substance (or a human) might use, compared lowercase with
# separators removed ("Base_Color" -> "basecolor").
ROLE_ALIASES = {
    "baseColor": ["basecolor", "basecolour", "albedo", "diffuse", "diff", "color", "colour", "col",
                  "basecolormap", "albedomap", "diffusemap"],
    "metalness": ["metalness", "metallic", "metal", "metalic", "metalnessmap", "metallicmap"],
    "roughness": ["roughness", "rough", "rgh", "roughnessmap"],
    "glossiness": ["glossiness", "gloss", "smoothness"],
    "normal": ["normal", "normalopengl", "normalgl", "normalogl", "nrm", "norm", "nor", "normalmap"],
    "normalDX": ["normaldirectx", "normaldx", "normaldirect"],
    "height": ["height", "heightmap", "displacement", "displace", "disp", "bump", "bumpmap"],
    "emissive": ["emissive", "emission", "emit", "emissivecolor", "emissioncolor", "emissive color"],
    "opacity": ["opacity", "alpha", "opacitymap"],
    "ao": ["ambientocclusion", "ao", "occlusion", "mixedao", "aomap"],
    "orm": ["occlusionroughnessmetallic", "orm"],
}
_ALIAS_TO_ROLE = {}
for _role, _names in ROLE_ALIASES.items():
    for _n in _names:
        _ALIAS_TO_ROLE[re.sub(r"[^a-z0-9]", "", _n)] = _role

ROLE_LABELS = {
    "baseColor": "Base Color", "metalness": "Metalness", "roughness": "Roughness",
    "glossiness": "Glossiness", "normal": "Normal", "normalDX": "Normal (DirectX)",
    "height": "Height", "emissive": "Emissive", "opacity": "Opacity", "ao": "AO",
    "orm": "ORM (packed)",
}

_SPLIT = re.compile(r"[_\-\s.]+")
_UDIM = re.compile(r"^(?P<base>.*?)[._](?P<udim>1\d{3})$")


def squash(text):
    """Lowercase and drop everything that isn't a letter or digit."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def is_image(filename):
    return os.path.splitext(filename)[1].lower() in IMAGE_EXTS


class TextureFile(object):
    def __init__(self, path, prefix, role, udim):
        self.path = path
        self.prefix = prefix          # everything before the map name, e.g. "Ball_Rubber"
        self.role = role              # e.g. "baseColor", or None if unknown
        self.udim = udim              # int or None
        self.ext = os.path.splitext(path)[1].lower()


def parse_texture_filename(path):
    """Split a texture file name into (prefix, role, udim). role is None if unrecognised."""
    stem = os.path.splitext(os.path.basename(path))[0]
    udim = None
    m = _UDIM.match(stem)
    if m:
        stem, udim = m.group("base"), int(m.group("udim"))
    tokens = [t for t in _SPLIT.split(stem) if t]
    if not tokens:
        return "", None, udim
    # Try the longest map name first so "Normal_OpenGL" beats "OpenGL".
    for k in (3, 2, 1):
        if k > len(tokens):
            continue
        role = _ALIAS_TO_ROLE.get(squash("".join(tokens[-k:])))
        if role:
            return "_".join(tokens[:-k]), role, udim
    return "_".join(tokens), None, udim


class TextureSet(object):
    """All maps that belong to one Substance texture set (= one material)."""

    def __init__(self, prefix):
        self.prefix = prefix
        self.name = prefix            # cleaned up later by strip_owner_prefix()
        self.maps = {}                # role -> TextureFile (first UDIM tile or the single file)
        self.ignored = []             # files we found but couldn't use

    @property
    def is_udim(self):
        return any(f.udim is not None for f in self.maps.values())

    def roles(self):
        return sorted(self.maps)

    def describe_maps(self):
        return ", ".join(ROLE_LABELS.get(r, r) for r in self.roles())


def _better(new, old):
    """Should `new` replace `old` for the same role in the same set?"""
    if old is None:
        return True
    if EXT_PRIORITY.get(new.ext, 99) != EXT_PRIORITY.get(old.ext, 99):
        return EXT_PRIORITY.get(new.ext, 99) < EXT_PRIORITY.get(old.ext, 99)
    # Same format: keep the lowest UDIM tile (1001) as the file node path.
    return (new.udim or 0) < (old.udim or 0)


def scan_folder(folder, only_prefix=None):
    """Read every image in `folder` (not recursive) and group into TextureSets.

    only_prefix: if given, only keep files whose prefix starts with this name
    (used when textures for several objects are dumped loose in one folder).
    Returns a list of TextureSet sorted by name.
    """
    sets = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    for fn in names:
        full = os.path.join(folder, fn)
        if not os.path.isfile(full) or not is_image(fn):
            continue
        prefix, role, udim = parse_texture_filename(fn)
        if only_prefix is not None and not squash(prefix).startswith(squash(only_prefix)):
            continue
        tf = TextureFile(full.replace("\\", "/"), prefix, role, udim)
        key = squash(prefix)
        ts = sets.get(key)
        if ts is None:
            ts = sets[key] = TextureSet(prefix)
        if role is None:
            ts.ignored.append(tf)
            continue
        if _better(tf, ts.maps.get(role)):
            ts.maps[role] = tf
    # Drop "sets" that are only junk files (e.g. a stray preview.png).
    result = [s for s in sets.values() if s.maps]
    # If both an OpenGL and a DirectX normal exist, use the OpenGL one (Maya is OpenGL).
    for s in result:
        if "normal" in s.maps and "normalDX" in s.maps:
            s.ignored.append(s.maps.pop("normalDX"))
    return sorted(result, key=lambda s: s.prefix.lower())


def strip_owner_prefix(texture_sets, owner_names):
    """Turn "AutoBridgeTestBall_openPBR_shader1" into "openPBR_shader1".

    Substance puts the mesh name in front of the texture set name. Remove it
    when it matches the object/folder name so material names don't repeat it.
    """
    owners = [squash(n) for n in owner_names if n]
    for ts in texture_sets:
        tokens = [t for t in _SPLIT.split(ts.prefix) if t]
        name = ts.prefix
        for owner in owners:
            acc = ""
            for i, tok in enumerate(tokens):
                acc += squash(tok)
                if acc == owner:
                    name = "_".join(tokens[i + 1:])
                    break
                if not owner.startswith(acc):
                    break
            if name != ts.prefix:
                break
        ts.name = name
    return texture_sets


def safe_node_name(text):
    """Make a string usable as a Maya node name."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", text).strip("_")
    name = re.sub(r"_+", "_", name)
    if not name:
        name = "material"
    if name[0].isdigit():
        name = "_" + name
    return name
