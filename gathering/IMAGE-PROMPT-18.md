# The Gathered Journey

The installed built-in imagegen tool generated the motif. Exact prompt:

> Use case: historical-scene. Make one small isolated prehistoric cave pigment motif for addition to an inherited wall, on a plain white background. A simple irregular charcoal cord loosely encloses three small red-ochre pebbles in a single cluster, with a tiny yellow-ochre pebble outside the cord, conveying three observations belonging together. Burnt-stick uneven lines, thumb daubs, earth pigments only, worn sparse silhouette, no gradients, no cast shadows. No figures or hands; no letters, numbers, captions, signatures, logos, watermarks, borders or frames. No photography or 3D. This generated mark will be added onto existing rock without changing any ancestor. Output a square PNG. If a workspace save is supported, use artifacts/gathering/wall-v19.png.

The ancestral gathering wall was downloaded from record 17's artifact URL,
SHA-256 verified, and visually inspected. The generator's returned image bytes
were saved only in the required wall output slot. finish_wall18.py transfers
the generated earth pigment onto vacant upper rock in (420,65,150,105), using
the inherited composition method: white paper contributes no pigment, sparse
generated texture is area-averaged, and stone remains visible. The output slot
is then replaced by the complete final wall, with an identical continuation
wall.png. No extra generated image remains in the workspace.

5516 pixels changed, zero outside the addition rectangle. Every ancestral mark
outside it, the frog, cracks, light and framing remain byte-identical. Final
PNG and 512-px JPEG were inspected. Each inherited hand has four fingers and
one thumb; no new hands were added. No writing or prohibited symbols observed.
No known unmet visual requirement. Inherited photographic-looking rock and
the small, subdued mark in the JPEG remain local-review limitations. Image
dimensions, formats and hashes are in checks/round-18/image-preservation.json.

Meaning: A charcoal cord gathers the stones of one journey without losing their traces.

The composition helper is one-time and requires the ancestor plus the original
generated motif; it cannot be rerun on the already-finished wall.
