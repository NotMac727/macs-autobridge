"""Builds/updates materials in Maya from Substance Painter texture folders."""

import os

import maya.cmds as cmds
import maya.mel as mel

from . import matching
from . import textures

TAG = "macsAB"                      # prefix for the custom attributes we put on our nodes

# ---------------------------------------------------------------------------
# Shader profiles: which shader attribute each map plugs into.
# A value of None means the shader has no slot for that map (it gets skipped).
# ---------------------------------------------------------------------------
SHADERS = {
    "aiStandardSurface": {
        "label": "Arnold Standard Surface (aiStandardSurface)",
        "plugin": "mtoa",
        "baseColor": "baseColor", "metalness": "metalness", "roughness": "specularRoughness",
        "emissive": "emissionColor", "emissive_weight": ("emission", 1.0),
        "opacity": "opacity", "normal": "normalCamera", "base_weight": ("base", 1.0),
    },
    "openPBRSurface": {
        "label": "OpenPBR Surface (Maya built-in)",
        "plugin": None,
        "baseColor": "baseColor", "metalness": "baseMetalness", "roughness": "specularRoughness",
        "emissive": "emissionColor", "emissive_weight": ("emissionLuminance", 1000.0),
        "opacity": "geometryOpacity", "normal": "normalCamera", "base_weight": ("baseWeight", 1.0),
    },
    "standardSurface": {
        "label": "Standard Surface (Maya built-in)",
        "plugin": None,
        "baseColor": "baseColor", "metalness": "metalness", "roughness": "specularRoughness",
        "emissive": "emissionColor", "emissive_weight": ("emission", 1.0),
        "opacity": "opacity", "normal": "normalCamera", "base_weight": ("base", 1.0),
    },
    "aiToon": {
        "label": "Arnold Toon (aiToon)",
        "plugin": "mtoa",
        "baseColor": "baseColor", "metalness": None, "roughness": "specularRoughness",
        "emissive": "emissionColor", "emissive_weight": ("emission", 1.0),
        "opacity": None, "normal": "normalCamera", "base_weight": ("base", 1.0),
    },
}
SHADER_ORDER = ["aiStandardSurface", "openPBRSurface", "standardSurface", "aiToon"]

HEIGHT_MODES = ["bump", "displacement", "ignore"]
NORMAL_MODES = ["auto", "opengl", "directx"]

COLOR_ROLES = {"baseColor", "emissive"}     # sRGB; every other map is Raw data


class Options(object):
    def __init__(self, shader="aiStandardSurface", height_mode="bump", height_strength=0.1,
                 normal_mode="auto"):
        self.shader = shader
        self.height_mode = height_mode
        self.height_strength = height_strength
        self.normal_mode = normal_mode


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
class Log(object):
    def __init__(self):
        self.lines = []
        self.warnings = 0

    def info(self, msg):
        self.lines.append(msg)

    def warn(self, msg):
        self.warnings += 1
        self.lines.append("WARNING: " + msg)

    def text(self):
        return "\n".join(self.lines)


def ensure_plugin(shader_type):
    plugin = SHADERS[shader_type]["plugin"]
    if plugin and not cmds.pluginInfo(plugin, q=True, loaded=True):
        try:
            cmds.loadPlugin(plugin, quiet=True)
        except RuntimeError:
            raise RuntimeError("%s needs the Arnold plug-in (mtoa), which isn't available. "
                               "Turn it on in Windows > Settings/Preferences > Plug-in Manager."
                               % shader_type)


def available_shaders():
    """Shader types this Maya can create (Arnold ones count if mtoa can be loaded)."""
    types = set(cmds.allNodeTypes())
    mtoa_ok = cmds.pluginInfo("mtoa", q=True, loaded=True) or \
        "mtoa" in (cmds.pluginInfo(q=True, listPlugins=True) or []) or _plugin_on_disk("mtoa")
    out = []
    for st in SHADER_ORDER:
        if SHADERS[st]["plugin"] == "mtoa":
            if mtoa_ok:
                out.append(st)
        elif st in types:
            out.append(st)
    return out


def _plugin_on_disk(name):
    for d in os.environ.get("MAYA_PLUG_IN_PATH", "").split(os.pathsep):
        if d and os.path.isfile(os.path.join(d, name + ".mll")):
            return True
    return False


def _set_tag(node, key, value):
    attr = TAG + "_" + key
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, dataType="string")
    cmds.setAttr(node + "." + attr, value, type="string")


def _get_tag(node, key):
    attr = TAG + "_" + key
    if cmds.objExists(node) and cmds.attributeQuery(attr, node=node, exists=True):
        return cmds.getAttr(node + "." + attr) or ""
    return None


def _tagged_nodes(key):
    """All nodes carrying a given tag attribute (any namespace)."""
    return cmds.ls("*.%s_%s" % (TAG, key), objectsOnly=True, recursive=True) or []


def _uuid(node):
    return cmds.ls(node, uuid=True)[0]


def _is_compound3(node, attr):
    return cmds.getAttr(node + "." + attr, type=True) in ("float3", "double3")


def _set_if_exists(node, attr, value):
    if cmds.attributeQuery(attr, node=node, exists=True):
        try:
            cmds.setAttr(node + "." + attr, value)
        except RuntimeError:
            pass


def _pick_colorspace(kind):
    names = cmds.colorManagementPrefs(q=True, inputSpaceNames=True) or []
    wanted = {
        "srgb": ["sRGB", "sRGB - Texture", "Utility - sRGB - Texture", "srgb_texture",
                 "sRGB Encoded Rec.709 (sRGB)"],
        "raw": ["Raw", "Utility - Raw", "raw", "Data"],
    }[kind]
    for w in wanted:
        if w in names:
            return w
    return None


def _texture_path(path):
    """Store project-relative paths when the texture lives inside the Maya project,
    so the scene keeps working if the whole project is moved to another computer."""
    root = (cmds.workspace(q=True, rootDirectory=True) or "").replace("\\", "/")
    p = path.replace("\\", "/")
    if root and p.lower().startswith(root.lower()):
        return p[len(root):]
    return p


# ---------------------------------------------------------------------------
# Scene side: which objects get which folder
# ---------------------------------------------------------------------------
class Job(object):
    """One texture folder and the scene objects that will use it."""

    def __init__(self, key, base_name, folder, tier, sets):
        self.key = key              # folder path (or root + name for loose files)
        self.base_name = base_name  # used to name materials, e.g. "AutoBridgeTestBall"
        self.folder = folder
        self.tier = tier
        self.sets = sets            # list of textures.TextureSet
        self.meshes = []            # long names of mesh transforms
        # Saved on our materials so a re-run finds them again. Uses the folder *name*
        # (not the full path) so it still works after the project is moved.
        self.tag_key = base_name.lower()


def mesh_transforms(nodes=None):
    """Long names of mesh transforms in `nodes` (and under them). None = whole scene."""
    if nodes is None:
        shapes = cmds.ls(type="mesh", noIntermediate=True, long=True) or []
    else:
        shapes = []
        for n in nodes:
            if cmds.nodeType(n) == "mesh":
                shapes.append(n)
            shapes += cmds.listRelatives(n, allDescendents=True, type="mesh", fullPath=True) or []
        shapes = [s for s in cmds.ls(shapes, noIntermediate=True, long=True) or []]
    out = []
    for s in shapes:
        parent = cmds.listRelatives(s, parent=True, fullPath=True)
        if parent and parent[0] not in out:
            out.append(parent[0])
    return out


def selected_nodes():
    sel = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    out = []
    for n in sel:
        if cmds.nodeType(n) == "mesh":
            n = cmds.listRelatives(n, parent=True, fullPath=True)[0]
        if n not in out:
            out.append(n)
    return out


def plan(root, nodes=None):
    """Work out which folder each mesh uses. Returns (jobs, unmatched_mesh_list)."""
    if not root or not os.path.isdir(root):
        raise RuntimeError("Pick a texture folder first (the folder that holds one folder per object).")
    index = matching.FolderIndex(root)
    jobs = {}
    unmatched = []
    for mesh in mesh_transforms(nodes):
        job = _job_for(mesh, index, jobs)
        if job is None:
            unmatched.append(mesh)
        elif mesh not in job.meshes:
            job.meshes.append(mesh)
    return sorted(jobs.values(), key=lambda j: j.base_name.lower()), unmatched


def _job_for(mesh, index, jobs):
    # Walk from the mesh up through its parent groups; the closest name with a folder wins.
    parts = mesh.split("|")
    for i in range(len(parts) - 1, 0, -1):
        name = parts[i]
        folder, tier = index.find(name)
        if folder:
            job = jobs.get(folder)
            if job is None:
                sets = textures.scan_folder(folder)
                if not sets:
                    continue            # empty folder: keep looking further up
                base = matching.clean_name(os.path.basename(folder.rstrip("/")))
                if os.path.normpath(folder) == os.path.normpath(index.root):
                    base = matching.clean_name(name)
                textures.strip_owner_prefix(sets, [base, matching.strip_namespace(name),
                                                   matching.clean_name(name)])
                job = jobs[folder] = Job(folder, base, folder, tier, sets)
            return job
    # Last resort: files for this object sitting loose in the root folder.
    name = matching.clean_name(parts[-1])
    key = index.root + "::" + matching.core_name(name)
    if key in jobs:
        return jobs[key]
    sets = index.loose_sets(name)
    if sets:
        textures.strip_owner_prefix(sets, [name])
        jobs[key] = Job(key, name, index.root, 5, sets)
        return jobs[key]
    return None


# ---------------------------------------------------------------------------
# Material building
# ---------------------------------------------------------------------------
def material_base(job, tset):
    if tset.name:
        return textures.safe_node_name(job.base_name + "_" + tset.name)
    return textures.safe_node_name(job.base_name)


def find_existing_material(job, tset):
    for node in _tagged_nodes("folder"):
        if _get_tag(node, "folder") == job.tag_key and _get_tag(node, "set") == tset.prefix.lower():
            if cmds.nodeType(node) == "shadingEngine":
                continue
            return node
    return None


def shading_group_of(shader):
    sgs = cmds.listConnections(shader + ".outColor", type="shadingEngine") or []
    return sgs[0] if sgs else None


def get_or_create_material(job, tset, opts, log):
    shader_type = opts.shader
    base = material_base(job, tset)
    existing = find_existing_material(job, tset)

    if existing and cmds.nodeType(existing) == shader_type:
        sg = shading_group_of(existing)
        if not sg:
            sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=base + "_SG")
            cmds.connectAttr(existing + ".outColor", sg + ".surfaceShader", force=True)
        log.info("  Updating existing material %s" % existing)
        return existing, sg, False

    shader = cmds.shadingNode(shader_type, asShader=True, name=base + "_MTL")
    _set_tag(shader, "folder", job.tag_key)
    _set_tag(shader, "set", tset.prefix.lower())

    if existing:
        # Same folder/texture set, but the shader type was changed in the dropdown:
        # swap the new shader onto the old shading group and remove the old shader.
        sg = shading_group_of(existing)
        old_name = existing
        old_uuid, new_uuid = _uuid(existing), _uuid(shader)
        for n in _tagged_nodes("owner"):
            if _get_tag(n, "owner") == old_uuid:
                _set_tag(n, "owner", new_uuid)      # keep the file nodes, just re-own them
        cmds.delete(existing)
        if sg:
            cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader", force=True)
        shader = cmds.rename(shader, old_name.split(":")[-1])
        log.info("  Replaced %s with a new %s (shader type changed)" % (old_name, shader_type))
    else:
        sg = None
        log.info("  Created %s (%s)" % (shader, shader_type))
    if not sg:
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=base + "_SG")
        cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader", force=True)
    _set_tag(sg, "folder", job.tag_key)
    return shader, sg, existing is None


_P2D_ATTRS = [
    ("coverage", "coverage"), ("translateFrame", "translateFrame"), ("rotateFrame", "rotateFrame"),
    ("mirrorU", "mirrorU"), ("mirrorV", "mirrorV"), ("stagger", "stagger"), ("wrapU", "wrapU"),
    ("wrapV", "wrapV"), ("repeatUV", "repeatUV"), ("offset", "offset"), ("rotateUV", "rotateUV"),
    ("noiseUV", "noiseUV"), ("vertexUvOne", "vertexUvOne"), ("vertexUvTwo", "vertexUvTwo"),
    ("vertexUvThree", "vertexUvThree"), ("vertexCameraOne", "vertexCameraOne"),
    ("outUV", "uvCoord"), ("outUvFilterSize", "uvFilterSize"),
]


def _owned(material_uuid, kind):
    """Our helper nodes of a given kind ("file", "helper", "place2d") for one material."""
    out = []
    for n in _tagged_nodes("owner"):
        if _get_tag(n, "owner") == material_uuid and _get_tag(n, "kind") == kind:
            out.append(n)
    return out


def _clear_network(material_uuid, shader, sg):
    """Remove the old wiring so the material can be re-wired cleanly (files are kept)."""
    helpers = _owned(material_uuid, "helper")
    if helpers:
        cmds.delete(helpers)
    for f in _owned(material_uuid, "file"):
        conns = cmds.listConnections(f, source=False, destination=True, plugs=True,
                                     connections=True) or []
        for src, dst in zip(conns[::2], conns[1::2]):
            dnode = dst.split(".")[0]
            if cmds.nodeType(dnode) in ("place2dTexture", "textureList", "defaultTextureList"):
                continue
            try:
                cmds.disconnectAttr(src, dst)
            except RuntimeError:
                pass


def _get_place2d(material_uuid, base):
    found = _owned(material_uuid, "place2d")
    if found:
        return found[0]
    p2d = cmds.shadingNode("place2dTexture", asUtility=True, name=base + "_place2d")
    _set_tag(p2d, "owner", material_uuid)
    _set_tag(p2d, "kind", "place2d")
    return p2d


def _get_file_node(material_uuid, base, role, p2d):
    for f in _owned(material_uuid, "file"):
        if _get_tag(f, "role") == role:
            return f
    f = cmds.shadingNode("file", asTexture=True, isColorManaged=True,
                         name="%s_%s_file" % (base, role))
    _set_tag(f, "owner", material_uuid)
    _set_tag(f, "kind", "file")
    _set_tag(f, "role", role)
    for a, b in _P2D_ATTRS:
        cmds.connectAttr(p2d + "." + a, f + "." + b, force=True)
    return f


def _helper(material_uuid, node_type, name, as_="utility"):
    if as_ == "shader":
        n = cmds.shadingNode(node_type, asShader=True, name=name)
    else:
        n = cmds.shadingNode(node_type, asUtility=True, name=name)
    _set_tag(n, "owner", material_uuid)
    _set_tag(n, "kind", "helper")
    return n


def _setup_file(fnode, tfile, role, is_udim, flip_green):
    cmds.setAttr(fnode + ".ignoreColorSpaceFileRules", 1)
    cs = _pick_colorspace("srgb" if role in COLOR_ROLES else "raw")
    if cs:
        cmds.setAttr(fnode + ".colorSpace", cs, type="string")
    cmds.setAttr(fnode + ".uvTilingMode", 3 if is_udim and tfile.udim is not None else 0)
    cmds.setAttr(fnode + ".fileTextureName", _texture_path(tfile.path), type="string")
    cmds.setAttr(fnode + ".alphaIsLuminance", 0 if role in COLOR_ROLES or role == "orm" else 1)
    # DirectX normal maps have green upside down compared to Maya: G' = 1 - G.
    if flip_green:
        cmds.setAttr(fnode + ".colorGain", 1, -1, 1, type="double3")
        cmds.setAttr(fnode + ".colorOffset", 0, 1, 0, type="double3")
    else:
        cmds.setAttr(fnode + ".colorGain", 1, 1, 1, type="double3")
        cmds.setAttr(fnode + ".colorOffset", 0, 0, 0, type="double3")
    if is_udim and tfile.udim is not None:
        try:
            cmds.ogs(regenerateUVTilePreview=fnode)
        except Exception:
            pass


def _connect_value(src_node, src_channel, shader, attr):
    """Plug a greyscale value into a float attribute, or a color into a float3 one."""
    if _is_compound3(shader, attr):
        cmds.connectAttr(src_node + ".outColor", shader + "." + attr, force=True)
    else:
        cmds.connectAttr(src_node + "." + src_channel, shader + "." + attr, force=True)


def wire_material(shader, sg, job, tset, opts, meshes, log):
    prof = SHADERS[cmds.nodeType(shader)]
    muuid = _uuid(shader)
    base = shader[:-4] if shader.endswith("_MTL") else shader
    _clear_network(muuid, shader, sg)
    p2d = _get_place2d(muuid, base)

    maps = dict(tset.maps)
    flip = False
    if "normalDX" in maps:
        maps["normal"] = maps.pop("normalDX")
        flip = opts.normal_mode != "opengl"
    elif "normal" in maps:
        flip = opts.normal_mode == "directx"
    if "ao" in maps:
        log.info("  Skipped AO map (shaders here don't use AO; it's baked for game engines)")
        maps.pop("ao")
    if opts.height_mode == "ignore" and "height" in maps:
        log.info("  Skipped Height map (Height map setting is 'Ignore')")
        maps.pop("height")

    # Remove file nodes for maps that no longer exist in the folder.
    for f in _owned(muuid, "file"):
        if _get_tag(f, "role") not in maps:
            cmds.delete(f)

    files = {}
    for role, tfile in maps.items():
        f = _get_file_node(muuid, base, role, p2d)
        _setup_file(f, tfile, role, tset.is_udim, flip and role == "normal")
        files[role] = f

    def slot(key):
        attr = prof.get(key)
        if attr and cmds.attributeQuery(attr, node=shader, exists=True):
            return attr
        return None

    def skipped(role):
        log.info("  Skipped %s map (%s has no slot for it)"
                 % (textures.ROLE_LABELS.get(role, role), cmds.nodeType(shader)))

    if "baseColor" in files:
        if slot("baseColor"):
            cmds.connectAttr(files["baseColor"] + ".outColor", shader + "." + slot("baseColor"),
                             force=True)
            w = prof.get("base_weight")
            if w:
                _set_if_exists(shader, w[0], w[1])
        else:
            skipped("baseColor")

    if "orm" in files:
        # Packed Unreal-style map: R = AO, G = roughness, B = metalness.
        if slot("roughness"):
            cmds.connectAttr(files["orm"] + ".outColorG", shader + "." + slot("roughness"), force=True)
        if slot("metalness"):
            cmds.connectAttr(files["orm"] + ".outColorB", shader + "." + slot("metalness"), force=True)

    if "metalness" in files:
        if slot("metalness"):
            _connect_value(files["metalness"], "outAlpha", shader, slot("metalness"))
        else:
            skipped("metalness")

    if "roughness" in files:
        if slot("roughness"):
            _connect_value(files["roughness"], "outAlpha", shader, slot("roughness"))
        else:
            skipped("roughness")
    elif "glossiness" in files:
        if slot("roughness"):
            rev = _helper(muuid, "reverse", base + "_gloss_to_rough")
            cmds.connectAttr(files["glossiness"] + ".outAlpha", rev + ".inputX", force=True)
            cmds.connectAttr(rev + ".outputX", shader + "." + slot("roughness"), force=True)
        else:
            skipped("glossiness")

    if "emissive" in files:
        if slot("emissive"):
            cmds.connectAttr(files["emissive"] + ".outColor", shader + "." + slot("emissive"),
                             force=True)
            w = prof.get("emissive_weight")
            if w and cmds.attributeQuery(w[0], node=shader, exists=True) \
                    and not cmds.getAttr(shader + "." + w[0]):
                cmds.setAttr(shader + "." + w[0], w[1])
                log.info("  Emission turned on (%s = %g), adjust to taste" % (w[0], w[1]))
        else:
            skipped("emissive")

    if "opacity" in files:
        if slot("opacity"):
            _connect_value(files["opacity"], "outAlpha", shader, slot("opacity"))
            for m in meshes:
                for shape in cmds.listRelatives(m, shapes=True, noIntermediate=True,
                                                fullPath=True) or []:
                    _set_if_exists(shape, "aiOpaque", 0)
        else:
            skipped("opacity")

    # Normal + height (bump) share the shader's normal input, so build them as a chain.
    normal_out = None
    if "normal" in files:
        nb = _helper(muuid, "bump2d", base + "_normal_bump")
        cmds.setAttr(nb + ".bumpInterp", 1)       # 1 = tangent space normals
        cmds.connectAttr(files["normal"] + ".outAlpha", nb + ".bumpValue", force=True)
        normal_out = nb + ".outNormal"
        if flip:
            log.info("  Normal map treated as DirectX (green channel flipped)")

    if "height" in files and opts.height_mode == "bump":
        hb = _helper(muuid, "bump2d", base + "_height_bump")
        cmds.setAttr(hb + ".bumpInterp", 0)       # 0 = bump
        cmds.setAttr(hb + ".bumpDepth", opts.height_strength)
        cmds.connectAttr(files["height"] + ".outAlpha", hb + ".bumpValue", force=True)
        if normal_out:
            cmds.connectAttr(normal_out, hb + ".normalCamera", force=True)
        normal_out = hb + ".outNormal"

    if normal_out:
        if slot("normal"):
            cmds.connectAttr(normal_out, shader + "." + slot("normal"), force=True)
        else:
            skipped("normal")

    if "height" in files and opts.height_mode == "displacement":
        disp = _helper(muuid, "displacementShader", base + "_displacement", as_="shader")
        cmds.connectAttr(files["height"] + ".outAlpha", disp + ".displacement", force=True)
        cmds.setAttr(disp + ".scale", opts.height_strength)
        _set_if_exists(disp, "aiDisplacementZeroValue", 0.5)   # Substance height: mid-grey = flat
        cmds.connectAttr(disp + ".displacement", sg + ".displacementShader", force=True)
        for m in meshes:
            for shape in cmds.listRelatives(m, shapes=True, noIntermediate=True, fullPath=True) or []:
                if cmds.attributeQuery("aiSubdivType", node=shape, exists=True) \
                        and cmds.getAttr(shape + ".aiSubdivType") == 0:
                    cmds.setAttr(shape + ".aiSubdivType", 1)          # catclark
                    cmds.setAttr(shape + ".aiSubdivIterations", 2)
                    log.info("  Turned on Arnold subdivision (2 levels) on %s for displacement"
                             % shape.split("|")[-1])

    log.info("  Maps: %s%s" % (", ".join(textures.ROLE_LABELS.get(r, r) for r in sorted(files)),
                              "  [UDIM]" if tset.is_udim else ""))
    for f in tset.ignored:
        log.info("  Didn't recognise %s (left out)" % os.path.basename(f.path))


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------
def _shapes(mesh):
    return cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True) or []


def _sgs_on(shape):
    return list(dict.fromkeys(cmds.listConnections(shape, type="shadingEngine") or []))


def _members_on(sg, shape):
    """Members of a shading group that belong to this shape (faces or the whole object)."""
    out = []
    transform = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
    for m in cmds.ls(cmds.sets(sg, q=True) or [], long=True) or []:
        node = m.split(".")[0]
        if node in (shape, transform):
            out.append(m)
    return out


def assign(job, results, log):
    """results: list of (texture_set, shader, sg). Puts each material on the right faces."""
    multi = len(results) > 1
    for mesh in job.meshes:
        name = mesh.split("|")[-1]
        for shape in _shapes(mesh):
            current = _sgs_on(shape)
            pending = []
            for tset, shader, sg in results:
                if sg in current:
                    continue                      # already on there from a previous run
                pending.append((tset, shader, sg))
            if not pending:
                log.info("  %s already uses its material(s), kept as is" % name)
                continue
            if not multi:
                tset, shader, sg = pending[0]
                cmds.sets(mesh, edit=True, forceElement=sg)
                log.info("  Assigned %s to %s" % (shader, name))
                continue
            # Several texture sets: find which faces each one belongs to, using the
            # materials already on the mesh (Substance names texture sets after them).
            assigned_any = len(pending) < len(results)
            unmatched = []
            for tset, shader, sg in pending:
                target = None
                for old_sg in current:
                    old_shader = (cmds.listConnections(old_sg + ".surfaceShader") or [""])[0]
                    if matching.set_matches_material(tset.name, old_shader) or \
                            matching.set_matches_material(tset.name, old_sg):
                        target = old_sg
                        break
                if target:
                    members = _members_on(target, shape)
                    if members:
                        cmds.sets(members, edit=True, forceElement=sg)
                        log.info("  Assigned %s to %s (faces that used %s)"
                                 % (shader, name, target))
                        assigned_any = True
                        continue
                unmatched.append((tset, shader, sg))
            if not assigned_any and unmatched:
                tset, shader, sg = unmatched.pop(0)
                cmds.sets(mesh, edit=True, forceElement=sg)
                log.warn("%s has %d texture sets but none matched its current materials. "
                         "Put %s on the whole object; assign the others by hand."
                         % (name, len(results), shader))
            for tset, shader, sg in unmatched:
                log.warn("Couldn't tell which faces of %s use texture set '%s'. %s was "
                         "created but not assigned." % (name, tset.name, shader))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run(root, opts, selected_only=True):
    """Bridge textures. Returns a Log."""
    log = Log()
    ensure_plugin(opts.shader)
    if selected_only:
        nodes = selected_nodes()
        if not nodes:
            raise RuntimeError("Nothing is selected. Select the object(s) to bridge, "
                               "or use Bridge All.")
    else:
        nodes = None
    jobs, unmatched = plan(root, nodes)
    if not jobs:
        raise RuntimeError("None of the %s objects have a matching texture folder in\n%s\n\n"
                           "Each object needs a folder named after it (e.g. a 'Ball' folder "
                           "for an object called 'Ball')."
                           % ("selected" if selected_only else "scene", root))

    selection = cmds.ls(selection=True, long=True) or []
    cmds.undoInfo(openChunk=True, chunkName="MacsAutoBridge")
    try:
        for job in jobs:
            log.info("%s  <-  %s (%s)" % (", ".join(m.split("|")[-1] for m in job.meshes),
                                         job.folder, matching.TIER_NOTES.get(job.tier, "")))
            results = []
            for tset in job.sets:
                shader, sg, _new = get_or_create_material(job, tset, opts, log)
                wire_material(shader, sg, job, tset, opts, job.meshes, log)
                results.append((tset, shader, sg))
            assign(job, results, log)
        for m in unmatched:
            log.info("No texture folder for %s (skipped)" % m.split("|")[-1])
        still_there = [n for n in selection if cmds.objExists(n)]
        if still_there:
            cmds.select(still_there, replace=True)
        else:
            cmds.select(clear=True)
    finally:
        cmds.undoInfo(closeChunk=True)
    return log
