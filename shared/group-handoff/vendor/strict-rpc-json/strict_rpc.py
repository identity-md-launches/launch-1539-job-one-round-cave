#!/usr/bin/env python3
"""Strict, bounded decoding of the window reader's single-request RPC replies."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    'capture_reader_for_rpc', HERE.parent / 'bounded-capture-reader' / 'reader.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
MAX_BYTES = reader.MAX_BYTES


def decode_reply(raw, expected_id=1, max_bytes=MAX_BYTES):
    """Return result; reject ambiguous JSON/envelopes and all RPC errors.

    A null result is valid here; the calling method validates its result type.
    This parser performs no network or filesystem reads on caller data.
    """
    if type(raw) is not bytes:
        raise ValueError('RPC reply must be bytes')
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
        raise ValueError('invalid RPC byte limit')
    if len(raw) > max_bytes:
        raise ValueError('RPC response exceeds byte limit')
    if type(expected_id) is not int:
        raise ValueError('expected RPC ID must be an integer')
    try:
        reader.check_nesting(raw)
        payload = json.loads(raw.decode('utf-8'),
                             object_pairs_hook=reader.no_duplicate_object,
                             parse_constant=reader.reject_constant,
                             parse_float=reader.finite_float)
    except (ValueError, RecursionError) as exc:
        raise ValueError('RPC response is not strict UTF-8 JSON: ' + str(exc)) from exc
    if type(payload) is not dict or payload.get('jsonrpc') != '2.0':
        raise ValueError('RPC response is not a JSON-RPC 2.0 object')
    if type(payload.get('id')) is not int or payload['id'] != expected_id:
        raise ValueError('RPC response ID does not match request')
    if ('result' in payload) == ('error' in payload):
        raise ValueError('RPC response requires exactly one of result or error')
    if 'error' in payload:
        error = payload['error']
        if (type(error) is not dict or type(error.get('code')) is not int
                or type(error.get('message')) is not str):
            raise ValueError('malformed RPC error object')
        # Do not echo arbitrary remote error data into reports.
        raise ValueError('RPC error code ' + str(error['code']))
    return payload['result']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', required=True)
    parser.parse_args(argv)
    capture = reader.read_capture(HERE.parent / 'transfer-crosscheck' / 'publicnode.json')
    # Saved capture is real evidence; this envelope is reconstructed, not a wire capture.
    envelope = json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': capture['raw_logs']}).encode()
    logs = decode_reply(envelope)
    rejected = []
    for name, raw in (
        ('duplicate key', b'{"jsonrpc":"2.0","id":1,"result":[],"result":null}'),
        ('non-finite number', b'{"jsonrpc":"2.0","id":1,"result":1e999}'),
        ('mixed result/error', b'{"jsonrpc":"2.0","id":1,"result":[],"error":{}}'),
    ):
        try:
            decode_reply(raw)
        except ValueError:
            rejected.append(name)
        else:
            raise AssertionError('invalid reply accepted: ' + name)
    print(json.dumps({'kind': 'strict-rpc-json-demo', 'token': capture['token'],
                      'retained_real_log_count': len(logs), 'rejected': rejected,
                      'network_used': False, 'max_bytes': MAX_BYTES,
                      'max_nesting': 64,
                      'limitations': 'Reconstructed envelope around dated provider evidence; not a new chain observation or completeness proof.'},
                     indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
