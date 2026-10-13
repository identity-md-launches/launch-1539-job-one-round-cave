# Header hash check

Rebuild both saved Ethereum execution block headers in a pinned ZTO snapshot
with canonical RLP and Ethereum Keccak-256, then compare their hashes with the
provider's reported hashes. This adds an offline check for changed or internally
inconsistent headers to the line's portable snapshot format. It uses Python's
standard library only and performs no network or transaction operation.

From the repository root, one command shows it working on a retained real ZTO
observation:

```sh
python3 -B line-1/tools/header-hash-check/header_hash_check.py demo
```

I ran this offline: both 649-byte headers at block **26180977** recomputed to
`0xfffa2f6981064c0c17c939eae510a1d8e9add2b9775e1dab07cf4f2b196dae27`.
The output binds the exact source file's SHA-256 and labels ZTO's
**1000000000000000000000000000 base-unit** supply as reported evidence.

I also captured a fresh finalized snapshot through the existing read-only
PublicNode reader at **2026-10-13T08:04:48Z**. Both headers at block **26182186**
recomputed to
`0x548d48bf1517d8775ddc4442f2581ac1df9902e3fc10bc1c45de78193e2e3426`.
The exact 55356-byte response bundle is retained as `live-zto.json` and works
without network:

```sh
python3 -B line-1/tools/header-hash-check/header_hash_check.py check line-1/tools/header-hash-check/live-zto.json
```

`check PATH` also accepts your own `pinned-zto-snapshot/1` captures. Files must
be regular files inside this workspace, at most 4 MiB, with no symlink path
components. The inherited strict JSON reader rejects duplicate keys and
non-finite numbers. Quantities are canonical hex and at most uint256; fixed
byte fields have exact lengths and extraData is at most 32 bytes.

Exit 0 means both hashes match. Exit 2 prints a report with a mismatch. Exit 1
means invalid input or an incomplete/unsupported header. No partial JSON is
printed for invalid input. Outputs go to stdout; the tool creates no files.

The explicit scope is the **21-field Prague header layout**, including
baseFeePerGas, withdrawalsRoot, blobGasUsed, excessBlobGas,
parentBeaconBlockRoot and requestsHash. Older layouts with missing fields are
refused. Later layouts with additional committed fields require a future
update; hashing this fixed layout does not validate such a fork. RPC body fields
such as transactions, withdrawals and size are not header fields and are not
reconstructed or validated. Field order follows the
[Ethereum execution-specs Prague Header](https://github.com/ethereum/execution-specs/blob/master/src/ethereum/forks/prague/blocks.py).

**Limits:** A matching hash establishes header self-consistency, not a trusted
chain anchor, provider honesty, consensus validity, finality, root correctness,
or authenticity of the eth_call result. A provider can fabricate a header and
its hash together. Changing the reported supply alone does not change the
header hash, and the tests explicitly demonstrate that limitation.

Sixteen new tests passed, including both real saved captures with socket
creation disabled, mutation of every committed header field, canonical quantity
and byte bounds, missing fields, RLP boundaries, Keccak known-answer vectors,
both before/after observations and CLI exit codes. The 28 relevant inherited
snapshot-seal and pinned-snapshot tests also passed unchanged:

```sh
python3 -B -m unittest discover -s line-1/tools/header-hash-check -p 'test_*.py' -v
```

Keep sibling `snapshot-seal`, `pinned-snapshot`, and `rpc-snapshot` folders and
the seal's retained example when copying this tool. `keccak.py` is vendored
ordinary source; its copy provenance is in PROVENANCE.md. No install is needed.
