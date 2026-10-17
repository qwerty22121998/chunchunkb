#!/usr/bin/env python3
"""Generate the chunchunkb reversible footprints (CC_*) into chunchun_rev.pretty/.

Every reversible pin is one pad number on both copper layers: front pad, back pad,
and a tented via, joined inside the footprint by copper strips: round-ended SMD pads
with no mask that run at 0/45/90 degrees, so they look and behave like tracks.
Silkscreen: straight lines only (0/45/90 degrees, square corners, no arcs), 0.25 mm wide,
boxes hug the pads (never the vias or strips), pin 1 is a filled triangle pointing at
the pad, text is the KiCad font at 1.0 mm with a 0.2 mm pen.
Re-run after changing a dimension:  python3 tools/gen_footprints.py
"""
import math
import re
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "chunchun_rev.pretty"
VIA, VIA_DRILL, STRIP = 0.6, 0.3, 0.3  # via pad, via drill, copper strip width (mm)
SILK_W, SILK_GAP = 0.25, 0.2  # silk line width, copper edge to silk line edge (JLCPCB min 0.15)
TEXT, PEN = 1.0, 0.2  # silk text height and stroke

SIDES = {"F": ("F.Cu", "F.Mask", "F.Paste"), "B": ("B.Cu", "B.Mask", "B.Paste")}


def n(v):
    return f"{round(v, 4):g}"


class Fp:
    def __init__(self, name, descr, attr):
        self.name, self.descr, self.attr = name, descr, attr
        self.items, self.models = [], []

    # --- copper
    def smd(self, num, x, y, w, h, side, shape="rect", copper_only=False):
        layers = (SIDES[side][0],) if copper_only else SIDES[side]
        self.items.append(f'(pad "{num}" smd {shape} (at {n(x)} {n(y)}) (size {n(w)} {n(h)}) '
                          f'(layers {" ".join(chr(34) + l + chr(34) for l in layers)}))')

    def tht(self, num, x, y, size, drill, shape="circle", sy=None, dy=None):
        sy = size if sy is None else sy
        dr = f"(drill {n(drill)})" if dy is None else f"(drill oval {n(drill)} {n(dy)})"
        self.items.append(f'(pad "{num}" thru_hole {shape} (at {n(x)} {n(y)}) (size {n(size)} {n(sy)}) {dr} '
                          f'(layers "*.Cu" "*.Mask"))')

    def npth(self, x, y, d, dy=None):
        shape, dr = ("circle", f"(drill {n(d)})") if dy is None else ("oval", f"(drill oval {n(d)} {n(dy)})")
        self.items.append(f'(pad "" np_thru_hole {shape} (at {n(x)} {n(y)}) (size {n(d)} {n(dy or d)}) {dr} '
                          f'(layers "*.Cu" "*.Mask"))')

    def via(self, num, x, y):
        self.items.append(f'(pad "{num}" thru_hole circle (at {n(x)} {n(y)}) (size {VIA} {VIA}) (drill {VIA_DRILL}) '
                          f'(layers "*.Cu"))')

    def strip(self, num, side, *pts):
        """Copper path on one layer, joined to the pads it touches by pad number. Each segment is a
        round-ended (oval) pad like a track; bends are 45 degrees."""
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            ang = math.degrees(math.atan2(y1 - y2, x2 - x1))  # KiCad angles are CCW on screen, y down
            assert abs(ang / 45 - round(ang / 45)) < 1e-6, f"strip segment at {ang} deg, want 0/45/90"
            length = math.hypot(x2 - x1, y2 - y1) + STRIP
            self.items.append(f'(pad "{num}" smd oval (at {n((x1 + x2) / 2)} {n((y1 + y2) / 2)} {n(ang)}) '
                              f'(size {n(length)} {STRIP}) (layers "{SIDES[side][0]}"))')

    # --- graphics (w=None: SILK_W on silkscreen, 0.15 elsewhere)
    def line(self, layer, x1, y1, x2, y2, w=None):
        w = w or (SILK_W if layer.endswith("SilkS") else 0.15)
        self.items.append(f'(fp_line (start {n(x1)} {n(y1)}) (end {n(x2)} {n(y2)}) '
                          f'(stroke (width {n(w)}) (type solid)) (layer "{layer}"))')

    def poly(self, layer, pts, w=None):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            self.line(layer, x1, y1, x2, y2, w)

    def rect(self, layer, x1, y1, x2, y2, w=None):
        w = w or (SILK_W if layer.endswith("SilkS") else 0.15)
        self.items.append(f'(fp_rect (start {n(x1)} {n(y1)}) (end {n(x2)} {n(y2)}) '
                          f'(stroke (width {n(w)}) (type solid)) (fill no) (layer "{layer}"))')

    def both_rect(self, kind, x1, y1, x2, y2, w=None):
        for s in "FB":
            self.rect(f"{s}.{kind}", x1, y1, x2, y2, w)

    def pad_box(self, x1, y1, x2, y2):
        """Silk box on both sides around the copper extents x1..x2, y1..y2 (pads only, not vias)."""
        g = SILK_GAP + SILK_W / 2
        self.both_rect("SilkS", x1 - g, y1 - g, x2 + g, y2 + g)

    def pin1(self, side, x, y, dx, dy):
        """Filled pin-1 triangle on one side's silk: tip at (x, y), pointing along (dx, dy)."""
        pts = [(x, y), (x - 0.7 * dx - 0.45 * dy, y - 0.7 * dy + 0.45 * dx), (x - 0.7 * dx + 0.45 * dy, y - 0.7 * dy - 0.45 * dx)]
        self.items.append(f'(fp_poly (pts {" ".join(f"(xy {n(px)} {n(py)})" for px, py in pts)}) '
                          f'(stroke (width 0) (type solid)) (fill yes) (layer "{side}.SilkS"))')

    def text(self, layer, s, x, y, size=TEXT):
        mirror = " (justify mirror)" if layer.startswith("B.") else ""
        self.items.append(f'(fp_text user "{s}" (at {n(x)} {n(y)}) (layer "{layer}") '
                          f'(effects (font (size {n(size)} {n(size)}) (thickness {n(PEN * size / TEXT)})){mirror}))')

    def model(self, path, offset=(0, 0, 0), rotate=(0, 0, 0)):
        self.models.append(f'(model "{path}" (offset (xyz {" ".join(n(v) for v in offset)})) '
                           f'(scale (xyz 1 1 1)) (rotate (xyz {" ".join(n(v) for v in rotate)})))')

    def write(self, ref_y=-9.5, val_y=9.5):
        head = [f'(footprint "{self.name}"', '(version 20241229)', '(generator "chunchunkb_gen")', '(layer "F.Cu")',
                f'(descr "{self.descr}")',
                f'(property "Reference" "REF**" (at 0 {n(ref_y)} 0) (layer "F.SilkS") (effects (font (size {n(TEXT)} {n(TEXT)}) (thickness {n(PEN)}))))',
                f'(property "Value" "{self.name}" (at 0 {n(val_y)} 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
                f'(attr {self.attr})']
        body = "\n\t".join(head + self.items + self.models)
        LIB.mkdir(exist_ok=True)
        (LIB / f"{self.name}.kicad_mod").write_text(f"{body}\n)\n")
        return self.name


# ---------------------------------------------------------------- MX hotswap
def socket_silk(fp, top=-6.9, wrap_low_pad=True):
    """Outline of the Kailh socket on each side's silkscreen, so it's obvious which pads take the
    socket on that side. Square corners, kept >= 0.15 mm off pads and holes; open at the bottom
    where the switch-pin holes and centre post leave no room. The socket body sits over the vias,
    so this is the one outline that encloses them."""
    pts = [(-5.6, -4.4), (-5.6, top), (7.15, top), (7.15, -3.3), (5.55, -3.3)]
    if wrap_low_pad:  # also box in the lower pad on the left
        pts = [(-5.6, -1.15), (-8.55, -1.15), (-8.55, -4.4)] + pts
    fp.poly("B.SilkS", pts)  # back socket: pads at upper right + lower left
    fp.poly("F.SilkS", [(-x, y) for x, y in pts])  # front socket is the mirror image


def mx_hotswap(fp, pin_l="2", pin_r="1", pegs=True, silk_top=-6.9, wrap_low_pad=True):
    """Kailh MX hotswap, socket usable on either side. Switch pins point to -y (rotate the
    footprint 180 deg on the board for north-facing LEDs). pin_r: right pads, pin_l: left pads."""
    fp.npth(0, 0, 4.1)  # switch centre post
    if pegs:
        for x in (-5.08, 5.08):
            fp.npth(x, 0, 1.75)  # 5-pin PCB-mount pegs
    for x, y in ((-3.81, -2.54), (2.54, -5.08), (3.81, -2.54), (-2.54, -5.08)):
        fp.npth(x, y, 3.0)  # switch pins into the socket sleeves (both orientations)
    for sx, num in ((1, pin_r), (-1, pin_l)):
        # same pin: lower pad on one side, upper pad on the other; via between them
        lo_side, hi_side = ("F", "B") if sx > 0 else ("B", "F")
        fp.smd(num, sx * 7.0, -2.58, 2.3, 2.0, lo_side)
        fp.smd(num, sx * 5.7, -5.12, 2.3, 2.0, hi_side)
        vx, vy = sx * 6.35, -3.85
        fp.via(num, vx, vy)
        fp.strip(num, lo_side, (vx, -3.0), (vx, vy))
        fp.strip(num, hi_side, (vx, -4.7), (vx, vy))
    socket_silk(fp, silk_top, wrap_low_pad)
    fp.both_rect("Fab", -7, -7, 7, 7, 0.1)  # switch body


def mx_models(fp):
    fp.model("${KIPRJMOD}/3dmodels/kbd.kailh_hotswap_socket.step", (-1.25, 7.6, -3.5), (0, 0, -180))
    fp.model("${KIPRJMOD}/3dmodels/asm_mx_asm_PCB.stp", (0.3, 0.3, 5.5), (0, 180, -90))


def gen_mx(u):
    name = f"CC_MX_Hotswap_{u}u"
    fp = Fp(name, f"Reversible Kailh MX hotswap, {u}u keycap outline on User.1. Pin 1/2 front+back joined by vias.", "smd")
    mx_hotswap(fp)
    w = 18 + (u - 1) * 19.05
    fp.rect("User.1", -w / 2, -9, w / 2, 9, 0.1)
    mx_models(fp)
    return fp.write()


# ---------------------------------------------------------------- EC11 + MX hybrid
def gen_ec11():
    fp = Fp("CC_EC11_MX_1u", "EC11 rotary encoder or reversible Kailh MX hotswap in one 1u spot. "
            "Encoder push switch shares S1/S2 with the MX pins.", "through_hole")
    # socket outline goes above the encoder pins and skips the lower pads, where the S1/S2 links run
    mx_hotswap(fp, pin_l="S1", pin_r="S2", pegs=False, silk_top=-8.85, wrap_low_pad=False)
    # EC11 rotary pins: A/B sit 2.4 mm from the MX pin holes, so their pads stay small
    fp.tht("A", 2.5, -7.5, 1.35, 1.0)
    fp.tht("C", 0, -7.5, 2.0, 1.0)
    fp.tht("B", -2.5, -7.5, 1.35, 1.0)
    fp.tht("S1", -2.5, 7.0, 2.0, 1.0)
    fp.tht("S2", 2.5, 7.0, 2.0, 1.0)
    for x in (-5.3, 5.3):
        fp.npth(x, 0, 2.2, 2.6)  # EC11 mounting lug slot, also takes an MX PCB-mount peg
    fp.strip("S2", "F", (2.5, 7.0), (7.0, 7.0), (7.6, 6.4), (7.6, -1.8))  # to the front lower S2 pad
    fp.strip("S1", "B", (-2.5, 7.0), (-7.0, 7.0), (-7.6, 6.4), (-7.6, -1.8))  # to the back lower S1 pad
    fp.both_rect("Fab", -6.1, -6.6, 6.1, 6.6, 0.1)  # EC11 body
    fp.rect("User.1", -9, -9, 9, 9, 0.1)
    mx_models(fp)
    fp.model("${KIPRJMOD}/3dmodels/EC11 Rotary Encoder Dode Switch-15mm .STEP", rotate=(0, 0, -180))
    return fp.write(ref_y=-10.1)  # clear of the socket outline at y=-8.85


# ---------------------------------------------------------------- SK6812MINI-E reverse mount
def gen_led():
    fp = Fp("CC_SK6812MINI-E", "Reversible SK6812MINI-E, reverse mount through a board cutout. "
            "1 VDD, 2 DOUT, 3 GND, 4 DIN; front/back pads joined by vias.", "smd")
    # square-cornered 3.6 x 3.1 cutout: big enough that the mill's corner radius still clears the
    # 3.2 x 2.8 body; pads (KiCad stock size/pitch) start 0.3 mm from it (JLCPCB copper-to-edge).
    # pin map from YS-SK6812MINI-E: the back side is the front mirrored top/bottom
    cx, cy, px, py = 1.8, 1.55, 2.775, 0.75
    for side, rows in (("F", {1: (px, -py), 2: (px, py), 3: (-px, py), 4: (-px, -py)}),
                       ("B", {1: (px, py), 2: (px, -py), 3: (-px, -py), 4: (-px, py)})):
        for num, (x, y) in rows.items():
            fp.smd(num, x, y, 1.35, 0.82, side)
    for sx, top, bot in ((1, "1", "2"), (-1, "4", "3")):
        # front: top pad -> near via, bottom pad -> far via, both straight out.
        # back has the pins swapped: its bottom pad climbs to the near via at 45 degrees and its
        # top pad loops over the near via to the far one.
        near, far = (sx * 4.0, -py), (sx * 5.2, py)
        fp.via(top, *near)
        fp.via(bot, *far)
        fp.strip(top, "F", (sx * 3.3, -py), near)
        fp.strip(bot, "F", (sx * 3.3, py), far)
        fp.strip(top, "B", (sx * 3.25, py), (sx * 4.0, 0), near)
        fp.strip(bot, "B", (sx * px, -1.0), (sx * px, -1.35), (sx * (px + 0.35), -1.7),
                 (sx * 4.85, -1.7), (sx * 5.2, -1.35), far)
    fp.poly("Edge.Cuts", [(-cx, -cy), (cx, -cy), (cx, cy), (-cx, cy), (-cx, -cy)], 0.1)
    fp.both_rect("CrtYd", -1.65, -1.45, 1.65, 1.45, 0.05)
    fp.pin1("F", px, -py - 0.41 - 0.35, 0, 1)  # above front pad 1, pointing down at it
    fp.pin1("B", px, py + 0.41 + 0.35, 0, -1)  # below back pad 1, pointing up at it
    fp.model("${KICAD10_3DMODEL_DIR}/LED_SMD.3dshapes/LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount.step", (0, 0, -1.6), (-180, 0, 0))
    return fp.write(ref_y=-3, val_y=3)


# ---------------------------------------------------------------- diode
def gen_diode():
    fp = Fp("CC_D_SOD-123", "Reversible SOD-123 diode (1N4148W). 1 = cathode. Pads on both sides joined by vias.", "smd")
    for num, x in (("1", -1.775), ("2", 1.775)):
        for s in "FB":
            fp.smd(num, x, 0, 1.3, 0.95, s)
            fp.strip(num, s, (x, -0.3), (x, -1.25))
        fp.via(num, x, -1.25)
    fp.pad_box(-2.425, -0.475, 2.425, 0.475)
    for s in "FB":
        lay = f"{s}.SilkS"
        fp.line(lay, -0.45, -0.45, -0.45, 0.45)  # cathode bar
        fp.poly(lay, [(-0.35, 0), (0.45, -0.45), (0.45, 0.45), (-0.35, 0)])
        fp.pin1(s, -3.05, 0, 1, 0)  # left of the box, pointing at the cathode
    fp.both_rect("CrtYd", -3.0, -1.75, 3.0, 1.0, 0.05)
    fp.model("${KICAD10_3DMODEL_DIR}/Diode_SMD.3dshapes/D_SOD-123.step", (0, 0, -1.7), (-180, 0, 0))
    return fp.write(ref_y=-2.6, val_y=2)


# ---------------------------------------------------------------- nice!nano
NANO_JUMPERS = {  # hole: (net when the nano sits on the front, net when it sits on the back)
    1: ("P0.06", "BAT"), 2: ("P0.08", "GND"), 3: ("GND", "RST"), 4: ("GND", "VCC"),
    21: ("VCC", "GND"), 22: ("RST", "GND"), 23: ("GND", "P0.08"), 24: ("BAT", "P0.06"),
}


def gen_nano():
    fp = Fp("CC_nice_nano", "Reversible nice!nano. Holes 5-20 wired straight (right half mirrors the GPIOs in firmware). "
            "Holes 1-4 and 21-24 pick their net with a solder jumper on the bottom side: "
            "back-copper jumpers for a nano on the front, front-copper jumpers for a nano on the back.", "through_hole")
    for i in range(12):
        y = -13.97 + 2.54 * i
        for hole, x in ((i + 1, -7.62), (24 - i, 7.62)):
            jumpered = hole in NANO_JUMPERS
            fp.tht(f"H{hole}" if jumpered else hole, x, y, 1.6, 1.1, shape="rect" if hole == 1 else "circle")
            if jumpered:
                f_mount, b_mount = NANO_JUMPERS[hole]
                jx = x + (0.8 + 0.25 + 0.45) * (1 if x < 0 else -1)  # 0.25 mm gap to the hole ring
                fp.smd(f_mount, jx, y, 0.9, 1.2, "B")  # nano on front: bridge on the back
                fp.smd(b_mount, jx, y, 0.9, 1.2, "F")  # nano on back: bridge on the front
                tx = jx + (3.1 if x < 0 else -3.1)  # clears the jumper pad for labels up to 5 chars
                fp.text("B.SilkS", f_mount, tx, y)
                fp.text("F.SilkS", b_mount, tx, y)
    fp.both_rect("SilkS", -8.96, -17.86, 8.96, 15.31)
    fp.both_rect("CrtYd", -9.1, -18.0, 9.1, 15.45, 0.05)
    for s, other in (("F", "B"), ("B", "F")):
        fp.text(f"{s}.SilkS", "USB", 0, -16.6)
        fp.text(f"{s}.SilkS", "BRIDGE IF", 0, -3.2)  # two lines: one line is wider than the hole rows
        fp.text(f"{s}.SilkS", f"NANO ON {other}", 0, -1.8)
    fp.model("${KIPRJMOD}/3dmodels/dip24.step", (-7.6, 14, 0))
    fp.model("${KIPRJMOD}/3dmodels/nice!nano v2.step", (0, 1, 5), (0, 0, 90))
    return fp.write(ref_y=-19, val_y=16.5)


# ---------------------------------------------------------------- nice!view / OLED header
def gen_display():
    fp = Fp("CC_Display_5pin", "Reversible nice!view (pins 1-5) or 128x32 OLED (pins 1-4 front, 2-5 back) header. "
            "Pins 1/5 go to two GPIOs (firmware picks MOSI/SDA vs CS per half); pins 2/4 pick SCK or GND "
            "with a solder jumper on the bottom side. Origin is the display centre.", "through_hole")
    y = 16.7
    for i, x in enumerate((-5.08, -2.54, 0, 2.54, 5.08), 1):
        fp.tht(f"H{i}" if i in (2, 4) else i, x, y, 1.7, 1.0, shape="rect" if i == 1 else "circle")
    for x, f_mount, b_mount in ((-2.54, "SCK", "GND"), (2.54, "GND", "SCK")):
        jy = y + 0.85 + 0.25 + 0.6
        fp.smd(f_mount, x, jy, 1.2, 1.2, "B")
        fp.smd(b_mount, x, jy, 1.2, 1.2, "F")
        fp.text("B.SilkS", f_mount, x, jy + 1.4)
        fp.text("F.SilkS", b_mount, x, jy + 1.4)
    fp.both_rect("Fab", -7.0, -18.0, 7.0, 18.4, 0.1)  # nice!view module
    fp.both_rect("CrtYd", -6.9, 14.8, 6.9, 19.25, 0.05)  # pads only; the SCK/GND labels hang below
    for s in "FB":
        fp.text(f"{s}.SilkS", "VIEW/OLED", 0, y - 1.9)
    fp.model("${KIPRJMOD}/3dmodels/nice!view.step", (0, 0, 12), (0, 0, -90))
    fp.model("${KICAD10_3DMODEL_DIR}/Connector_PinSocket_2.54mm.3dshapes/PinSocket_1x05_P2.54mm_Vertical.step", (-5, -16.5, 0), (0, 0, -90))
    return fp.write(ref_y=13, val_y=22)


# ---------------------------------------------------------------- reset + power switches
def gen_reset():
    fp = Fp("CC_SW_Reset", "6x3.5 mm through-hole reset button (APEM MJTP1243), reversible by being through-hole.", "through_hole")
    fp.tht(1, -3.25, 0, 2.25, 1.3, shape="rect")
    fp.tht(2, 3.25, 0, 2.25, 1.3)
    fp.pad_box(-4.375, -1.125, 4.375, 1.125)
    fp.both_rect("Fab", -3.0, -1.75, 3.0, 1.75, 0.1)
    fp.both_rect("CrtYd", -4.9, -2.1, 4.9, 2.1, 0.05)
    fp.model("${KICAD10_3DMODEL_DIR}/Button_Switch_THT.3dshapes/SW_PUSH_1P1T_6x3.5mm_H4.3_APEM_MJTP1243.step", (-3.25, 0, 0))
    return fp.write(ref_y=-3.2, val_y=3.2)


def gen_power():
    fp = Fp("CC_SW_Power_PCM12", "Reversible C&K PCM12 side-actuated slide switch; lever faces +y (board edge). "
            "Pins 1 and 2 joined front/back by vias; pin 3 unused (left unjoined).", "smd")
    for x, y in ((-3.65, -0.78), (3.65, -0.78), (-3.65, 1.43), (3.65, 1.43)):
        for s in "FB":
            fp.smd("", x, y, 1.0, 0.8, s)  # mechanical hold-down pads
    for x in (-1.5, 1.5):
        fp.npth(x, 0.33, 0.9)
    for num, xf, xb in (("1", -2.25, 2.25), ("2", 0.75, -0.75), ("3", 2.25, -2.25)):
        fp.smd(num, xf, -1.43, 0.7, 1.5, "F")
        fp.smd(num, xb, -1.43, 0.7, 1.5, "B")
    fp.via("2", 0, -2.9)
    fp.strip("2", "F", (0.75, -2.0), (0.75, -2.15), (0, -2.9))
    fp.strip("2", "B", (-0.75, -2.0), (-0.75, -2.15), (0, -2.9))
    fp.via("1", 3.3, -2.9)
    fp.strip("1", "B", (2.25, -1.85), (3.3, -2.9))
    fp.strip("1", "F", (-2.25, -2.0), (-2.25, -3.45), (-1.9, -3.8), (2.95, -3.8), (3.3, -3.45), (3.3, -2.9))  # over pin 2's via
    fp.both_rect("Fab", -3.35, -1.0, 3.35, 1.6, 0.1)
    fp.both_rect("CrtYd", -4.2, -4.25, 4.2, 2.3, 0.05)  # no silk: the lever edge sits on the board edge
    fp.model("${KICAD10_3DMODEL_DIR}/Button_Switch_SMD.3dshapes/SW_SPDT_PCM12.step")
    return fp.write(ref_y=-5.2, val_y=3.2)


# ---------------------------------------------------------------- battery connector
def gen_battery():
    fp = Fp("CC_Battery_MX1.25", "Reversible 2-pin 1.25 mm battery connector (Molex CLIK-Mate 502386, sold as 'MX1.25'). "
            "Pin 1 = BAT+. Pins swap sides front/back; each pin's front and back pads meet at its via "
            "(pin 1 above the pads, pin 2 under the housing).", "smd")
    for num, xf in (("1", -0.625), ("2", 0.625)):
        fp.smd(num, xf, -1.85, 0.6, 1.7, "F")  # KiCad stock pad size and pitch
        fp.smd(num, -xf, -1.85, 0.6, 1.7, "B")
    for x in (-2.475, 2.475):
        for s in "FB":
            fp.smd("", x, 1.35, 1.0, 2.7, s)  # housing hold-down pads
    fp.via("1", 0, -3.6)
    fp.via("2", 0, -0.1)
    for sx, side in ((-1, "F"), (1, "B")):  # pin 1 sits at sx * 0.625 on this side, pin 2 opposite
        fp.strip("1", side, (sx * 0.625, -2.5), (sx * 0.625, -2.975), (0, -3.6))
        fp.strip("2", side, (-sx * 0.625, -1.2), (-sx * 0.625, -0.725), (0, -0.1))
        fp.pin1(side, sx * 1.55, -1.85, -sx, 0)
    fp.pad_box(-0.925, -2.7, 0.925, -1.0)
    fp.both_rect("Fab", -2.925, -1.8, 2.925, 2.6, 0.1)  # housing
    fp.both_rect("CrtYd", -3.5, -4.15, 3.5, 3.25, 0.05)
    fp.model("${KICAD10_3DMODEL_DIR}/Connector_Molex.3dshapes/Molex_CLIK-Mate_502386-0270_1x02-1MP_P1.25mm_Horizontal.step")
    return fp.write(ref_y=-4.8, val_y=3.9)


# ---------------------------------------------------------------- mounting hole
def gen_hole():
    fp = Fp("CC_Hole_4.1mm", "4.1 mm unplated mounting hole (same size as the old HOLE_M2_TH, so the case still fits). "
            "Corner brackets on both silk layers.", "exclude_from_pos_files exclude_from_bom")
    fp.npth(0, 0, 4.1)
    h, arm = 2.75, 1.0
    for s in "FB":
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            fp.poly(f"{s}.SilkS", [(sx * h, sy * (h - arm)), (sx * h, sy * h), (sx * (h - arm), sy * h)])
    fp.both_rect("CrtYd", -2.3, -2.3, 2.3, 2.3, 0.05)
    return fp.write(ref_y=-3.7, val_y=3.7)


if __name__ == "__main__":
    made = [gen_mx(1), gen_mx(1.5), gen_ec11(), gen_led(), gen_diode(), gen_nano(), gen_display(), gen_reset(), gen_power(),
            gen_battery(), gen_hole()]
    for m in made:
        assert re.fullmatch(r"CC_[\w.\-]+", m)
    print("wrote", len(made), "footprints to", LIB)
