#!/usr/bin/env python3
"""Compare fully verified v1 handoffs offline; never extract or run payloads."""
import argparse
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import zipfile


def load_workspace_module(name, relative):
    # Only these fixed, inherited workspace sources are imported, never ZIP code.
    path = Path(relative)
    current = Path(__file__).resolve().parents[1]
    for component in path.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError('dependency symlinks are not allowed')
    spec = importlib.util.spec_from_file_location(name, current)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def inspector():
    return load_workspace_module('handoff_compare_inspector',
                                 'handoff-inspect/inspect_handoff.py')


def compare_receipts(before, after):
    """Internal: accept only receipts from completed inspector calls."""
    left = {item['path']: item for item in before['files']}
    right = {item['path']: item for item in after['files']}
    added = [right[p] for p in sorted(right.keys() - left.keys())]
    removed = [left[p] for p in sorted(left.keys() - right.keys())]
    modified, unchanged = [], []
    for path in sorted(left.keys() & right.keys()):
        if left[path] == right[path]:
            unchanged.append(path)
        else:
            modified.append({'path': path,
                             'before': {k: left[path][k] for k in ('bytes', 'sha256')},
                             'after': {k: right[path][k] for k in ('bytes', 'sha256')}})
    same = not (added or removed or modified)
    def summary(receipt):
        return {key: receipt[key] for key in ('archive_sha256', 'archive_bytes',
                'file_count', 'payload_bytes', 'trusted_digest_matched')}
    return {'format': 'handoff-comparison-v1', 'verified': True,
            'before': summary(before), 'after': summary(after),
            'same_payload': same,
            'same_archive': before['archive_sha256'] == after['archive_sha256'],
            'payload_byte_delta': after['payload_bytes'] - before['payload_bytes'],
            'counts': {'added': len(added), 'removed': len(removed),
                       'modified': len(modified), 'unchanged': len(unchanged)},
            'added': added, 'removed': removed, 'modified': modified,
            'unchanged': unchanged,
            'note': 'Integrity is not authenticity without independently trusted archive hashes. '
                    'Renames are reported as removal plus addition; payload code is never executed.'}


def compare_paths(before, after, before_sha256=None, after_sha256=None, limits=None):
    check = inspector()
    # Nothing is printed unless BOTH archives pass full verification.
    first = check.inspect_path(before, limits, before_sha256)
    second = check.inspect_path(after, limits, after_sha256)
    return compare_receipts(first, second)


def demo():
    check = inspector()
    producer = load_workspace_module('handoff_compare_producer',
                                    'handoff/handoff.py')
    before = check.inspect_path('line-2/handoff.zip')
    # Use the real inherited payload as the base, with a clearly labeled
    # in-memory proposed addition. No modified archive is written or executed.
    with zipfile.ZipFile('line-2/handoff.zip') as archive:
        files = {item['path']: archive.read(item['path']) for item in before['files']}
    files['PROPOSED-HANDOFF-NOTE.md'] = b'Proposed offline handoff comparison demo.\n'
    proposed = producer.build(files)
    after = check.inspect_stream(io.BytesIO(proposed))
    result = compare_receipts(before, after)
    assert result['counts'] == {'added': 1, 'removed': 0, 'modified': 0,
                                'unchanged': before['file_count']}
    result['demo'] = 'real inherited bundle versus an in-memory proposed note addition'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('demo')
    diff = commands.add_parser('compare')
    diff.add_argument('before')
    diff.add_argument('after')
    diff.add_argument('--before-sha256')
    diff.add_argument('--after-sha256')
    diff.add_argument('--fail-on-change', action='store_true',
                      help='exit 2 when verified payloads differ (default success)')
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            result = demo()
        else:
            result = compare_paths(args.before, args.after,
                                   args.before_sha256, args.after_sha256)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 2 if (args.command == 'compare' and args.fail_on_change
                     and not result['same_payload']) else 0
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError,
            zipfile.BadZipFile, EOFError, NotImplementedError, struct.error) as error:
        print('handoff-compare: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
