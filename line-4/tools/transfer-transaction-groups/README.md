# Transfer transaction groups

See which observed ERC-20 transfers belong to the same mined transaction, in
chain order. Each group retains the individual events and block-global log
indexes, and gives exact received, sent and net event flows for its endpoints.
An intermediate endpoint that receives and forwards an amount is visible even
when its net is zero. This is Python using only the standard library.

From the repository root, this command works offline with retained real ZTO
evidence, without installation:

```sh
python3 -B line-4/tools/transfer-transaction-groups/groups.py --demo
```

Tried on 2026-10-13: blocks 26177298–26177309 yielded **three ZTO transfers in
one transaction**, at block 26177309, transaction index 238, log indexes
642, 644 and 645. Four event endpoints appear. The intermediate endpoint
`0x8f10b468b06c6fd214b65f87778827f7d113f996` receives and forwards
133156.484573036068537766 ZTO in these logs, with zero net event flow.
This is a summary of observed events, not a claim about its balance.

A fresh historical read at **2026-10-13T08:34:03Z**, through the machine's
provided Ethereum relay and attributed to the brief's public source
https://ethereum-rpc.publicnode.com, returned the same three events. Its raw
evidence is retained in `live-zto.json`. Inspect that saved read offline:

```sh
python3 -B line-4/tools/transfer-transaction-groups/groups.py --capture line-4/tools/transfer-transaction-groups/live-zto.json
```

Use `--capture your-window.json` for a public capture from the line's existing
transfer-window reader. ZTO is the demonstration token; valid IMD observations
are also accepted. All raw logs and decoded summaries are first checked by the
existing validator. The added checks reject a transaction hash with different
mined positions, two transaction hashes in one block/transaction-index slot,
and transaction indexes decreasing in block-global log order. A transaction
index may restart in a later block. Duplicate raw logs are validated and counted
once. Input order does not change the grouping.

Amounts use integers and exact decimal strings. The group event total is a sum
of emitted amounts, so routing the same tokens through several endpoints can
count them repeatedly. It is **not trade volume**. These token-only groups are
not complete receipts: gaps between log indexes can contain other events.
Transfers involving the shared Uniswap v4 PoolManager do not identify a
particular pool or its swaps, nor establish ZTO's price. Groups do not establish
complete history, provider honesty, finality, holders or balances. All event
endpoints are retained; their net flows sum to zero by construction, which is
not evidence that the capture is complete.

The shared no-follow reader accepts only regular workspace files, rejects
symlinks and traversal, caps inputs at 16 MiB, and rejects duplicate JSON keys,
non-finite numbers, invalid UTF-8 and nesting above 64 levels. The inherited
validator caps ranges at 2,000 blocks and raw log lists at 20,000 entries.
Invalid inputs exit 2 without producing a report. Saved-capture analysis
performs no network access and reads no environment, key, wallet or secret.
It neither signs nor submits transactions.

Keep these sibling runtime folders when copying the tool: `transfer-crosscheck`,
`erc20-transfer-window`, `strict-rpc-json` and `bounded-capture-reader`.
All dependencies are ordinary files already in this repository.

```sh
python3 -B line-4/tools/transfer-transaction-groups/test_groups.py
```

All **15 tests passed**: the real ZTO group and intermediate endpoint, empty
captures, duplicates and raw ordering, contradictory positions, cross-block
identity, monotonic ordering, multiple transactions, per-block index restart,
self-transfers and zero values, uint256 amount arithmetic, IMD/zero-decimal
formatting, forged decoded summaries, removed logs, offline CLI and workspace
path boundaries. Mutated test examples are rejection/arithmetic fixtures, not
chain observations. Filesystem fixtures live only in `test/scratch/`.
