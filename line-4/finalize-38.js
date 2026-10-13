// Format preparation and additive pigment compositing, using Node built-ins only.
// The input motif comes from the installed image generator, not this program.
const fs = require('node:fs');
const zlib = require('node:zlib');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const ancestorPath = 'artifacts/line-4/wall.png';
const outputPath = 'artifacts/line-4/wall-v19.png';
const expected = '46ef5d3f5d3e828d274fdb703df6e65705251c48baf70f7d81bec8f51bb43955';
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const ancestorBytes = fs.readFileSync(ancestorPath);
assert.equal(hash(ancestorBytes), expected, 'refuse to replace a different ancestor');

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function decode(bytes) {
  assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  let width, height, channels;
  const compressed = [];
  for (let pos = 8; pos < bytes.length;) {
    const size = bytes.readUInt32BE(pos);
    const type = bytes.subarray(pos + 4, pos + 8).toString('ascii');
    const body = bytes.subarray(pos + 8, pos + 8 + size);
    assert.equal(crc32(bytes.subarray(pos + 4, pos + 8 + size)), bytes.readUInt32BE(pos + 8 + size));
    if (type === 'IHDR') {
      width = body.readUInt32BE(0); height = body.readUInt32BE(4);
      assert.equal(body[8], 8); assert.ok([2, 6].includes(body[9]));
      assert.deepEqual([...body.subarray(10)], [0, 0, 0]);
      channels = body[9] === 2 ? 3 : 4;
    }
    if (type === 'IDAT') compressed.push(body);
    if (type === 'IEND') break;
    pos += size + 12;
  }
  const stride = width * channels;
  const raw = zlib.inflateSync(Buffer.concat(compressed));
  assert.equal(raw.length, (stride + 1) * height);
  const pixels = Buffer.alloc(width * height * 3);
  let previous = Buffer.alloc(stride);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    const row = Buffer.from(raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1)));
    for (let i = 0; i < stride; i++) {
      const a = i >= channels ? row[i - channels] : 0;
      const b = previous[i], c = i >= channels ? previous[i - channels] : 0;
      let predictor;
      if (filter === 0) predictor = 0;
      else if (filter === 1) predictor = a;
      else if (filter === 2) predictor = b;
      else if (filter === 3) predictor = Math.floor((a + b) / 2);
      else if (filter === 4) {
        const p = a + b - c, da = Math.abs(p - a), db = Math.abs(p - b), dc = Math.abs(p - c);
        predictor = da <= db && da <= dc ? a : db <= dc ? b : c;
      } else throw new Error('invalid PNG filter');
      row[i] = (row[i] + predictor) & 255;
    }
    for (let x = 0; x < width; x++) {
      if (channels === 4) assert.equal(row[x * channels + 3], 255);
      row.copy(pixels, (y * width + x) * 3, x * channels, x * channels + 3);
    }
    previous = row;
  }
  return { width, height, pixels };
}

function chunk(name, body) {
  const type = Buffer.from(name), out = Buffer.alloc(body.length + 12);
  out.writeUInt32BE(body.length); type.copy(out, 4); body.copy(out, 8);
  out.writeUInt32BE(crc32(Buffer.concat([type, body])), body.length + 8);
  return out;
}

function encode(image) {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(image.width); header.writeUInt32BE(image.height, 4);
  header[8] = 8; header[9] = 2;
  const stride = image.width * 3, raw = Buffer.alloc((stride + 1) * image.height);
  for (let y = 0; y < image.height; y++) image.pixels.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  return Buffer.concat([Buffer.from('89504e470d0a1a0a', 'hex'), chunk('IHDR', header),
    chunk('IDAT', zlib.deflateSync(raw, {level: 9})), chunk('IEND', Buffer.alloc(0))]);
}

const wall = decode(ancestorBytes);
const motifBytes = fs.readFileSync(outputPath), motif = decode(motifBytes);
assert.deepEqual([wall.width, wall.height], [1254, 1254]);
assert.deepEqual([motif.width, motif.height], [1536, 1024]);
const original = Buffer.from(wall.pixels);
const rectangle = [70, 660, 112, 102];
const [left, top, width, height] = rectangle;
const crop = [440, 210, 665, 585];
let changed = 0;
for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
  const sx0 = crop[0] + Math.floor(x * crop[2] / width);
  const sx1 = crop[0] + Math.floor((x + 1) * crop[2] / width);
  const sy0 = crop[1] + Math.floor(y * crop[3] / height);
  const sy1 = crop[1] + Math.floor((y + 1) * crop[3] / height);
  const rgb = [0, 0, 0]; let count = 0;
  for (let sy = sy0; sy < sy1; sy++) for (let sx = sx0; sx < sx1; sx++) {
    for (let c = 0; c < 3; c++) rgb[c] += motif.pixels[(sy * motif.width + sx) * 3 + c];
    count++;
  }
  for (let c = 0; c < 3; c++) rgb[c] /= count;
  // Near-white paper disappears; rock texture remains in the pigment.
  const ink = Math.max(0, Math.min(1, (248 - Math.min(...rgb)) / 175));
  const feather = Math.min(1, x / 5, y / 5, (width - 1 - x) / 5, (height - 1 - y) / 5);
  const at = ((top + y) * wall.width + left + x) * 3;
  const shade = (original[at] + original[at + 1] + original[at + 2]) / (3 * 150);
  const opacity = ink * feather * 0.70;
  let different = false;
  for (let c = 0; c < 3; c++) {
    const pigment = rgb[c] * Math.max(0.36, Math.min(0.85, shade));
    wall.pixels[at + c] = Math.round(original[at + c] * (1 - opacity) + pigment * opacity);
    different ||= wall.pixels[at + c] !== original[at + c];
  }
  if (different) changed++;
}
let changedOutside = 0;
for (let y = 0; y < wall.height; y++) for (let x = 0; x < wall.width; x++) {
  if (x >= left && x < left + width && y >= top && y < top + height) continue;
  const p = (y * wall.width + x) * 3;
  if (!wall.pixels.subarray(p, p + 3).equals(original.subarray(p, p + 3))) changedOutside++;
}
assert.equal(changedOutside, 0); assert.ok(changed > 0);
const final = encode(wall);
fs.writeFileSync(outputPath, final); fs.writeFileSync(ancestorPath, final);
const review = {
  name: 'The Tied Observations', ancestor_sha256: expected,
  generated_motif_sha256: hash(motifBytes), wall_sha256: hash(final),
  wall: {paths: [ancestorPath, outputPath], dimensions: [wall.width, wall.height],
         format: 'PNG', colour: '8-bit RGB', bytes: final.length},
  addition_rectangle: rectangle, generated_crop: crop,
  changed_pixels: changed, changed_pixels_outside_addition: changedOutside,
  method: 'Installed built-in image generator supplied the motif; Node built-ins removed white in memory and composited pigment only in vacant rock. Generated motif overwritten by final wall.'
};
fs.writeFileSync('line-4/round-38-image-review.json', JSON.stringify(review, null, 2) + '\n');
console.log(JSON.stringify(review));
