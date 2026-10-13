#!/usr/bin/env python3
"""Trace changed verified payloads through an explicitly declared dependency graph."""
import argparse
import hashlib
import io
import json
import struct
import sys
import zipfile
from pathlib import Path
import importlib.util


def load(name, relative):
    current = Path(__file__).resolve().parents[1]
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink():
            raise ValueError('dependency symlinks are not allowed')
    spec = importlib.util.spec_from_file_location(name, current)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


DEP = load('impact_dependencies', 'handoff-dependencies/dependencies.py')
COMPARE = load('impact_compare', 'handoff-compare/compare_handoff.py')
INSPECT, WRITER = DEP.INSPECT, DEP.WRITER
MAX_REPORT_BYTES = 99000


def normalize(document, limits):
    if (not isinstance(document, dict)
            or set(document) != {'format', 'roots', 'dependencies'}
            or document['format'] != 'handoff-impact-graph-v1'):
        raise ValueError('unsupported impact graph document')
    graph, roots, _ = DEP.normalize(document['dependencies'], document['roots'], limits)
    canonical = json.dumps({'format': document['format'], 'roots': roots,
                            'dependencies': graph}, sort_keys=True,
                           separators=(',', ':'), ensure_ascii=True).encode('ascii')
    if len(canonical) > DEP.MAX_GRAPH_BYTES:
        raise ValueError('canonical impact graph exceeds byte limit')
    return graph, roots, hashlib.sha256(canonical).hexdigest()


def parse_graph(data, limits):
    if not isinstance(data, bytes) or len(data) > DEP.MAX_GRAPH_BYTES:
        raise ValueError('graph must be a bounded byte snapshot')
    def invalid_constant(value):
        raise ValueError('nonstandard JSON constant: ' + value)
    document = json.loads(data.decode('utf-8'), object_pairs_hook=INSPECT.unique_object,
                          parse_constant=invalid_constant)
    normalize(document, limits)
    return document


def analyze_bytes(before, after, document, before_sha256=None, after_sha256=None,
                  limits=None):
    limits = limits or INSPECT.Limits()
    limits.validate()
    graph, roots, graph_hash = normalize(document, limits)
    for snapshot in (before, after):
        if not isinstance(snapshot, (bytes, bytearray)) or len(snapshot) > limits.archive_bytes:
            raise ValueError('archive must be a bounded byte snapshot')
    # Freeze both buffers before checking either; never execute archive payloads.
    before, after = bytes(before), bytes(after)
    left = INSPECT.inspect_stream(io.BytesIO(before), limits, before_sha256)
    right = INSPECT.inspect_stream(io.BytesIO(after), limits, after_sha256)
    absent = sorted(set(graph) - {item['path'] for item in left['files']})
    if absent:
        raise ValueError('graph paths absent from baseline archive: ' + repr(absent))
    comparison = COMPARE.compare_receipts(left, right)
    modified = {item['path'] for item in comparison['modified']}
    removed = {item['path'] for item in comparison['removed']}
    changed = modified | removed
    # First restrict attention to the requested baseline roots and their closure.
    closure, pending = set(), list(roots)
    while pending:
        path = pending.pop()
        if path not in closure:
            closure.add(path)
            pending.extend(graph[path])
    reverse = {path: [] for path in closure}
    for path in sorted(closure):
        for dependency in graph[path]:
            reverse[dependency].append(path)
    impacted, pending = set(), sorted(changed & closure)
    while pending:
        path = pending.pop()
        if path not in impacted:
            impacted.add(path)
            pending.extend(reverse[path])
    affected_roots = sorted(set(roots) & impacted)
    report = {
        'format': 'handoff-impact-v1', 'verified': True,
        'graph_sha256': graph_hash,
        'graph_digest_encoding': 'ASCII JSON, sorted keys and lists, compact separators, no newline',
        'graph_node_count': len(graph), 'graph_edge_count': sum(map(len, graph.values())),
        'roots': roots, 'closure_paths': sorted(closure),
        'affected_roots': affected_roots,
        'unaffected_roots': sorted(set(roots) - impacted),
        'affected_declared_paths': sorted(impacted),
        'direct_modified_paths': sorted(modified & closure),
        'missing_dependency_paths': sorted(removed & closure),
        'changed_outside_closure': sorted(changed - closure),
        'requires_review': bool(affected_roots), 'comparison': comparison,
        'note': 'Impact means a baseline root reaches a changed or removed file through caller '
                'declarations, including its own bytes. Added files and changes outside that '
                'closure do not affect these baseline roots. No new-revision dependency inference, '
                'payload execution, authorship proof or software-behavior claim is made.',
    }
    # Bound output too: enormous names must not produce an unbounded receipt.
    if len(encode(report)) > MAX_REPORT_BYTES:
        raise ValueError('impact report exceeds 99000-byte output limit')
    return report


def encode(report):
    return (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')


def analyze_paths(before, after, graph_path, before_sha256=None, after_sha256=None,
                  limits=None):
    limits = limits or INSPECT.Limits()
    limits.validate()
    # Validate all path syntax before any user input file is read.
    paths = [WRITER.workspace_path(path) for path in (before, after, graph_path)]
    document = parse_graph(WRITER.regular_bytes(paths[2], DEP.MAX_GRAPH_BYTES), limits)
    left = WRITER.regular_bytes(paths[0], limits.archive_bytes)
    right = WRITER.regular_bytes(paths[1], limits.archive_bytes)
    return analyze_bytes(left, right, document, before_sha256, after_sha256, limits)


def demo():
    original = WRITER.regular_bytes(WRITER.workspace_path('line-2/handoff.zip'),
                                   INSPECT.Limits.archive_bytes)
    receipt = INSPECT.inspect_stream(io.BytesIO(original))
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        files = {item['path']: archive.read(item['path']) for item in receipt['files']}
    files['handoff.py'] += b'\n# Proposed revision impact demonstration; not executed.\n'
    document = {'format': 'handoff-impact-graph-v1', 'roots': ['README.md'],
                'dependencies': {'README.md': ['handoff.py'], 'handoff.py': []}}
    result = analyze_bytes(original, WRITER.build(files), document)
    if result['affected_roots'] != ['README.md'] or result['direct_modified_paths'] != ['handoff.py']:
        raise ValueError('demo impact propagation failed')
    result['demo'] = 'real inherited archive versus an explicitly hypothetical in-memory code edit'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('demo')
    check = commands.add_parser('check')
    check.add_argument('before')
    check.add_argument('after')
    check.add_argument('graph')
    check.add_argument('--before-sha256')
    check.add_argument('--after-sha256')
    check.add_argument('--fail-on-impact', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = (demo() if args.command == 'demo' else analyze_paths(
            args.before, args.after, args.graph, args.before_sha256, args.after_sha256))
        sys.stdout.write(encode(result).decode('ascii'))
        return 2 if (args.command == 'check' and args.fail_on_impact
                     and result['requires_review']) else 0
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError,
            zipfile.BadZipFile, EOFError, NotImplementedError, struct.error) as error:
        print('handoff-impact: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
