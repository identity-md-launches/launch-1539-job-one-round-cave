#!/usr/bin/env python3
"""Recompute Prague-layout Ethereum headers in saved pinned ZTO snapshots offline."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

from keccak import keccak256

TOOLS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('header_snapshot_seal',
                                            TOOLS / 'snapshot-seal/snapshot_seal.py')
seal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seal)

# Execution-specs Prague Header order. None denotes a canonical uint256 quantity;
# -1 denotes extraData (at most 32 bytes). Other values are exact byte lengths.
FIELDS = (
    ('parentHash', 32), ('sha3Uncles', 32), ('miner', 20),
    ('stateRoot', 32), ('transactionsRoot', 32), ('receiptsRoot', 32),
    ('logsBloom', 256), ('difficulty', None), ('number', None),
    ('gasLimit', None), ('gasUsed', None), ('timestamp', None),
    ('extraData', -1), ('mixHash', 32), ('nonce', 8),
    ('baseFeePerGas', None), ('withdrawalsRoot', 32),
    ('blobGasUsed', None), ('excessBlobGas', None),
    ('parentBeaconBlockRoot', 32), ('requestsHash', 32),
)


def rlp_bytes(data):
    if len(data) == 1 and data[0] < 128:
        return data
    if len(data) <= 55:
        return bytes([128 + len(data)]) + data
    size = len(data).to_bytes((len(data).bit_length() + 7) // 8, 'big')
    return bytes([183 + len(size)]) + size + data


def encode_header(block):
    if not isinstance(block, dict):
        raise ValueError('header must be an object')
    values = []
    for field, length in FIELDS:
        value = block.get(field)
        if length is None:
            if (not isinstance(value, str) or len(value) > 66 or
                    not re.fullmatch(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)', value)):
                raise ValueError('invalid header quantity: ' + field)
            number = int(value, 16)
            data = number.to_bytes((number.bit_length() + 7) // 8, 'big')
        else:
            maximum = 32 if length == -1 else length
            if (not isinstance(value, str) or len(value) > 2 + maximum * 2 or
                    not seal.pinned.rpc.hex_data(value, None if length == -1 else length)):
                raise ValueError('missing or invalid header bytes: ' + field)
            data = bytes.fromhex(value[2:])
        values.append(rlp_bytes(data))
    payload = b''.join(values)
    size = len(payload).to_bytes((len(payload).bit_length() + 7) // 8, 'big')
    # These 21 fields always exceed 55 bytes.
    return bytes([247 + len(size)]) + size + payload


def check_header(block):
    reported = block.get('hash') if isinstance(block, dict) else None
    if not seal.pinned.rpc.hex_data(reported, 32):
        raise ValueError('missing or malformed reported hash')
    encoded = encode_header(block)
    computed = '0x' + keccak256(encoded).hex()
    return {'block_number': str(int(block['number'], 16)),
            'reported_hash': reported, 'computed_hash': computed,
            'matches': computed.lower() == reported.lower(),
            'rlp_bytes': len(encoded), 'header_field_count': len(FIELDS)}


def report(path):
    raw, snapshot, facts = seal.load_snapshot(path)
    checks = [dict(observation=name, **check_header(snapshot[name]))
              for name in ('block', 'block_after')]
    return {'schema': 'pinned-zto-header-hash-check/1',
            'snapshot_sha256': hashlib.sha256(raw).hexdigest(),
            'header_layout': 'Prague (21 fields)',
            'all_header_hashes_match': all(item['matches'] for item in checks),
            'headers': checks,
            'token': facts['token'],
            'reported_total_supply_base_units': facts['total_supply_base_units'],
            'evidence_limits': ('Header self-consistency only. No trusted hash anchor, '
                                'consensus/finality validation, transaction or receipt '
                                'root reconstruction, or proof of the eth_call result. '
                                'The reported ZTO supply remains provider evidence.')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('demo', help='offline retained real Ethereum observation')
    check = sub.add_parser('check')
    check.add_argument('snapshot', help='workspace pinned-zto-snapshot/1 JSON file')
    args = parser.parse_args()
    path = TOOLS / 'snapshot-seal/current-zto.json' if args.command == 'demo' else args.snapshot
    try:
        result = report(path)
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, RuntimeError, RecursionError):
        print('header-hash-check: invalid snapshot or unsupported/incomplete header', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['all_header_hashes_match'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
