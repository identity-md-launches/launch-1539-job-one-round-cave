#!/usr/bin/env python3
"""Check round 38 formats and scope without network or external files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def jpeg_size(data):
    assert data[:2] == b'\xff\xd8' and data[-2:] == b'\xff\xd9'
    pos = 2
    while pos < len(data):
        assert data[pos] == 255
        marker = data[pos + 1]
        length = int.from_bytes(data[pos + 2:pos + 4], 'big')
        if marker == 0xc0:
            depth, height, width = struct.unpack('>BHH', data[pos + 4:pos + 9])
            assert depth == 8
            return width, height
        assert marker != 0xda, 'missing baseline frame header'
        pos += 2 + length
    raise AssertionError('missing JPEG dimensions')


def main():
    spec = importlib.util.spec_from_file_location('thumbnail_check_38', ROOT / 'gathering/make_thumbnail.py')
    thumbnail = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(thumbnail)
    images = [ROOT / 'artifacts/line-4' / name for name in ('wall.png', 'wall-v19.png')]
    wall = images[0].read_bytes()
    assert images[1].read_bytes() == wall
    width, height, rows = thumbnail.png_rgb(wall)
    assert (width, height) == (1254, 1254)
    assert len(rows) == height
    jpeg = (ROOT / 'dist/line-4/38.jpg').read_bytes()
    assert jpeg_size(jpeg) == (512, 512)
    assert len(jpeg) < 100000

    records = sorted((ROOT / 'dist/line-4').glob('[0-9][0-9].json'))
    assert len(records) == 38 and records[-1].name == '38.json'
    record = json.loads(records[-1].read_text())
    assert set(record) == {'name', 'image', 'attributes'}
    assert record['image'] == 'https://api.imd.fun/artifacts/' + digest(wall)
    assert record['name'] == 'The Tied Observations'
    assert len(record['attributes']) == 6
    for trait in record['attributes']:
        assert set(trait) == {'trait_type', 'value'}
    attributes = {trait['trait_type']: trait['value'] for trait in record['attributes']}
    assert set(attributes) == {'Cave', 'Wall', 'Number', 'Left behind', 'Meaning', 'One thing'}
    assert attributes['Cave'] == 'Base' and attributes['Wall'] == 'Line 4'
    assert type(attributes['Number']) is int and attributes['Number'] == 38
    assert all(type(attributes[k]) is str and attributes[k] for k in attributes if k != 'Number')
    review = json.loads((ROOT / 'line-4/round-38-image-review.json').read_text())
    assert review['wall_sha256'] == digest(wall)
    assert review['changed_pixels_outside_addition'] == 0
    assert review['changed_pixels'] == 6835
    assert review['unmet_visual_requirements'] == []

    originals = [ROOT / 'line-4/GOAL.md', *records[:-1]]
    for path in originals:
        relative = path.relative_to(ROOT).as_posix()
        original = subprocess.run(['git', 'show', 'HEAD:' + relative], cwd=ROOT,
                                  capture_output=True, check=True).stdout
        assert path.read_bytes() == original, 'ancestor changed: ' + relative
    changed = subprocess.run(['git', 'diff', '--name-only'], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.splitlines()
    new = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.splitlines()
    permitted = ('line-4/', 'artifacts/line-4/', 'dist/line-4/', 'test/scratch/')
    assert all(path.startswith(permitted) for path in changed + new), 'out-of-scope change'
    for relative in changed + new:
        path = ROOT / relative
        if path.is_file() and not relative.startswith(('artifacts/', 'test/scratch/')):
            assert path.stat().st_size < 100000, 'oversized delivered file: ' + relative
    assert subprocess.run(['git', 'ls-files', '--error-unmatch', 'artifacts/line-4/wall-v19.png'],
                          cwd=ROOT, capture_output=True).returncode != 0
    result = {
        'all_checks_passed': True, 'record_number': 38,
        'wall': {'dimensions': [width, height], 'format': 'PNG', 'sha256': digest(wall)},
        'thumbnail': {'dimensions': [512, 512], 'format': 'baseline JPEG', 'bytes': len(jpeg)},
        'unchanged_goal': True, 'unchanged_older_records': 37,
        'changed_pixels_outside_addition': 0,
        'unmet_visual_requirements': review['unmet_visual_requirements'],
        'local_review_only': True,
    }
    (ROOT / 'line-4/round-38-deliverable-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
