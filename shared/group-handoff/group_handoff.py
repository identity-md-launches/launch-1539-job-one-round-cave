#!/usr/bin/env python3
"""Carry ERC-20 transaction groups with evidence and trace handoff revisions."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import sys
import zipfile

HERE = Path(__file__).resolve().parent
MAX_BYTES = 99_000
CAPTURE = 'evidence/window.json'
REPORT = 'review/groups.json'
GRAPH = 'review/dependencies.json'


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, HERE / 'vendor' / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


groups = load('group_handoff_groups', 'transfer-transaction-groups/groups.py')
impact = load('group_handoff_impact', 'handoff-impact/impact.py')
writer, inspector = impact.WRITER, impact.INSPECT
LIMITS = inspector.Limits(archive_bytes=MAX_BYTES, payload_bytes=MAX_BYTES,
                         manifest_bytes=4096, metadata_bytes=4096, files=3)
DEPENDENCIES = {REPORT: [CAPTURE, GRAPH], CAPTURE: [], GRAPH: []}
IMPACT_GRAPH = {'format': 'handoff-impact-graph-v1', 'roots': [REPORT],
                'dependencies': DEPENDENCIES}


def canonical(value):
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')
    if len(raw) > MAX_BYTES:
        raise ValueError('JSON output exceeds 99000 bytes')
    return raw


def reject_number(value):
    raise ValueError('floating point and non-finite JSON numbers refused')


def recompute(raw):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError('capture must be bounded original bytes')
    groups.reader.check_nesting(raw)
    capture = json.loads(raw.decode('utf-8'),
                         object_pairs_hook=groups.reader.no_duplicate_object,
                         parse_float=reject_number, parse_constant=reject_number)
    return groups.report(capture)


def inspect_bytes(data, expected=None):
    """Validate an immutable archive, then recompute its groups from exact logs."""
    if type(data) is not bytes or len(data) > MAX_BYTES:
        raise ValueError('archive must be bounded bytes')
    receipt = inspector.inspect_stream(io.BytesIO(data), LIMITS, expected)
    if {item['path'] for item in receipt['files']} != set(DEPENDENCIES):
        raise ValueError('exact capture, report and dependency graph required')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = {name: archive.read(name) for name in DEPENDENCIES}
    if files[GRAPH] != canonical(IMPACT_GRAPH):
        raise ValueError('dependency graph differs from the fixed contract')
    report = recompute(files[CAPTURE])
    if files[REPORT] != canonical(report):
        raise ValueError('groups differ from the recomputed original logs')
    selected, closure = impact.DEP.select_bytes(data, [REPORT], DEPENDENCIES,
                                               expected, LIMITS)
    if selected != data:
        raise ValueError('archive is not byte reproducible')
    result = {'schema': 'erc20-group-handoff/1', 'verified': True,
              'groups_recomputed': True, 'byte_reproducible': True,
              'network_used': False, 'archive_sha256': receipt['archive_sha256'],
              'archive_bytes': len(data),
              'trusted_digest_matched': receipt['trusted_digest_matched'],
              'capture_sha256': hashlib.sha256(files[CAPTURE]).hexdigest(),
              'dependency_closure': closure, 'groups': report,
              'limitations': 'Token Transfer observations, not complete receipts, '
              'trade volume, prices, balances, finality or sender authentication. '
              'PoolManager endpoints do not identify a particular Uniswap v4 pool. '
              'Nothing is extracted or executed from an archive.'}
    canonical(result)
    return result


def build(raw):
    files = {CAPTURE: raw, REPORT: canonical(recompute(raw)),
             GRAPH: canonical(IMPACT_GRAPH)}
    if sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError('combined payload exceeds 99000 bytes')
    data = writer.build(files)
    inspect_bytes(data)
    return data


def compare_bytes(before, after, before_sha256=None, after_sha256=None):
    """Reject false reports before tracing changes through fixed dependencies."""
    left = inspect_bytes(before, before_sha256)
    right = inspect_bytes(after, after_sha256)
    result = impact.analyze_bytes(before, after, IMPACT_GRAPH, before_sha256,
                                 after_sha256, LIMITS)
    result.update(schema='erc20-group-handoff-impact/1',
                  both_group_reports_recomputed=True,
                  group_report_changed=left['groups'] != right['groups'],
                  network_used=False)
    canonical(result)
    return result


def file_parts(raw):
    path = Path(raw)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('relative workspace file without traversal required')
    return path.parts


def parent_descriptor(raw):
    parts = file_parts(raw)
    if not all(hasattr(os, name) for name in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK')):
        raise ValueError('POSIX no-follow file support required')
    directory = os.open(Path.cwd(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
    except BaseException:
        os.close(directory)
        raise
    return directory, parts[-1]


def read_workspace(raw):
    directory, name = parent_descriptor(raw)
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        with os.fdopen(descriptor, 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError('bounded regular file required')
            data = source.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('file grew past byte limit')
        return data
    finally:
        os.close(directory)


def save_new(raw, data):
    """Create one explicit output through no-follow parents; never overwrite."""
    directory, name = parent_descriptor(raw)
    try:
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o644, dir_fd=directory)
        try:
            with os.fdopen(descriptor, 'wb') as target:
                target.write(data)
        except BaseException:
            os.unlink(name, dir_fd=directory)
            raise
    finally:
        os.close(directory)


def demo():
    raw = (HERE / 'examples/zto-window.json').read_bytes()
    data = build(raw)
    if data != build(raw):
        raise ValueError('nondeterministic archive')
    result = inspect_bytes(data)
    result['unchanged_revision'] = compare_bytes(data, data)['requires_review'] is False
    result['demo'] = 'Dated real ZTO logs; no network, writes or extraction.'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('demo')
    pack = commands.add_parser('pack')
    pack.add_argument('capture')
    pack.add_argument('archive')
    check = commands.add_parser('check')
    check.add_argument('archive')
    check.add_argument('--sha256', help='independently retained archive digest')
    compare = commands.add_parser('compare')
    compare.add_argument('before')
    compare.add_argument('after')
    compare.add_argument('--before-sha256')
    compare.add_argument('--after-sha256')
    compare.add_argument('--fail-on-impact', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            result = demo()
        elif args.command == 'pack':
            # Refuse invalid destination syntax before opening selected evidence.
            file_parts(args.archive)
            data = build(read_workspace(args.capture))
            result = inspect_bytes(data)
            result['output'] = args.archive
            encoded = canonical(result)
            save_new(args.archive, data)
            sys.stdout.write(encoded.decode('ascii'))
            return 0
        elif args.command == 'check':
            result = inspect_bytes(read_workspace(args.archive), args.sha256)
        else:
            file_parts(args.before)
            file_parts(args.after)
            result = compare_bytes(read_workspace(args.before), read_workspace(args.after),
                                   args.before_sha256, args.after_sha256)
        sys.stdout.write(canonical(result).decode('ascii'))
        return 2 if (args.command == 'compare' and args.fail_on_impact
                     and result['requires_review']) else 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, UnicodeError,
            RecursionError, OverflowError, zipfile.BadZipFile, EOFError,
            NotImplementedError, struct.error):
        print('group-handoff: invalid, over-limit or inconsistent evidence; no receipt',
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
