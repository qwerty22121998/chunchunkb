#!/usr/bin/env python3
"""Check the via half of the routing style rule, which KiCad's DRC can't express:
no track may turn more than 45 degrees through a via. Every track touching a via (ending on it, or
passing straight through it) must have a partner track at that via, on either layer, at 135 degrees
or more (180 = straight on). Same-layer corners are covered by chunchunkb.kicad_dru (track_angle).
usage: python3 tools/check_via_bends.py [board.kicad_pcb]      (needs KiCad's pcbnew module; reads the saved file)"""
import math
import sys

import pcbnew

TOL = 0.01  # mm: an end counts as "on" the via if it is this close to the via centre


def arms(board):
    """via -> list of unit vectors pointing from the via along each track touching it."""
    mm = pcbnew.ToMM
    vias = [t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA']
    segs = [t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK']
    out = {}
    for v in vias:
        c = v.GetPosition()
        cx, cy = mm(c.x), mm(c.y)
        a = []
        for s in segs:
            if s.GetNetCode() != v.GetNetCode():
                continue
            p, q = s.GetStart(), s.GetEnd()
            px, py, qx, qy = mm(p.x), mm(p.y), mm(q.x), mm(q.y)
            for (ex, ey), (ox, oy) in (((px, py), (qx, qy)), ((qx, qy), (px, py))):
                if math.hypot(ex - cx, ey - cy) < TOL:  # track ends at the via
                    d = math.hypot(ox - ex, oy - ey)
                    a.append(((ox - ex) / d, (oy - ey) / d))
                    break
            else:  # passes through the via: two arms
                dx, dy = qx - px, qy - py
                L = math.hypot(dx, dy)
                t = ((cx - px) * dx + (cy - py) * dy) / (L * L)
                if TOL / L < t < 1 - TOL / L and math.hypot(px + t * dx - cx, py + t * dy - cy) < TOL:
                    a += [(dx / L, dy / L), (-dx / L, -dy / L)]
        out[(round(cx, 3), round(cy, 3), v.GetNetname())] = a
    return out


def main():
    board = pcbnew.LoadBoard(sys.argv[1] if len(sys.argv) > 1 else 'chunchunkb.kicad_pcb')
    bad = []
    for key, a in arms(board).items():
        for i, (ux, uy) in enumerate(a):
            # angle between this arm and its straightest partner: 180 = straight through
            best = max((math.degrees(math.acos(max(-1.0, min(1.0, ux * vx + uy * vy)))) for j, (vx, vy) in enumerate(a) if j != i),
                       default=180.0)
            if best < 134.5:
                bad.append((key, round(best, 1)))
                break
    for (x, y, net), ang in bad:
        print(f'via {net} @ ({x}, {y}): sharpest pass-through {ang} deg (want >= 135)')
    print(f'{len(bad)} via bend violation(s)')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
