#!/usr/bin/env python3
"""Read a bounded ERC-20 Transfer log window from Ethereum JSON-RPC.

This program is deliberately read-only.  It neither reads credentials nor creates,
signs, sends, or serializes a transaction.
"""

import argparse
import datetime as dt
import importlib.util
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
import urllib.parse


TOKENS = {
    "zto": "0xd782bdea4ef02a0bd391eb9089470c8080f0a68e",
    "imd": "0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7",
}
DEFAULT_RPC = "https://ethereum-rpc.publicnode.com"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DECIMALS_CALL = "0x313ce567"
USER_AGENT = "Pepeolithic-ERC20-Transfer-Window/2.0 (read-only public data)"
MAX_WINDOW = 2_000
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_LOGS = 20_000
READ_METHODS = frozenset({"eth_chainId", "eth_blockNumber", "eth_call", "eth_getLogs", "eth_getBlockByNumber"})
HEX_QUANTITY = re.compile(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]{0,63})\Z")

_rpc_spec = importlib.util.spec_from_file_location(
    'strict_json_for_transfer_window',
    Path(__file__).resolve().parent.parent / 'strict-rpc-json' / 'strict_rpc.py')
strict_rpc = importlib.util.module_from_spec(_rpc_spec)
_rpc_spec.loader.exec_module(strict_rpc)


class RpcError(RuntimeError):
    """An RPC response could not supply the requested public data."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep every public read at the endpoint the worker explicitly selected."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        raise RpcError("RPC endpoint returned an HTTP redirect; no redirect followed")


def public_opener():
    """Build a fresh transport without environment or system proxy discovery."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def rpc(endpoint, method, params):
    """Perform one JSON-RPC request, returning its result or raising RpcError."""
    if method not in READ_METHODS:
        raise RpcError("method is not an allowed public read")
    validate_endpoint(endpoint)
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with public_opener().open(request, timeout=25) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RpcError("RPC response exceeds byte limit; use a smaller window")
            result = strict_rpc.decode_reply(raw, expected_id=1, max_bytes=MAX_RESPONSE_BYTES)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RpcError("network or JSON failure: {}".format(exc)) from exc
    return result


def parse_block(value):
    """Accept a non-negative decimal or 0x-prefixed block number."""
    try:
        number = int(value, 16 if value.lower().startswith("0x") else 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("block must be decimal or 0x-prefixed") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("block must not be negative")
    if number >= 2**256:
        raise argparse.ArgumentTypeError("block must fit an unsigned 256-bit quantity")
    return number


def as_quantity(number):
    return hex(number)


def validate_endpoint(endpoint):
    try:
        parts = urllib.parse.urlsplit(endpoint)
        if (not parts.hostname or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment):
            raise ValueError("credential-free endpoint without query/fragment required")
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise ValueError("invalid port")
        public_https = parts.scheme == "https"
        local_mainnet_relay = (parts.scheme == "http" and parts.hostname == "127.0.0.1"
                               and parts.port is not None and parts.path == "/rpc/1")
        if not (public_https or local_mainnet_relay):
            raise ValueError("public HTTPS or exact 127.0.0.1:<port>/rpc/1 required")
    except ValueError as exc:
        raise RpcError("invalid RPC endpoint: {}".format(exc)) from exc


def quantity(value, name):
    if not isinstance(value, str) or HEX_QUANTITY.fullmatch(value) is None:
        raise RpcError("{} must be a canonical hex quantity".format(name))
    return int(value, 16)


def hex_bytes(value, size, name):
    if (not isinstance(value, str) or len(value) != 2 + 2 * size
            or not value.startswith("0x")
            or re.fullmatch(r"[0-9a-fA-F]+", value[2:]) is None):
        raise RpcError("{} must contain exactly {} hex bytes".format(name, size))
    return value.lower()


def topic_address(topic):
    topic = hex_bytes(topic, 32, "indexed address topic")
    if topic[2:26] != "0" * 24:
        raise RpcError("indexed address topic has nonzero ABI padding")
    return "0x" + topic[-40:]


def address(value):
    """Normalize one externally supplied Ethereum address without resolving it."""
    if not isinstance(value, str) or re.fullmatch(r"0x[0-9a-fA-F]{40}", value) is None:
        raise argparse.ArgumentTypeError("address must be exactly 0x followed by 40 hex characters")
    return value.lower()


def display_units(raw, decimals):
    """Format a nonnegative integer using a token's on-chain decimal count."""
    if decimals == 0:
        return str(raw)
    whole, fraction = divmod(raw, 10**decimals)
    if fraction == 0:
        return str(whole)
    return "{}.{}".format(str(whole), str(fraction).zfill(decimals).rstrip("0"))


def decode_log(log, decimals, token_address=TOKENS["zto"], from_block=None, to_block=None):
    """Validate one mined ERC-20 log before interpreting any of its values."""
    if not isinstance(log, dict):
        raise RpcError("Transfer log is not an object")
    if log.get("removed") is not False:
        raise RpcError("Transfer log is removed or has no explicit removed=false")
    emitter = hex_bytes(log.get("address"), 20, "log emitter")
    if emitter != token_address.lower():
        raise RpcError("Transfer log has the wrong emitter")
    topics = log.get("topics")
    if not isinstance(topics, list) or len(topics) != 3:
        raise RpcError("Transfer event requires exactly three topics")
    if hex_bytes(topics[0], 32, "event signature") != TRANSFER_TOPIC:
        raise RpcError("Transfer log has the wrong event signature")
    raw_value = int(hex_bytes(log.get("data"), 32, "Transfer uint256 data"), 16)
    block = quantity(log.get("blockNumber"), "blockNumber")
    index = quantity(log.get("logIndex"), "logIndex")
    transaction_index = quantity(log.get("transactionIndex"), "transactionIndex")
    if ((from_block is not None and block < from_block)
            or (to_block is not None and block > to_block)):
        raise RpcError("Transfer log is outside the requested inclusive range")
    return {
        "block": block,
        "block_hash": hex_bytes(log.get("blockHash"), 32, "blockHash"),
        "log_index": index,
        "transaction_index": transaction_index,
        "transaction_hash": hex_bytes(log.get("transactionHash"), 32, "transactionHash"),
        "from": topic_address(topics[1]),
        "to": topic_address(topics[2]),
        "raw_value": str(raw_value),
        "value": display_units(raw_value, decimals),
    }


def validate_logs(logs, decimals, token_address, from_block, to_block):
    if not isinstance(logs, list):
        raise RpcError("eth_getLogs result is not a list")
    if len(logs) > MAX_LOGS:
        raise RpcError("too many logs; use a smaller window (no truncation performed)")
    unique = {}
    block_hashes = {}
    slots = {}
    duplicates = 0
    for log in logs:
        item = decode_log(log, decimals, token_address, from_block, to_block)
        block, block_hash = item["block"], item["block_hash"]
        if block in block_hashes and block_hashes[block] != block_hash:
            raise RpcError("logs disagree on the hash of one block")
        block_hashes[block] = block_hash
        key = (block_hash, item["transaction_hash"], item["log_index"])
        slot = (block, item["log_index"])
        if slot in slots and slots[slot] != key:
            raise RpcError("conflicting events occupy the same block/log index")
        slots[slot] = key
        if key in unique:
            if item != unique[key]:
                raise RpcError("duplicate identity contains conflicting Transfer fields")
            duplicates += 1
        else:
            unique[key] = item
    return sorted(unique.values(), key=lambda item: (item["block"], item["log_index"])), duplicates


def address_summary(transfers, selected_address, decimals):
    """Summarize selected-window flows involving one public address.

    This is deliberately a summary of the already validated bounded log window,
    not a token balance calculation. A self-transfer counts once in each flow.
    """
    received = sent = incoming_count = outgoing_count = matched_count = 0
    for item in transfers:
        raw = int(item["raw_value"])
        if item["to"] == selected_address or item["from"] == selected_address:
            matched_count += 1
        if item["to"] == selected_address:
            received += raw
            incoming_count += 1
        if item["from"] == selected_address:
            sent += raw
            outgoing_count += 1
    net = received - sent
    return {
        "address": selected_address,
        "matching_transfer_count": matched_count,
        "incoming_transfer_count": incoming_count,
        "outgoing_transfer_count": outgoing_count,
        "received_raw": str(received),
        "received": display_units(received, decimals),
        "sent_raw": str(sent),
        "sent": display_units(sent, decimals),
        "net_raw": str(net),
        "net": display_units(net, decimals) if net >= 0 else "-" + display_units(-net, decimals),
        "scope": "Flows in this captured transfer-log window only; not a token balance or a complete activity history.",
    }


def block_anchor(endpoint, number):
    block = rpc(endpoint, "eth_getBlockByNumber", [hex(number), False])
    if not isinstance(block, dict) or quantity(block.get("number"), "anchor block number") != number:
        raise RpcError("requested anchor block is unavailable or has the wrong number")
    return {"number": number, "hash": hex_bytes(block.get("hash"), 32, "anchor block hash")}


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", choices=sorted(TOKENS), default="zto", help="token to inspect (default: zto)")
    parser.add_argument("--from-block", type=parse_block, help="first inclusive block")
    parser.add_argument("--to-block", type=parse_block, help="last inclusive block")
    parser.add_argument("--latest-window", type=int, default=12, help="latest inclusive block window when bounds are omitted (default: 12)")
    parser.add_argument("--address", type=address, help="optional public address to summarize within the captured window")
    parser.add_argument("--rpc", default=DEFAULT_RPC, help="public Ethereum JSON-RPC URL")
    args = parser.parse_args(argv)
    if (args.from_block is None) != (args.to_block is None):
        parser.error("--from-block and --to-block must be supplied together")
    if args.latest_window < 1 or args.latest_window > MAX_WINDOW:
        parser.error("--latest-window must be between 1 and {}".format(MAX_WINDOW))
    if args.from_block is not None and args.to_block < args.from_block:
        parser.error("--to-block must not precede --from-block")
    if args.from_block is not None and args.to_block - args.from_block + 1 > MAX_WINDOW:
        parser.error("the requested block range exceeds {} blocks".format(MAX_WINDOW))
    return args


def main(argv=None):
    args = arguments(argv)
    token_address = TOKENS[args.token]
    validate_endpoint(args.rpc)
    chain_id = quantity(rpc(args.rpc, "eth_chainId", []), "chain ID")
    if chain_id != 1:
        raise RpcError("Ethereum mainnet (chain ID 1) is required")
    head = quantity(rpc(args.rpc, "eth_blockNumber", []), "chain head")
    if args.from_block is None:
        to_block = head
        from_block = max(0, head - args.latest_window + 1)
    else:
        from_block, to_block = args.from_block, args.to_block
    if to_block > head:
        raise RpcError("requested range extends beyond the observed chain head")
    start_anchor = block_anchor(args.rpc, from_block)
    end_anchor = start_anchor if to_block == from_block else block_anchor(args.rpc, to_block)
    decimals_result = rpc(args.rpc, "eth_call", [{"to": token_address, "data": DECIMALS_CALL}, hex(to_block)])
    decimals = int(hex_bytes(decimals_result, 32, "decimals() ABI result"), 16)
    if decimals > 255:
        raise RpcError("token decimals() result exceeds uint8")
    filter_object = {
        "address": token_address,
        "fromBlock": as_quantity(from_block),
        "toBlock": as_quantity(to_block),
        "topics": [TRANSFER_TOPIC],
    }
    logs = rpc(args.rpc, "eth_getLogs", [filter_object])
    transfers, duplicates = validate_logs(logs, decimals, token_address, from_block, to_block)
    for anchor in (start_anchor, end_anchor):
        for item in transfers:
            if item["block"] == anchor["number"] and item["block_hash"] != anchor["hash"]:
                raise RpcError("Transfer log disagrees with a boundary block hash")
    # Re-read both boundaries after decimals/logs to detect a reorg during capture.
    if block_anchor(args.rpc, from_block) != start_anchor:
        raise RpcError("start block changed during capture; retry")
    if to_block != from_block and block_anchor(args.rpc, to_block) != end_anchor:
        raise RpcError("end block changed during capture; retry")
    output = {
        "captured_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "read_only": True,
        "schema_version": 3,
        "chain_id": chain_id,
        "from_block_anchor": start_anchor,
        "to_block_anchor": end_anchor,
        "decimals_block": to_block,
        "raw_logs": logs,
        "duplicate_count": duplicates,
        "provider_result": "validated",
        "limitations": "Single-provider observation; not a completeness or finality proof. Interior block hashes are retained but not independently verified.",
        "rpc": args.rpc,
        "token": args.token.upper(),
        "token_address": token_address,
        "decimals": decimals,
        "head_at_capture": head,
        "from_block": from_block,
        "to_block": to_block,
        "transfer_count": len(transfers),
        "transfers": transfers,
    }
    if args.address is not None:
        output["address_window_summary"] = address_summary(transfers, args.address, decimals)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RpcError as exc:
        print("transfer-window: {}".format(exc), file=sys.stderr)
        raise SystemExit(2)
