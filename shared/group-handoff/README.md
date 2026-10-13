# Transaction group handoff

Carry a bounded ERC-20 transfer observation with its transaction groups in a
reproducible HANDOFF v1 ZIP. The receiver verifies every payload, rebuilds the
groups from raw logs, and checks the exact dependency graph. Compare revisions
to see when changed evidence requires another review, even if the grouped
report stays identical. This joins Line 4's transaction groups with Line 2's
dependency selection and revision impact. ZTO is the default real token; valid
IMD captures also work. Python 3.10+ and the standard library only.

From the repository root, one command shows it working offline:

```sh
python3 -B shared/group-handoff/group_handoff.py demo
```

Tried locally: the unchanged retained real ZTO observation contains three
transfers in one mined transaction at block 26177309, log indexes 642, 644 and
645. Its four endpoints include an intermediate endpoint that receives and
forwards the same amount, with zero net event flow. The demo builds an archive
twice, verifies the exact original evidence bytes, recomputes the report, and
finds no revision impact when comparing the archive with itself. It writes
nothing and uses no network.

A fresh gathering read from dRPC at 2026-10-13T08:43:47Z returned the same
three events. `examples/fresh-zto-groups.zip` carries its exact native capture;
`examples/zto-groups.zip` carries the dated line observation. Both are checked
by the original Line 2 inspector. Comparing them reports changed evidence and
an affected review root while `group_report_changed` is false: capture time,
provider and extra raw RPC fields changed, but the decoded groups did not.
This distinguishes source-byte review from changed event meaning.

```sh
python3 -B shared/group-handoff/group_handoff.py check shared/group-handoff/examples/fresh-zto-groups.zip
python3 -B shared/group-handoff/group_handoff.py compare shared/group-handoff/examples/zto-groups.zip shared/group-handoff/examples/fresh-zto-groups.zip --fail-on-impact
```

The second command intentionally exits 2 with a review report. To package a
public capture selected inside your workspace, create the destination directory
first and choose a new filename:

```sh
python3 -B shared/group-handoff/group_handoff.py pack shared/group-handoff/examples/zto-window.json test/scratch/my-groups.zip
```

The archive contains `evidence/window.json`, `review/groups.json`,
`review/dependencies.json`, and the original writer's `HANDOFF.json` manifest.
The fixed report dependencies include both evidence and graph; no declaration
can silently drop the raw logs. `check --sha256 HASH` and comparison's
`--before-sha256 HASH` / `--after-sha256 HASH` accept independently retained
archive digests. A self-calculated digest is an integrity identifier, not
sender authentication.

Ordinary success exits 0. Comparison with `--fail-on-impact` exits 2 when
review is required. Invalid inputs exit 1 with no receipt on stdout. Inputs,
combined payload, ZIP and JSON output are each capped at 99000 bytes; no
truncation occurs. Strict JSON refuses duplicate keys, floating point and
non-finite numbers and nesting beyond 64 levels. The line validator still
requires mainnet, real ZTO/IMD identities, bounded ranges, matching decoded
summaries, stable boundary metadata and consistent mined transaction positions.
Input files must be relative regular workspace files. Descriptor-relative
no-follow reads reject traversal, symlinks, directories and FIFOs. Outputs use
exclusive creation through no-follow parents and never overwrite an existing
file. POSIX file flags are required. The workspace and installed modules are
trusted; this is not a sandbox against hostile concurrent directory renames,
hard links or file rewrites.

Sixteen behavioral tests passed:

```sh
python3 -B -m unittest discover -s shared/group-handoff -p 'test_*.py' -v
```

They exercise real groups, zero-net routing, exact bytes, deterministic ZIPs,
validly rehashed false reports, graph omissions, forged decoded summaries,
conflicting transaction positions, source-only revisions, trusted digests,
strict parsing, bounds, corrupt/noncanonical archives, empty windows, file
boundaries, exclusive output and copying this whole folder to a new workspace.
All eleven runtime modules are delivered as ordinary files. Six are byte-for-
byte copies; five adapt only import or workspace roots. PROVENANCE.json records
source/copy SHA-256 and each adaptation. Copy this whole folder, including
vendor and examples, for standalone use. No install is needed.

Groups describe this token's observed Transfer events, not complete receipts,
trade volume, prices, balances, holders, consensus or finality. Routed amounts
may be counted several times in event totals. A shared PoolManager endpoint
does not identify the named Uniswap v4 pool's swaps. Impact means changed bytes
reach a declared baseline review root; it does not establish semantic breakage.
Nothing is extracted or executed from an archive. No environment settings,
wallets, keys, signing, transaction submission, payment or uploads are used.
