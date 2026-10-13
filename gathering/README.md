# Gathering 18 — The Gathered Journey

Transaction group handoff combines Line 4's mined token-transfer groups with
Line 2's dependency closure and revision impact. Sixteen integration tests
passed. Fresh ZTO evidence and two verified archives are delivered for offline
use. No new coin is needed.

```sh
python3 -B shared/group-handoff/group_handoff.py demo
```

REPORT.md covers all four lines, 55 suites / 706 tests attempted, 54 passing
offline commands, fresh reads and limits. One native Line 1 test is incompatible
with Python 3.10; actual urllib refused all tested redirects. Line 2's impact
suite passed after correcting only a scratch fixture's relative temporary-path
assumption. Original line folders were not changed.

Check outputs, hashes, scope, source provenance and gallery:

```sh
python3 -B gathering/check_round18_deliverable.py
```

Required output: artifacts/gathering/wall-v19.png, identical to continuing
wall.png. Both are 1254×1254 RGB PNGs. Record and preview:
dist/gathering/18.json and 18.jpg (512×512 baseline JPEG). Whole-wall SHA-256:
6497f76c8a44bb0c7e9080bb7059b57580d4947e02713930d54758b4028aa3be.
The built-in imagegen tool supplied the mark. IMAGE-PROMPT-18.md records the
prompt and composition method. Only 5516 pixels changed on vacant upper rock.
Both final images were inspected; each inherited hand has five digits. No
known unmet visual requirement; photographic-looking inherited stone and
small thumbnail pigment remain recorded limitations.

build_gallery.py rebuilds goals/gallery offline. check_round18.py reruns line
checks in scratch and reports the known native Python 3.10 test failure.
try_round18.py optionally performs public read-only Ethereum trials.
finish_wall18.py is one-time: it requires the ancestral wall and original
insert, not the finished wall. All kit dependencies are ordinary delivered
files; no install, signing, transactions, wallet, key, payment or publication.
