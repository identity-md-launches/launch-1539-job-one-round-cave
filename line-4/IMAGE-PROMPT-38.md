# The Tied Observations

Installed built-in `image_gen` tool, generation of a supporting pigment insert.
The returned image bytes were used directly; no generated file outside the
workspace was read. The insert temporarily occupied the required output path,
then was overwritten by the completed wall. No extra picture remains in the
workspace.

Exact prompt:

> Use case: illustration-story. Create a small prehistoric earth-pigment motif for addition to an existing cave wall. A bundle of exactly three small rounded pebbles, tied together by one looping charcoal cord, showing separate observations held as one group. Only this single motif, centrally positioned on a pure white background with ample white margin. Red and yellow ochre pebbles, burnt charcoal black cord; rough irregular thumb-dab and burnt-stick marks with pigment gaps and worn edges. Flat hand-made cave drawing, no realism, no shadows, no 3D. No rock background. No hands, no frogs, no people, no letters, no numbers, no text, no logo, no frame or border, no watermarks. This is a supporting insert for an existing wall; final wall must retain all existing ancestral paintings unchanged. If saving the generated asset, use only artifacts/line-4/wall-v19.png in the workspace; it will be overwritten with the finished full wall.

`finalize-38.js` uses Node's built-in PNG/zlib and file functions to add the
pigment within (70,660,112,102), retaining rock texture. It refuses an unexpected
ancestor digest. The addition is 6,835 changed pixels, zero outside that
rectangle. All ancestors, including Pepe and every inherited hand, remain
unchanged. The script is an image preparation record; rerunning it requires
the original ancestor and generated insert, which are not additional delivered
pictures. The final wall is the deliverable.

The already reviewed `gathering/make_thumbnail.py` standard-library helper
converted the final RGB PNG into the required 512px baseline JPEG. This is
format conversion only. No dependency was installed. Visual review of the
finished PNG and JPEG is recorded in `round-38-image-review.json`.
