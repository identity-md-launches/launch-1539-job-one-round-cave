#!/usr/bin/env python3
"""Group revalidated ERC-20 Transfer observations by mined transaction."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crosscheck = load("crosscheck_for_transaction_groups",
                  HERE.parent / "transfer-crosscheck" / "crosscheck.py")
reader = load("reader_for_transaction_groups",
              HERE.parent / "bounded-capture-reader" / "reader.py")
window = crosscheck.window
LIMITATION = (
    "Groups contain this token's observed Transfer events only, not complete "
    "transaction receipts. Missing log indexes may belong to other events. "
    "Event totals can count a routed amount more than once; they are not trade "
    "volume, prices, balances, holders or proof of activity in a specific v4 pool. "
    "Metadata consistency does not prove provider honesty, completeness or finality."
)


def units(value, decimals):
    return ("-" if value < 0 else "") + window.display_units(abs(value), decimals)


def report(capture):
    """Rebuild events, check transaction positions, then group in chain order."""
    checked = crosscheck.checked(capture)
    by_hash, by_position, last_index = {}, {}, {}
    for event in checked["transfers"]:
        tx = event["transaction_hash"]
        position = (event["block"], event["transaction_index"])
        identity = (event["block"], event["block_hash"], event["transaction_index"])
        if tx in by_hash and by_hash[tx]["identity"] != identity:
            raise window.RpcError("one transaction hash has conflicting mined positions")
        if position in by_position and by_position[position] != tx:
            raise window.RpcError("different transaction hashes occupy one mined position")
        # The inherited decoder sorts by block and block-global log index.
        prior = last_index.get(event["block"], -1)
        if event["transaction_index"] < prior:
            raise window.RpcError("transaction indexes decrease in block log order")
        last_index[event["block"]] = event["transaction_index"]
        by_position[position] = tx
        group = by_hash.setdefault(tx, {"identity": identity, "events": []})
        group["events"].append(event)

    groups = []
    for tx, group in by_hash.items():
        events = group["events"]
        flows = {}
        for event in events:
            amount = int(event["raw_value"])
            for endpoint in sorted({event["from"], event["to"]}):
                flow = flows.setdefault(endpoint, {
                    "address": endpoint, "touching_count": 0,
                    "received_raw": 0, "sent_raw": 0,
                })
                flow["touching_count"] += 1
                if endpoint == event["from"]:
                    flow["sent_raw"] += amount
                if endpoint == event["to"]:
                    flow["received_raw"] += amount
        endpoints = []
        for endpoint in sorted(flows):
            flow = flows[endpoint]
            flow["net_raw"] = flow["received_raw"] - flow["sent_raw"]
            for name in ("received", "sent", "net"):
                flow[name] = units(flow[name + "_raw"], checked["decimals"])
                flow[name + "_raw"] = str(flow[name + "_raw"])
            endpoints.append(flow)
        total = sum(int(event["raw_value"]) for event in events)
        block, block_hash, index = group["identity"]
        groups.append({
            "transaction_hash": tx, "transaction_index": index,
            "block": block, "block_hash": block_hash,
            "transfer_count": len(events),
            "log_indexes": [event["log_index"] for event in events],
            "event_total_raw": str(total),
            "event_total": units(total, checked["decimals"]),
            "endpoint_count": len(endpoints), "endpoints": endpoints,
            "transfers": events,
        })
    return {
        "kind": "erc20-transfer-transaction-groups", "schema_version": 1,
        "read_only": True, "raw_logs_revalidated": True,
        "transaction_metadata_consistent": True,
        "chain_id": checked["chain_id"], "token": capture["token"],
        "token_address": checked["token_address"], "decimals": checked["decimals"],
        "from_block": checked["from_block"], "to_block": checked["to_block"],
        "from_block_anchor": checked["from_block_anchor"],
        "to_block_anchor": checked["to_block_anchor"],
        "transfer_count": len(checked["transfers"]),
        "duplicate_log_count": capture["duplicate_count"],
        "observed_transaction_count": len(groups), "transactions": groups,
        "limitations": LIMITATION,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true", help="retained real ZTO logs, offline")
    source.add_argument("--capture", type=Path, help="public saved capture inside this workspace")
    args = parser.parse_args(argv)
    path = HERE.parent / "transfer-crosscheck" / "publicnode.json" if args.demo else args.capture
    print(json.dumps(report(reader.read_capture(path)), indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, window.RpcError) as exc:
        print("transfer-transaction-groups: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
