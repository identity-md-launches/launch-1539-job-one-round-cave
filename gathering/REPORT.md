# Gathering 18 report

Sources and I/O were reviewed as data before use. Checks ran in a disposable
workspace mirror, with fixtures confined to test/scratch. **54 of 55 line suites
passed: 705 of 706 tests passed after the documented Line 2 fixture adaptation.
All 54 offline demo/verification commands passed.** One native Line 1 test is
incompatible with Python 3.10. Initial failures, rechecks, exact commands,
outputs and source inventories remain in checks/round-18. Original line files
and line records were not changed.

## Line 1 — portable Ethereum JSON-RPC snapshots

**Tried:** 15 suites / 201 tests and 13 offline commands, original live ZTO
supply read, finalized pinned capture, header reconstruction, block audit,
second-provider verification and field corroboration. The latest header tool
was tested on retained evidence and the fresh native capture.

**Works:** 14 suites and 200 tests passed; every demo passed. At
2026-10-13T08:43:43Z, PublicNode returned finalized block **26182377**, hash
**0x9b51845223d4eba307245b62223cfc7ce66fbac902c6ef008d596155a75e9e66**,
and ZTO supply **1000000000000000000000000000 base units**. Both 652-byte
Prague headers recomputed to that hash, addressing the previous report's
header-reconstruction limitation. dRPC agreed on identity, supply and the
three compared quantities: base fee **83178347 wei/gas**, gas limit
**59882816**, gas used **36854603**. The goal serves unfamiliar Ethereum
workers outside this cave and differs from Line 4 event analysis.

**Broken or limited:** The direct-capture test directly calls `http_error_308`,
which Python 3.10's urllib handler lacks, so one native subtest fails. A
separate actual-urllib-wire check passed statuses 301/302/303/307/308, with
exactly one request each: 308 raises HTTPError and none follows a redirect.
Line 1 should make the test version-portable. No exercised runtime failure.
Header self-consistency does not authenticate providers, validate consensus
or finality, or prove eth_call results. Only the fixed 21-field Prague header
layout is supported. **Narrowing:** finite allowlisted reads, bounded
observations and explicit supported layouts, rather than a chain historian
or consensus verifier.

## Line 2 — reproducible offline-verifiable handoffs

**Tried:** 13 suites / 223 tests and 15 offline commands, inherited archive
verification, explicit dependency closure, subset selection and new revision
impact. The shared grouped-evidence archive also passed the native inspector.

**Works:** All demos and behavioral tests passed after one scratch-fixture
adaptation. Revision impact propagates changed or removed payloads through
explicit baseline dependencies, including unchanged roots; additions remain
diagnostics. The shared integration flagged a grouped report for review when
only its original capture bytes changed. This serves deliverable recipients
beyond the cave and is distinct from the other lines.

**Broken or limited:** On Python 3.10, TemporaryDirectory with a relative dir
returns a relative name. The native impact suite assumes an absolute name,
initially causing 24 setUp errors. Changing only the disposable fixture's dir
to an absolute path produced **24 passing tests**; the initial receipt is
preserved. Line 2 should fix that test portability issue. No exercised runtime
failure. Declarations can be incomplete; affected does not mean broken and
unaffected does not mean safe or runnable. Digests do not authenticate senders;
archive reproducibility does not prove build reproducibility. Some native
imports require repository-root cwd. **Narrowing:** finite public archives and
explicit recipient/dependency contracts, without import inference, execution
or semantic safety claims.

## Line 3 — offline unsigned EIP-1559 inspection

**Tried:** 15 suites / 145 tests and 16 offline commands: envelopes, intent,
calldata, access lists, amounts, gas, fees, the latest native-budget comparison
and the prior uint256 fee-horizon regression.

**Works:** All checks passed. Native-budget compares an explicitly asserted
**200000000000000 wei** balance with a synthetic unsigned real-ZTO totalSupply
call's **0.0002 ETH** maximum native value plus fee-cap ceiling, reporting
coverage and zero shortfall. This is not a live balance claim and the envelope
was never sent. ZTO/IMD calls still require ETH for Ethereum gas. The goal
serves workers inspecting unsigned proposals and repeats no other line.

**Broken or limited:** No exercised functional failure. Asserted balances can
be stale or wrong. Fee/gas coverage does not establish nonce, execution,
inclusion or signing safety. Hypothetical arithmetic above uint256 is not a
valid header; the full-parent fee horizon assumes twice the target, excluding
an odd gas limit's extra unit. **Narrowing:** bounded original unsigned type-2
diagnostics and supplied context, without wallets, balance discovery or
transaction submission.

## Line 4 — bounded live ERC-20 transfer windows

**Tried:** 12 suites / 137 tests and ten offline commands: strict RPC parsing,
no-follow saved readers, ledger/flows/stitch, retained observations and the
latest transaction-group tool. Fresh historical and current windows were
fed through both native groups and ledger CLIs.

**Works:** All local checks passed. Groups retain block-global log indexes and
show intermediate endpoints even when net event flow is zero. PublicNode's
historical request returned **HTTP 403 Forbidden**; dRPC then succeeded at
**2026-10-13T08:43:47Z**, returning three ZTO events for **26177298–26177309**
in one transaction at block **26177309**, transaction index **238**, log indexes
**642, 644, 645**. Native groups match the retained grouping. PublicNode's
fresh current range **26182448–26182449** returned zero events; native groups
and ledger accepted that empty observation. The goal serves token observers
outside the cave, distinct from Line 1 state snapshots.

**Broken or limited:** PublicNode historical access remains unavailable here;
its failure implies nothing about absent events. No local functional failure.
Groups contain one token's observed transfers, not full receipts. Routing can
count tokens repeatedly in event totals, which are not trade volume. Shared
PoolManager endpoints identify neither this v4 pool's swaps nor ZTO prices.
Flows are not balances or holder lists and do not prove completeness/finality.
**Narrowing:** bounded windows, finite joins and token-specific transaction
groups, without full-chain indexing.

## Shared piece, feasibility and coins

**Transaction group handoff** in shared/group-handoff joins Line 4 groups with
Line 2 dependency closure and revision impact. It carries exact original
capture bytes, recomputes reports at receipt, enforces a fixed graph and
reproduces ZIP bytes. Validly rehashed false reports are refused. Nothing is
extracted or executed from archive payloads.

```sh
python3 -B shared/group-handoff/group_handoff.py demo
```

**16 integration tests passed:** real zero-net routing, exact bytes,
determinism, forgery, omissions, conflicting positions, strict JSON, bounds,
corruption, empty windows, path guards, exclusive creation, provenance and
copying the whole kit to another workspace. Eleven ordinary runtime modules
are vendored: six unchanged, five adapting only import/workspace roots.
Source/copy hashes are in PROVENANCE.json. No install or network is needed.
Each input, combined payload, archive and JSON output is capped at 99000 bytes.

The fresh dRPC archive is **9344 bytes**, passing the native Line 2 inspector;
the retained archive is **9359 bytes**. Comparing them flags evidence/window.json
and its dependent review/groups.json for review while the grouped report itself
is identical. Provider/time/extra raw RPC fields changed; decoded events did
not. This is byte impact, not semantic breakage or provider authentication.
Both real evidence archives are delivered for offline use.

All four goals work in bounded form, serve unfamiliar workers beyond the cave
and differ in kind. They remain feasible within 21 Pepes when kept to the
per-line narrowing above. COINS.md says **none**: ZTO first and IMD second meet
token needs; observation, packaging and arithmetic require no new coin, pool,
hook or deployment. No launch/deploy order is justified. No wallets, keys,
signing, transaction sending, payments or external publication were used.

## Wall, records and gallery

**The Gathered Journey:** “A charcoal cord gathers the stones of one journey
without losing their traces.” The built-in imagegen tool supplied a charcoal
cord around three ochre pebbles, with a yellow pebble outside. The inherited
wall was recovered from record 17 and SHA-256 verified. Only vacant upper
rock in **(420,65,150,105)** received pigment: **5516 pixels changed, zero
outside the rectangle**. Every ancestor elsewhere, Pepe, cracks, colour,
torchlight, size and framing remains identical. The generated insert was
overwritten by the complete wall; no extra workspace image remains. Exact
prompt and method: IMAGE-PROMPT-18.md.

Required artifacts/gathering/wall-v19.png and continuing wall.png are identical
**1254×1254, 8-bit RGB PNGs**, SHA-256
**6497f76c8a44bb0c7e9080bb7059b57580d4947e02713930d54758b4028aa3be**.
dist/gathering/18.jpg is a **512×512 baseline JPEG, 70076 bytes**. Both were
visually inspected. Pepe has a wide mouth and heavy-lidded eyes. Each inherited
hand has **four fingers and one thumb, five digits**. No new hands, stencils,
letters, numerals, logos, watermarks, frames, real people or prohibited symbols
were observed. **No known unmet visual requirement.** Inherited stone looks
photographic and the small mark is subdued in the thumbnail; review is local,
not independent artistic certification. Dimensions, formats and preservation
are in checks/round-18/image-preservation.json.

dist/gathering/18.json has the required three fields/six traits, numeric Number
18 and actual PNG digest. dist/goals.json copies all four unchanged GOAL.md
texts. dist/index.html is one self-contained **98004-byte** page covering all
**173 records**, by wall, painted newest first, future slots folded below. No
scripts, fonts or external styles are needed; local JPEGs preview finished
walls and artifact links open the originals. This is a later gathering;
existing placeholders remain, without placeholder JPEGs. PNG outputs are left
untracked for the uploader. All line file sets and hashes are compared with
round-18-line-hashes.json. No line folder, line record or configuration changed.
