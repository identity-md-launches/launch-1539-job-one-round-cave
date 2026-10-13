"""Confine generated earth pigment to unused rock, preserving ancestor pixels."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    png = load('png_helpers', ROOT / 'line-1/finalize-35.py')
    thumb = load('thumbnail', ROOT / 'gathering/make_thumbnail.py')
    wall = ROOT / 'artifacts/line-1/wall.png'
    output = ROOT / 'artifacts/line-1/wall-v19.png'
    original, generated = wall.read_bytes(), output.read_bytes()
    previous = json.loads((ROOT / 'dist/line-1/37.json').read_text())
    digest = lambda data: hashlib.sha256(data).hexdigest()
    assert digest(original) == previous['image'].rsplit('/', 1)[1]
    width, height, channels, rows = png.decode_png(original)
    gw, gh, gc, marks = png.decode_png(generated)
    assert (width, height, channels) == (1254, 1254, 3)
    assert gc in (3, 4)
    left, top, pw, ph = 700, 231, 103, 103
    # Crop the generated ring and stone; discard all white background in memory.
    sx0, sy0 = int(gw * .18), int(gh * .17)
    sw, sh = int(gw * .64), int(gh * .65)
    changed = 0
    for y in range(ph):
        sy = sy0 + y * sh // ph
        for x in range(pw):
            sx = sx0 + x * sw // pw
            p = sx * gc
            r, g, b = marks[sy][p:p+3]
            alpha = marks[sy][p+3] if gc == 4 else 255
            red = r > 65 and r > g * 1.3 and r > b * 1.55
            yellow = r > 120 and g > 80 and r > g * 1.12 and g > b * 1.45
            charcoal = max(r, g, b) < 125
            if alpha < 165 or not (red or yellow or charcoal):
                continue
            at = (left + x) * 3
            old = rows[top+y][at:at+3]
            pigment = (151, 61, 31) if red else ((183, 125, 42) if yellow else (40, 29, 21))
            strength = .72 * alpha / 255
            new = bytes(round(old[i] * (1-strength) + pigment[i] * strength)
                        for i in range(3))
            if new != old:
                rows[top+y][at:at+3] = new
                changed += 1
    assert changed > 250
    final = png.encode_rgb(rows, width, height)
    _, _, _, before = png.decode_png(original)
    fw, fh, fc, after = png.decode_png(final)
    actual_changed = outside = 0
    for y in range(height):
        for x in range(width):
            p = x * 3
            if before[y][p:p+3] != after[y][p:p+3]:
                actual_changed += 1
                if not (left <= x < left+pw and top <= y < top+ph):
                    outside += 1
    assert actual_changed == changed and outside == 0
    assert (fw, fh, fc) == (1254, 1254, 3)
    jpeg = thumb.jpeg(thumb.resize(width, height, after))
    assert len(jpeg) < 100000
    record = ROOT / 'dist/line-1/38.json'
    assert not record.exists()
    meaning = 'A ring tests the ochre stone within, as saved headers reveal their own hashes.'
    metadata = {
        'name': 'The Tested Stone',
        'image': 'https://api.imd.fun/artifacts/' + digest(final),
        'attributes': [{'trait_type': k, 'value': v} for k, v in (
            ('Cave', 'Base'), ('Wall', 'Line 1'), ('Number', 38),
            ('Left behind', 'header-hash-check'), ('Meaning', meaning),
            ('One thing', 'portable live Ethereum state snapshots'))],
    }
    output.write_bytes(final)
    wall.write_bytes(final)
    (ROOT / 'dist/line-1/38.jpg').write_bytes(jpeg)
    record.write_text(json.dumps(metadata, indent=2) + '\n')
    review = {
        'source_record': 37, 'record_number': 38,
        'source_sha256': digest(original), 'generated_sha256': digest(generated),
        'wall_sha256': digest(final), 'png_dimensions': [width, height],
        'png_format': '8-bit RGB PNG', 'png_bytes': len(final),
        'jpeg_dimensions': [512, 512], 'jpeg_format': 'baseline JPEG',
        'jpeg_bytes': len(jpeg), 'addition_rectangle': [left, top, pw, ph],
        'changed_pixels': changed, 'changed_pixels_outside_rectangle': outside,
        'new_hands_or_stencils': 0,
        'unmet_visual_requirements': [
            'Inherited rock looks photographic and was preserved to retain the cave.'],
        'visual_review': 'Pending final PNG and JPEG inspection.',
    }
    (ROOT / 'line-1/wall-review-38.json').write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps(review, indent=2))


if __name__ == '__main__':
    main()
