#!/usr/bin/env python3
"""Compare two independently captured, bounded Ethereum ERC-20 windows."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "transfer_window", HERE.parent / "erc20-transfer-window" / "transfer_window.py")
window = importlib.util.module_from_spec(spec)
spec.loader.exec_module(window)
LIMITATION = ("Agreement corroborates two provider observations; it does not prove "
              "completeness, provider independence, finality, or current balances.")


def same_transfers(actual, expected):
    """Match the decoded flat event schema, including exact JSON value types.

    validate_logs bounds the expected event count and emits only scalar fields.
    Check that fixed structure directly; never recurse into untrusted values.
    """
    return (type(actual) is list and len(actual) == len(expected)
            and all(type(got) is dict and got.keys() == want.keys()
                    and all(type(got[key]) is type(value) and got[key] == value
                            for key, value in want.items())
                    for got, want in zip(actual, expected)))


def checked(capture):
    """Rebuild transfers from raw evidence before trusting a saved summary."""
    if not isinstance(capture, dict):
        raise window.RpcError("capture must be an object")
    if (type(capture.get("schema_version")) is not int or capture["schema_version"] not in (2, 3)
            or type(capture.get("chain_id")) is not int or capture["chain_id"] != 1
            or capture.get("read_only") is not True
            or capture.get("provider_result") != "validated"):
        raise window.RpcError("validated read-only schema 2 or 3 mainnet capture required")
    if not isinstance(capture.get("rpc"), str):
        raise window.RpcError("capture RPC URL must be a string")
    window.validate_endpoint(capture["rpc"])
    for key in ("from_block", "to_block", "head_at_capture", "decimals", "decimals_block",
                "transfer_count", "duplicate_count"):
        if type(capture.get(key)) is not int or not 0 <= capture[key] < 2**256:
            raise window.RpcError("invalid capture integer: " + key)
    start, end = capture["from_block"], capture["to_block"]
    if not start <= end <= capture["head_at_capture"] or end-start+1 > window.MAX_WINDOW:
        raise window.RpcError("invalid bounded capture range")
    if capture["decimals"] > 255 or capture["decimals_block"] != end:
        raise window.RpcError("invalid pinned decimals")
    symbol = capture.get("token")
    if symbol not in ("ZTO", "IMD") or capture.get("token_address") != window.TOKENS[symbol.lower()]:
        raise window.RpcError("unsupported or inconsistent token identity")
    anchors = []
    for key, number in (("from_block_anchor", start), ("to_block_anchor", end)):
        anchor = capture.get(key)
        if (not isinstance(anchor, dict) or type(anchor.get("number")) is not int
                or anchor["number"] != number):
            raise window.RpcError("invalid boundary anchor: " + key)
        anchors.append({"number": number,
                        "hash": window.hex_bytes(anchor.get("hash"), 32, key)})
    if start == end and anchors[0] != anchors[1]:
        raise window.RpcError("single-block anchors disagree")
    events, duplicates = window.validate_logs(capture.get("raw_logs"), capture["decimals"],
                                             capture["token_address"], start, end)
    for event in events:
        for anchor in anchors:
            if event["block"] == anchor["number"] and event["block_hash"] != anchor["hash"]:
                raise window.RpcError("event disagrees with boundary anchor")
    if (not same_transfers(capture.get("transfers"), events)
            or capture["transfer_count"] != len(events)
            or capture["duplicate_count"] != duplicates):
        raise window.RpcError("capture summary disagrees with raw evidence")
    if "address_window_summary" in capture:
        if capture["schema_version"] != 3:
            raise window.RpcError("address summary requires schema 3")
        summary = capture["address_window_summary"]
        if not isinstance(summary, dict):
            raise window.RpcError("address summary must be an object")
        try:
            selected = window.address(summary.get("address"))
        except argparse.ArgumentTypeError as exc:
            raise window.RpcError("invalid address summary address") from exc
        expected = window.address_summary(events, selected, capture["decimals"])
        # Compare types too: Python considers True == 1 and 1.0 == 1.
        if (summary.keys() != expected.keys()
                or any(type(summary[key]) is not type(value) or summary[key] != value
                       for key, value in expected.items())):
            raise window.RpcError("address summary disagrees with raw evidence")
    return {"chain_id": 1, "token_address": capture["token_address"],
            "from_block": start, "to_block": end, "decimals": capture["decimals"],
            "from_block_anchor": anchors[0], "to_block_anchor": anchors[1],
            "transfers": events}


def compare(left, right):
    a, b = checked(left), checked(right)
    if left["rpc"].rstrip("/").lower() == right["rpc"].rstrip("/").lower():
        raise window.RpcError("two different provider URLs required")
    metadata = [key for key in a if key != "transfers" and a[key] != b[key]]
    # A same-slot content change is explicitly reported as a conflicting event.
    def slots(events):
        return {(event["block"], event["log_index"]): event for event in events}
    la, rb = slots(a["transfers"]), slots(b["transfers"])
    only_left = [la[key] for key in sorted(la.keys() - rb.keys())]
    only_right = [rb[key] for key in sorted(rb.keys() - la.keys())]
    conflicts = [{"left": la[key], "right": rb[key]}
                 for key in sorted(la.keys() & rb.keys()) if la[key] != rb[key]]
    agreement = not (metadata or only_left or only_right or conflicts)
    return {"schema_version": 1, "status": "agreement" if agreement else "disagreement",
            "read_only": True, "providers": [left["rpc"], right["rpc"]],
            "token": left["token"], "from_block": a["from_block"], "to_block": a["to_block"],
            "transfer_counts": [len(la), len(rb)], "metadata_differences": metadata,
            "only_left": only_left, "only_right": only_right, "conflicts": conflicts,
            "limitations": LIMITATION}


def capture(endpoint, token, start, end):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        window.main(["--rpc", endpoint, "--token", token,
                     "--from-block", str(start), "--to-block", str(end)])
    return json.loads(output.getvalue())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="compare retained real ZTO observations offline")
    parser.add_argument("--token", choices=sorted(window.TOKENS), default="zto")
    parser.add_argument("--blocks", type=int, default=12)
    parser.add_argument("--confirmations", type=int, default=12,
                        help="distance below the first provider head; not a finality claim")
    parser.add_argument("--from-block", type=window.parse_block)
    parser.add_argument("--to-block", type=window.parse_block)
    parser.add_argument("--left-rpc", default=window.DEFAULT_RPC)
    parser.add_argument("--right-rpc", default="https://eth.drpc.org")
    args = parser.parse_args(argv)
    if not 1 <= args.blocks <= window.MAX_WINDOW or not 0 <= args.confirmations < 2**256:
        parser.error("blocks must be 1..2000 and confirmations a nonnegative uint256")
    if (args.from_block is None) != (args.to_block is None):
        parser.error("supply both block bounds")
    if args.from_block is not None and not 0 <= args.to_block-args.from_block < window.MAX_WINDOW:
        parser.error("range must contain 1..2000 blocks")
    if args.demo:
        if args.from_block is not None:
            parser.error("demo uses its retained range; omit block bounds")
        left, right = [json.loads((HERE / name).read_text())
                       for name in ("publicnode.json", "drpc.json")]
    else:
        for endpoint in (args.left_rpc, args.right_rpc):
            window.validate_endpoint(endpoint)
        if args.left_rpc.rstrip("/").lower() == args.right_rpc.rstrip("/").lower():
            parser.error("two different provider URLs required")
        start, end = args.from_block, args.to_block
        if start is None:
            chain = window.quantity(window.rpc(args.left_rpc, "eth_chainId", []), "chain ID")
            if chain != 1:
                raise window.RpcError("Ethereum mainnet required")
            head = window.quantity(window.rpc(args.left_rpc, "eth_blockNumber", []), "head")
            if args.confirmations > head:
                raise window.RpcError("confirmation distance exceeds observed head")
            end = head - args.confirmations
            start = max(0, end - args.blocks + 1)
        left = capture(args.left_rpc, args.token, start, end)
        right = capture(args.right_rpc, args.token, start, end)
    result = compare(left, right)
    result["evidence"] = {"left": left, "right": right}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "agreement" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (window.RpcError, ValueError, OSError) as exc:
        print("transfer-crosscheck: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
