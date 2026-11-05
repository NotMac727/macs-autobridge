"""Build the shelf/window icons from Mac's MDVFX logo (DIGI 130).
Run with:  mayapy dev/make_icons.py"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtGui, QtCore
app = QtGui.QGuiApplication([])

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "logo_source", "mascot_sparkle.png")
OUT = os.path.join(HERE, "..", "MacsAutoBridge", "icons")
TEAL, YELLOW, ORANGE, RED = "#0e6873", "#f3c051", "#fe7e3c", "#e4201b"   # sampled from the logo

mascot = QtGui.QImage(SRC).copy(585, 590, 390, 465)    # mascot + sparkle + glow, cropped

def master(M=256):
    s = M / 64.0
    img = QtGui.QImage(M, M, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing); p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    # dark rounded tile
    p.setPen(QtGui.QPen(QtGui.QColor("#3a3a3a"), 1.2 * s))
    p.setBrush(QtGui.QColor("#1b1b1b"))
    p.drawRoundedRect(QtCore.QRectF(1 * s, 1 * s, 62 * s, 62 * s), 10 * s, 10 * s)
    # racing stripes (slanted like the MDVFX logo; red is the widest)
    p.setPen(QtCore.Qt.NoPen)
    top, bot, slant = 9.0, 55.0, 15.0
    x = 4.0
    for color, w in ((TEAL, 3.2), (YELLOW, 5.2), (ORANGE, 6.6), (RED, 10.0)):
        poly = QtGui.QPolygonF([QtCore.QPointF((x + slant) * s, top * s), QtCore.QPointF((x + slant + w) * s, top * s),
                                QtCore.QPointF((x + w) * s, bot * s), QtCore.QPointF(x * s, bot * s)])
        p.setBrush(QtGui.QColor(color)); p.drawPolygon(poly)
        x += w + 1.6
    # mascot with sparkle, in front on the right
    h = 50.0 * s
    w = h * mascot.width() / mascot.height()
    p.drawImage(QtCore.QRectF(64 * s - w - 2 * s, 8 * s, w, h), mascot)
    p.end()
    return img

big = master(256)
for size, name in ((32, "macsAutoBridge.png"), (48, "macsAutoBridge_150.png"), (64, "macsAutoBridge_200.png"),
                   (256, "macsAutoBridge_256.png")):
    big.scaled(size, size, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation).save(os.path.join(OUT, name))
print("icons written to", os.path.normpath(OUT))
sys.stdout.flush(); os._exit(0)
