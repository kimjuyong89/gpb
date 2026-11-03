#!/usr/bin/env python3
"""Simulate GPA's RegionView rendering with InkPixel tiles, to verify drop-in compatibility.

  python3 Tools/gpa_sim/render_region.py <region> [--scale 2] [--out Docs/previews/gpa_<region>.png]

Reads Integration/GPA/layouts/<Region>.txt and tiledefs_<region>.json (resolved), slices sheets exactly
like RegionView.Slice (16px cells from the top-left, props anchored at their top-left letter and
extending down/right), draws ground under props, Y-sorts props/NPCs (lower on screen = in front),
draws NPC walk frame (down, 0) and the player at '@'.
"""
import argparse, json, os, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
ART = os.path.join(ROOT, 'Assets', 'InkPixel', 'Art')
GPA_DIR = os.path.join(ROOT, 'Integration', 'GPA')
CELL = 16
_sheets = {}


def sheet(rel):
    if rel not in _sheets:
        _sheets[rel] = Image.open(os.path.join(ART, rel)).convert('RGBA')
    return _sheets[rel]


def slice_cells(rel, cx, cy, sx, sy):
    return sheet(rel).crop((cx * CELL, cy * CELL, (cx + sx) * CELL, (cy + sy) * CELL))


def render(region, scale=2, out=None):
    defs = json.load(open(os.path.join(GPA_DIR, f'tiledefs_{region.lower()}.json'), encoding='utf-8'))
    rows = open(os.path.join(GPA_DIR, 'layouts', f'{region}.txt'), encoding='utf-8').read().rstrip('\n').split('\n')
    tiles = {t['key']: t for t in defs['tiles']}
    npcs = {n['key']: n for n in defs['npcs']}
    special_ground = defs.get('specialGround', '=')
    height = len(rows)
    width = max(len(r) for r in rows)
    img = Image.new('RGBA', (width * CELL, height * CELL), (30, 27, 24, 255))
    layer = []  # (sort_key, image, x_px, y_px)
    for row, line in enumerate(rows):
        for x in range(width):
            c = line[x] if x < len(line) else ' '
            if c == ' ':
                continue
            is_special = c == '@' or c == 'E' or c in npcs
            d = tiles.get(special_ground) if is_special else tiles.get(c)
            if d is None:
                continue
            is_prop = d['sizeX'] != 1 or d['sizeY'] != 1 or d['overlay']
            ground = tiles.get(d['ground']) if is_prop else d
            if ground is not None:
                img.alpha_composite(slice_cells(ground['sheet'], ground['cellX'], ground['cellY'], 1, 1), (x * CELL, row * CELL))
            if is_prop:
                im = slice_cells(d['sheet'], d['cellX'], d['cellY'], d['sizeX'], d['sizeY'])
                bottom = row + d['sizeY']  # rows grow downward; larger = nearer
                layer.append((bottom, im, x * CELL, row * CELL))
            if c in npcs:
                n = npcs[c]
                if 'prop' in n:
                    im = slice_cells(n['prop'], n['propCellX'], n['propCellY'], 1, 1)
                else:
                    im = slice_cells(n['sheet'], 0, 0, 1, 1)  # walk down frame 0
                layer.append((row + 1 + 0.5, im, x * CELL, row * CELL))
            if c == '@' and defs.get('playerSheet'):
                im = slice_cells(defs['playerSheet'], 0, 0, 1, 1)
                layer.append((row + 1 + 0.5, im, x * CELL, row * CELL))
    for _, im, px, py in sorted(layer, key=lambda t: t[0]):
        img.alpha_composite(im, (px, py))
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    out = out or os.path.join(ROOT, 'Docs', 'previews', f'gpa_{region.lower()}.png')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    print('wrote', out, img.size)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('region')
    ap.add_argument('--scale', type=int, default=2)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    render(a.region, a.scale, a.out)
