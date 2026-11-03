#!/usr/bin/env python3
"""Resolve InkPixel sprite names in Integration/GPA/tiledefs_*.src.json into the cell coordinates
GPA's RegionData needs, using the generated sidecar JSON files.

  python3 Tools/gpa_sim/resolve_tiledefs.py            # resolves every *.src.json next to it

Output: tiledefs_<region>.json with entries
  tiles: {key, sheet (relative to sheetBase, e.g. "Tiles/town.png"), cellX, cellY, sizeX, sizeY,
          solid, ground, overlay, portal, encounterNode}
  npcs:  {key, name, sheet ("Characters/<name>.png")}  or  {key, name, prop (sheet path), propCellX, propCellY}
"""
import glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
ART = os.path.join(ROOT, 'Assets', 'InkPixel', 'Art')
GPA_DIR = os.path.join(ROOT, 'Integration', 'GPA')


def load_index():
    """sprite name -> (sheet relative path like 'Tiles/town.png', entry dict)"""
    index = {}
    for sidecar in glob.glob(os.path.join(ART, '**', '*.sprites.json'), recursive=True):
        data = json.load(open(sidecar, encoding='utf-8'))
        png = sidecar[:-len('.sprites.json')] + '.png'
        rel = os.path.relpath(png, ART).replace(os.sep, '/')
        for sp in data.get('sprites', []):
            index[sp['name']] = (rel, sp, data)
    return index


def resolve(src_path, index, strict=True):
    src = json.load(open(src_path, encoding='utf-8'))
    out = {k: src[k] for k in ('region', 'sheetBase', 'specialGround', 'playerSheet') if k in src}
    out['tiles'] = []
    missing = []
    for t in src['tiles']:
        name = t['sprite']
        if name not in index:
            missing.append(name)
            continue
        rel, sp, data = index[name]
        cs = data.get('cellSize', 16) or 16
        out['tiles'].append({
            'key': t['key'], 'sheet': rel,
            'cellX': sp['x'] // cs, 'cellY': sp['y'] // cs,
            'sizeX': max(1, sp['w'] // cs), 'sizeY': max(1, sp['h'] // cs),
            'solid': bool(t.get('solid', sp.get('solid', False))),
            'ground': t.get('ground', '.'),
            'overlay': bool(t.get('overlay', sp.get('overlay', False))),
            'portal': t.get('portal', ''), 'encounterNode': t.get('encounterNode', ''),
        })
    out['npcs'] = []
    for n in src.get('npcs', []):
        e = {'key': n['key'], 'name': n.get('name', '')}
        if 'sheet' in n:
            png = os.path.join(ART, 'Characters', n['sheet'] + '.png')
            if not os.path.exists(png):
                missing.append('Characters/' + n['sheet'] + '.png')
            e['sheet'] = 'Characters/' + n['sheet'] + '.png'
        if 'prop' in n:
            if n['prop'] not in index:
                missing.append(n['prop'])
                continue
            rel, sp, data = index[n['prop']]
            cs = data.get('cellSize', 16) or 16
            e['prop'] = rel
            e['propCellX'] = sp['x'] // cs
            e['propCellY'] = sp['y'] // cs
        out['npcs'].append(e)
    if 'playerSheet' in src:
        out['playerSheet'] = 'Characters/' + src['playerSheet'] + '.png'
    return out, missing


def main():
    index = load_index()
    ok = True
    for src_path in sorted(glob.glob(os.path.join(GPA_DIR, 'tiledefs_*.src.json'))):
        out, missing = resolve(src_path, index)
        dst = src_path.replace('.src.json', '.json')
        json.dump(out, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print(f"{os.path.basename(dst)}: {len(out['tiles'])} tiles, {len(out['npcs'])} npcs"
              + (f", MISSING {missing}" if missing else ''))
        ok = ok and not missing
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
