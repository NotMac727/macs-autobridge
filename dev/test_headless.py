"""Headless test. Run with:  mayapy dev/test_headless.py
Opens the AutoBridge test scene (never saves over it) and exercises the tool."""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "MacsAutoBridge", "scripts"))

import maya.standalone
maya.standalone.initialize()
import maya.cmds as cmds

from macs_autobridge import builder

PROJECT = os.path.normpath(os.path.join(HERE, "..", "..", "AutoBridgeTestBall")).replace("\\", "/")
SCENE = PROJECT + "/scenes/AutobridgeTestScene.ma"
ROOT = PROJECT + "/sourceimages/Materials_textures"

fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def src(plug):
    c = cmds.listConnections(plug, source=True, destination=False, plugs=True) or []
    return c[0] if c else None


def sg_of(obj):
    shape = cmds.listRelatives(obj, shapes=True, fullPath=True)[0]
    return sorted(set(cmds.listConnections(shape, type="shadingEngine") or []) - {"initialShadingGroup"})


cmds.loadPlugin("mtoa", quiet=True)
cmds.workspace(PROJECT, openWorkspace=True)
cmds.file(SCENE, open=True, force=True)

print("\n== 1. aiStandardSurface, Bridge Selected ==")
cmds.select("AutoBridgeTestBall")
log = builder.run(ROOT, builder.Options("aiStandardSurface"), selected_only=True)
print(log.text())
m = "AutoBridgeTestBall_openPBR_shader1_MTL"
check(cmds.objExists(m) and cmds.nodeType(m) == "aiStandardSurface", "material created")
check(sg_of("AutoBridgeTestBall") == [m.replace("_MTL", "_SG")], "assigned to ball")
bc = src(m + ".baseColor")
check(bc and bc.endswith(".outColor"), "baseColor wired: %s" % bc)
f = bc.split(".")[0]
check(cmds.getAttr(f + ".uvTilingMode") == 3, "UDIM mode on")
check(cmds.getAttr(f + ".colorSpace") == "sRGB", "base color sRGB")
print("    path:", cmds.getAttr(f + ".fileTextureName"))
check(src(m + ".metalness").endswith("outAlpha"), "metalness wired")
rf = src(m + ".specularRoughness").split(".")[0]
check(cmds.getAttr(rf + ".colorSpace") == "Raw" and cmds.getAttr(rf + ".alphaIsLuminance"), "roughness raw + alphaIsLum")
n = src(m + ".normalCamera")
check(n and cmds.nodeType(n.split(".")[0]) == "bump2d", "height bump on normalCamera")
nb = src(n.split(".")[0] + ".normalCamera")
check(nb and cmds.getAttr(nb.split(".")[0] + ".bumpInterp") == 1, "normal map chained under bump")
n_files = len(cmds.ls(type="file"))
n_ai = len(cmds.ls(type="aiStandardSurface"))
n_bump = len(cmds.ls(type="bump2d"))

print("\n== 2. re-run (should update, not duplicate) ==")
log = builder.run(ROOT, builder.Options("aiStandardSurface"), selected_only=True)
print(log.text())
check(len(cmds.ls(type="aiStandardSurface")) == n_ai, "no duplicate aiStandardSurface")
check(len(cmds.ls(type="file")) == n_files, "no duplicate file nodes")
check(len(cmds.ls(type="bump2d")) == n_bump, "no duplicate bump nodes")

print("\n== 3. switch to openPBR + displacement ==")
log = builder.run(ROOT, builder.Options("openPBRSurface", "displacement", 0.2), selected_only=True)
print(log.text())
check(cmds.nodeType(m) == "openPBRSurface", "shader swapped, same name")
check(sg_of("AutoBridgeTestBall") == [m.replace("_MTL", "_SG")], "same SG still assigned")
check(src(m + ".baseMetalness") is not None, "baseMetalness wired")
check(len(cmds.ls(type="file")) == n_files, "file nodes reused")
d = src(m.replace("_MTL", "_SG") + ".displacementShader")
check(d is not None, "displacement connected to SG")
check(cmds.getAttr("AutoBridgeTestBallShape.aiSubdivType") == 1, "arnold subdiv turned on")
check(len(cmds.ls(type="bump2d")) == n_bump - 1, "only the normal bump remains")

print("\n== 4. aiToon + standardSurface ==")
log = builder.run(ROOT, builder.Options("aiToon", "bump"), selected_only=True)
print(log.text())
check(cmds.nodeType(m) == "aiToon", "aiToon")
check(len(cmds.ls(cmds.ls(type="displacementShader"))) == 0, "displacement removed in bump mode")
log = builder.run(ROOT, builder.Options("standardSurface"), selected_only=False)
check(cmds.nodeType(m) == "standardSurface", "standardSurface via Bridge All")

print("\n== 5. fuzzy names, groups, multi texture sets, loose files ==")
tmp = tempfile.mkdtemp(prefix="macsab_")
tex = ROOT + "/AutoBridgeTestBall"
def fake(folder, names):
    os.makedirs(folder, exist_ok=True)
    for nm in names:
        shutil.copy(tex + "/AutoBridgeTestBall_openPBR_shader1_BaseColor.1001.png", os.path.join(folder, nm))
fake(tmp + "/Crate", ["Crate_Wood_Base_Color.png", "Crate_Wood_Roughness.png", "Crate_Metal_BaseColor.png",
                     "Crate_Metal_Metallic.png", "Crate_Metal_Normal_DirectX.png", "preview.png"])
fake(tmp + "/robot_geo", ["Robot_Body_BaseColor.png", "Robot_Body_Normal_OpenGL.png"])
fake(tmp, ["Lamp_Glass_BaseColor.png", "Lamp_Glass_Opacity.png"])
cmds.file(new=True, force=True)
crate = cmds.polyCube(name="crate1")[0]
wood = cmds.shadingNode("lambert", asShader=True, name="Wood")
wsg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="WoodSG")
cmds.connectAttr(wood + ".outColor", wsg + ".surfaceShader")
metal = cmds.shadingNode("lambert", asShader=True, name="metal_mat")
msg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="metal_matSG")
cmds.connectAttr(metal + ".outColor", msg + ".surfaceShader")
cmds.sets(crate + ".f[0:2]", e=True, forceElement=wsg)
cmds.sets(crate + ".f[3:5]", e=True, forceElement=msg)
a = cmds.polySphere(name="pSphere1")[0]
b = cmds.polySphere(name="pSphere2")[0]
cmds.namespace(add="char")
grp = cmds.group(a, b, name="char:Robot_GRP")
lamp = cmds.polyCylinder(name="Lamp")[0]
cmds.polyCone(name="noTextures")
log = builder.run(tmp, builder.Options("aiStandardSurface"), selected_only=False)
print(log.text())
check(not [m for m in cmds.sets("initialShadingGroup", q=True) or [] if "crate" in m], "crate no longer in initialShadingGroup")
check(set(sg_of(crate)) == {"Crate_Wood_SG", "Crate_Metal_SG"}, "crate faces split by texture set: %s" % sg_of(crate))
check(set(cmds.ls(cmds.sets("Crate_Wood_SG", q=True), flatten=True)) == {"crate1.f[0]", "crate1.f[1]", "crate1.f[2]"}, "wood on the right faces")
nf = src("Crate_Metal_normal_bump.bumpValue").split(".")[0]
check(cmds.getAttr(nf + ".colorGain")[0][1] == -1, "DirectX normal flipped")
check(sg_of("pSphere1") == ["robot_Body_SG"] and sg_of("pSphere2") == ["robot_Body_SG"], "group folder applied to children (named after folder robot_geo -> robot)")
check(sg_of("Lamp") == ["Lamp_Glass_SG"], "loose files matched")
check(cmds.getAttr("LampShape.aiOpaque") == 0, "opacity -> aiOpaque off")
cmds.undo()
check(not cmds.objExists("Crate_Wood_MTL"), "single undo removes everything")

shutil.rmtree(tmp, ignore_errors=True)
print("\nRESULT: %s" % ("ALL PASSED" if not fails else "%d FAILED" % len(fails)))
os._exit(0 if not fails else 1)
