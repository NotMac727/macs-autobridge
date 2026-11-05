"""Matching scene object names to texture folders, as forgivingly as possible.

Pure Python (no Maya imports).

Match tiers, best first:
  1. exact name                      "Ball"        == "Ball"
  2. ignoring upper/lower case       "ball"        == "Ball"
  3. ignoring namespaces, separators and common suffixes
                                     "char:Ball_GEO" == "ball-geo" == "Ball"
  4. also ignoring trailing numbers  "Ball1"       == "Ball"
"""

import os
import re

from . import textures

# Trailing words people tack onto object or folder names. Only removed when they
# are a separate word ("Ball_GEO"), never from inside a word ("Pillow").
NAME_SUFFIXES = {
    "geo", "geom", "geometry", "msh", "mesh", "mdl", "model", "grp", "group", "shape",
    "low", "lo", "lowpoly", "high", "hi", "highpoly", "ply", "poly", "obj",
    "tex", "textures", "texture", "txt", "maps", "export", "exports", "sp", "substance",
    "mat", "mtl", "material", "materials", "shd", "shader",
}

_WORDS = re.compile(r"[_\-\s.]+")


def short_name(name):
    """'|grp|char:Ball' -> 'char:Ball'."""
    return name.split("|")[-1]


def strip_namespace(name):
    return short_name(name).split(":")[-1]


def clean_name(name):
    """Readable name with namespace and suffix words removed: 'char:Robot_GEO' -> 'Robot'."""
    words = [w for w in _WORDS.split(strip_namespace(name)) if w]
    while len(words) > 1 and words[-1].lower() in NAME_SUFFIXES:
        words.pop()
    return "_".join(words)


def core_name(name):
    """Tier-3 key: no namespace, no separators, no common suffix words, lowercase."""
    words = [w for w in _WORDS.split(strip_namespace(name)) if w]
    while len(words) > 1 and words[-1].lower() in NAME_SUFFIXES:
        words.pop()
    return textures.squash("".join(words))


def core_name_no_digits(name):
    """Tier-4 key: like core_name but also drops trailing numbers ("Ball01" -> "ball")."""
    core = core_name(name)
    trimmed = re.sub(r"\d+$", "", core)
    return trimmed or core


def _keys(name):
    return (
        strip_namespace(name),
        strip_namespace(name).lower(),
        core_name(name),
        core_name_no_digits(name),
    )


class FolderIndex(object):
    """Every folder under the texture root (2 levels deep) plus the root itself."""

    MAX_DEPTH = 2

    def __init__(self, root):
        self.root = os.path.normpath(root) if root else ""
        self.folders = []          # list of (path, name)
        if self.root and os.path.isdir(self.root):
            self._walk(self.root, 0)

    def _walk(self, folder, depth):
        self.folders.append((folder.replace("\\", "/"), os.path.basename(folder)))
        if depth >= self.MAX_DEPTH:
            return
        try:
            entries = sorted(os.listdir(folder))
        except OSError:
            return
        for e in entries:
            full = os.path.join(folder, e)
            if os.path.isdir(full) and not e.startswith("."):
                self._walk(full, depth + 1)

    def find(self, object_name):
        """Return (folder_path, tier) for the best matching folder, or (None, None).

        If several folders tie, the shallowest one wins.
        """
        want = _keys(object_name)
        for tier in range(4):
            if not want[tier]:
                continue
            hits = [p for p, n in self.folders if _keys(n)[tier] == want[tier]]
            if hits:
                hits.sort(key=lambda p: (p.count("/"), p.lower()))
                return hits[0], tier + 1
        return None, None

    def loose_sets(self, object_name):
        """Texture sets sitting loose in the root whose file names start with the object name."""
        if not self.root:
            return []
        for name in (strip_namespace(object_name), core_name(object_name)):
            sets = textures.scan_folder(self.root, only_prefix=name)
            if sets:
                return sets
        return []


TIER_NOTES = {
    1: "exact match",
    2: "matched ignoring case",
    3: "matched ignoring namespace/suffix",
    4: "matched ignoring trailing numbers",
    5: "loose files in root folder",
}


def set_matches_material(set_name, material_name):
    """Does an existing material (e.g. 'Rubber_MTL', 'rubber_SG') belong to texture set 'Rubber'?"""
    if not set_name:
        return False
    a = core_name(set_name)
    b = core_name(re.sub(r"(?i)(_?sg|shadinggroup)$", "", strip_namespace(material_name)))
    return bool(a) and (a == b or core_name_no_digits(set_name) == core_name_no_digits(b))
