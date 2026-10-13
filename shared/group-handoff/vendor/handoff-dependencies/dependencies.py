#!/usr/bin/env python3
"""Select a verified handoff's transitive, explicitly declared file dependencies."""
import argparse
import hashlib
import io
import json
import struct
import sys
import zipfile
from pathlib import Path
import importlib.util


def load():
    path = Path(__file__).resolve().parents[1]
    for part in Path('handoff-subset/subset.py').parts:
        path /= part
        if path.is_symlink():
            raise ValueError('dependency symlinks are not allowed')
    spec = importlib.util.spec_from_file_location('dependencies_subset', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUBSET = load()
INSPECT = SUBSET.INSPECT
WRITER = SUBSET.WRITER
MAX_EDGES = 10000
MAX_NAME_BYTES = 1024
MAX_GRAPH_BYTES = 512 * 1024


def name(raw):
    INSPECT.safe_name(raw)
    if raw == INSPECT.MANIFEST:
        raise ValueError('HANDOFF.json is reserved')
    if len(raw.encode('utf-8')) > MAX_NAME_BYTES:
        raise ValueError('dependency path exceeds UTF-8 byte limit')
    return raw


def normalize(graph, roots, limits):
    """Require complete declarations, including explicit [] for every leaf."""
    if not isinstance(graph, dict) or not 1 <= len(graph) <= limits.files:
        raise ValueError('dependency graph must be a nonempty bounded object')
    if not isinstance(roots, (list, tuple)) or not 1 <= len(roots) <= limits.files:
        raise ValueError('select a nonempty bounded list of roots')
    roots = list(roots)
    for root in roots:
        name(root)
    if len(set(roots)) != len(roots):
        raise ValueError('duplicate root')
    normalized = {}
    edges = 0
    for path, requires in graph.items():
        name(path)
        if not isinstance(requires, (list, tuple)):
            raise ValueError('each dependency list must be a list or tuple')
        edges += len(requires)
        if edges > MAX_EDGES:
            raise ValueError('dependency graph exceeds edge limit')
        for required in requires:
            name(required)
        if len(set(requires)) != len(requires):
            raise ValueError('duplicate dependency for ' + repr(path))
        normalized[path] = sorted(requires)
    normalized = dict(sorted(normalized.items()))
    undeclared = sorted((set(roots) | {p for deps in normalized.values() for p in deps})
                        - set(normalized))
    if undeclared:
        raise ValueError('undeclared paths (declare leaves explicitly): ' + repr(undeclared))
    canonical = json.dumps(normalized, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=True).encode('ascii')
    if len(canonical) > MAX_GRAPH_BYTES:
        raise ValueError('canonical graph exceeds byte limit')
    return normalized, sorted(roots), canonical


def select_bytes(data, roots, graph, expected=None, limits=None):
    limits = limits or INSPECT.Limits()
    limits.validate()
    graph, roots, canonical = normalize(graph, roots, limits)
    if not isinstance(data, (bytes, bytearray)) or len(data) > limits.archive_bytes:
        raise ValueError('archive must be a bounded byte snapshot')
    data = bytes(data)
    source = INSPECT.inspect_stream(io.BytesIO(data), limits, expected)
    available = {entry['path'] for entry in source['files']}
    missing = sorted(set(graph) - available)
    if missing:
        raise ValueError('declared graph paths absent from verified archive: ' + repr(missing))
    # Iterative traversal terminates for cycles, self-edges, and deep graphs.
    selected, pending = set(), list(roots)
    while pending:
        path = pending.pop()
        if path not in selected:
            selected.add(path)
            pending.extend(graph[path])
    output, subset = SUBSET.select_bytes(data, sorted(selected), expected, limits)
    receipt = {
        'format': 'handoff-dependencies-v1',
        'roots': roots, 'added_dependency_paths': sorted(selected - set(roots)),
        'unselected_declared_paths': sorted(set(graph) - selected),
        'graph': graph, 'graph_sha256': hashlib.sha256(canonical).hexdigest(),
        'graph_digest_encoding': 'ASCII JSON, sorted keys/lists, compact separators, no newline',
        'graph_node_count': len(graph), 'graph_edge_count': sum(map(len, graph.values())),
        'subset': subset,
        'note': 'Dependencies are caller declarations, never inferred or executed. '
                'All source payloads are verified. Complete graph closure does not prove '
                'the declarations are correct, software is runnable, or a sender is authentic.',
    }
    return output, receipt


def select_path(archive, roots, graph, expected=None, limits=None):
    limits = limits or INSPECT.Limits()
    limits.validate()
    normalize(graph, roots, limits)  # Reject bad declarations before reading the archive.
    data = WRITER.regular_bytes(WRITER.workspace_path(archive), limits.archive_bytes)
    return select_bytes(data, roots, graph, expected, limits)


def declarations(edges, leaves):
    graph = {}
    for leaf in leaves:
        name(leaf)
        if leaf in graph:
            raise ValueError('duplicate leaf')
        graph[leaf] = []
    leaf_set = set(graph)
    if len(edges) > MAX_EDGES:
        raise ValueError('dependency graph exceeds edge limit')
    for path, required in edges:
        name(path)
        name(required)
        if path in leaf_set:
            raise ValueError('a leaf cannot also declare dependencies')
        graph.setdefault(path, []).append(required)
    return graph


def demo():
    # The inherited README describes use of handoff.py: preserve both together.
    graph = {'README.md': ['handoff.py'], 'handoff.py': []}
    output, receipt = select_path('line-2/handoff.zip', ['README.md'], graph)
    again, _ = select_path('line-2/handoff.zip', ['README.md'], graph)
    if output != again:
        raise ValueError('dependency selection did not reproduce')
    receipt['demo'] = 'real inherited README plus its explicitly declared handoff.py; no writes'
    receipt['reproduced'] = True
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('demo')
    select = commands.add_parser('select')
    select.add_argument('archive')
    select.add_argument('--file', required=True, action='append', dest='roots')
    select.add_argument('--requires', nargs=2, action='append', default=[],
                        metavar=('PATH', 'DEPENDENCY'))
    select.add_argument('--leaf', action='append', default=[],
                        help='declare a file with no dependencies')
    select.add_argument('--sha256', help='independently retained source archive digest')
    select.add_argument('--output', help='optional new ZIP; parent must already exist')
    select.add_argument('--max-archive-bytes', type=INSPECT.positive,
                        default=INSPECT.Limits.archive_bytes)
    select.add_argument('--max-payload-bytes', type=INSPECT.positive,
                        default=INSPECT.Limits.payload_bytes)
    select.add_argument('--max-files', type=INSPECT.positive, default=INSPECT.Limits.files)
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            receipt = demo()
        else:
            if args.output is not None:
                WRITER.workspace_path(args.output, must_exist=False)
            graph = declarations(args.requires, args.leaf)
            limits = INSPECT.Limits(archive_bytes=args.max_archive_bytes,
                                   payload_bytes=args.max_payload_bytes, files=args.max_files)
            output, receipt = select_path(args.archive, args.roots, graph, args.sha256, limits)
            if args.output is not None:
                SUBSET.save_new(args.output, output)
                receipt['output'] = args.output
        print(json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=True))
        return 0
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError,
            zipfile.BadZipFile, EOFError, NotImplementedError, struct.error) as error:
        print('handoff-dependencies: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
