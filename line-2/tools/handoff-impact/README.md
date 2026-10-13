# Handoff Revision Impact

Compare two fully verified HANDOFF v1 archives and trace changed or removed
payloads back to selected baseline files through an explicit dependency graph.
An unchanged README can require review when a code file it depends on changed.
Python 3.8+ and only its standard library are needed. From the workspace root:

```sh
python3 -B line-2/tools/handoff-impact/impact.py demo
```

When tried, the actual inherited `line-2/handoff.zip` verified as two files,
12,603 payload bytes and 13,181 archive bytes. A clearly hypothetical code
comment was added **in memory** to `handoff.py`. The unchanged `README.md` was
correctly flagged through its declared dependency. Neither archive payload was
executed; the demo writes nothing. The inherited archive digest is
`aaa03a258268263186f610e17ad8ede6851c8597b70a7ec29ae6b283f72f60bb`.

For actual revisions, declare baseline dependencies in a public JSON file:

```json
{
  "format": "handoff-impact-graph-v1",
  "roots": ["README.md"],
  "dependencies": {"README.md": ["handoff.py"], "handoff.py": []}
}
```

Every root and referenced dependency needs a declaration, including explicit
empty lists for leaves. Every graph node must exist in the baseline archive;
the graph may cover only part of that archive. Roots must be nonempty and
unique; duplicate edges, unsafe paths and reserved `HANDOFF.json` are refused.
Cycles and self-edges terminate. Names are exact, case sensitive archive paths.
Use the delivered example to check the inherited archive against itself:

```sh
python3 -B line-2/tools/handoff-impact/impact.py check line-2/handoff.zip line-2/handoff.zip line-2/tools/handoff-impact/example-graph.json --fail-on-impact
```

Replace the second archive with a candidate revision. The deterministic JSON
report includes both archive digests, full byte-level comparison, chosen
baseline closure, directly modified files, missing dependencies, transitively
affected files, affected/unaffected roots, and changed files outside that
closure. Each file reaches itself, so a changed or removed root is affected
even with no dependencies. Additions are retained in the comparison but not
inferred as new dependencies. Changes outside the chosen closure are explicit
diagnostics. Archive metadata changes alone do not count as payload impact.
The graph digest includes both roots and dependencies, encoded as sorted,
compact ASCII JSON without a newline.

Ordinary valid checks exit 0. `--fail-on-impact` exits 2 when a selected root is
affected, retaining the JSON report. Invalid inputs exit 1 with stderr and no
partial JSON. Argparse syntax errors exit 2 without a report.
`--before-sha256 HASH` and `--after-sha256 HASH` require independently retained
archive digests. A digest calculated from the candidate itself establishes no
sender authenticity.

Both archives are captured once into bounded immutable byte snapshots. All
payloads, including those outside the selected graph, pass the inherited ZIP,
CRC and manifest digest verifier before impact is reported. Default limits are
66 MiB per archive, 64 MiB payload, 1,000 files, 512 KiB manifest and central
metadata. Graphs are capped at 512 KiB, 1,000 nodes, 10,000 edges and 1,024 UTF-8
bytes per name. The completed JSON report is capped at 99,000 bytes; an oversized
report is refused rather than truncated. Peak memory can exceed the combined
archive sizes. Graph duplicate JSON keys, NaN/Infinity and unknown fields are
refused. Inputs must be relative regular workspace files, without `..`, symlinks
or FIFOs. Keep the workspace stable: the inherited reader does not prevent
hostile ancestor-directory replacement or make multi-file capture atomic.

Keep these trusted local runtime modules at their existing workspace paths:

- `line-2/tools/handoff-dependencies/dependencies.py`
- `line-2/tools/handoff-subset/subset.py`
- `line-2/tools/handoff-inspect/inspect_handoff.py`
- `line-2/tools/handoff/handoff.py`
- `line-2/tools/handoff-compare/compare_handoff.py`

The demo additionally needs `line-2/handoff.zip`. Archive code is never imported.
No network, extraction, environment-variable reads, keys, wallets, signing,
transactions, payments or uploads are provided. No coin or pool is needed.

All 24 behavioral tests passed:

```sh
python3 -B line-2/tools/handoff-impact/test_impact.py
```

Coverage includes same-size/transitive changes, removals, shared dependencies,
cycles, self-edges, additions, unrelated changes, metadata-only changes, invalid
graphs, deterministic ordering, trusted digests, corrupt unselected payloads,
limits, path boundaries, CLI exits and replacing input paths after their single
capture. The first run exposed absolute fixture paths from Python's temporary
directory helper; making those fixtures workspace-relative fixed the tests.
The production path guard correctly refused them.

This checks **declared baseline impact**, not semantic breakage. Declarations
may be incomplete or wrong; a new revision can introduce a dependency absent
from the baseline graph. Update and review declarations separately. An
unaffected result does not prove runnable code, safe execution, build
reproducibility, authorship or correctness. Affected roots deserve review;
they are not automatically broken.
