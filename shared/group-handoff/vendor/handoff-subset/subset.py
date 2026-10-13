#!/usr/bin/env python3
"""Create an independently verifiable subset of a fully verified HANDOFF v1 ZIP."""
import argparse
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


INSPECT = load('subset_inspector', 'handoff-inspect/inspect_handoff.py')
WRITER = load('subset_writer', 'handoff/handoff.py')


def select_bytes(data, paths, expected=None, limits=None):
    """Return (new ZIP bytes, provenance receipt); never extract or execute data."""
    limits = limits or INSPECT.Limits()
    limits.validate()
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError('archive snapshot must be bytes')
    if len(data) > limits.archive_bytes:
        raise ValueError('archive exceeds size limit')
    if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= limits.files:
        raise ValueError('select a nonempty bounded list of exact payload paths')
    for name in paths:
        INSPECT.safe_name(name)
        if name == INSPECT.MANIFEST:
            raise ValueError('manifest cannot be selected; a new manifest is generated')
    if len(set(paths)) != len(paths):
        raise ValueError('duplicate selected path')
    # All verification and reads describe one frozen snapshot, never a reopened path.
    data = bytes(data)
    source = INSPECT.inspect_stream(io.BytesIO(data), limits, expected)
    files = {item['path']: item for item in source['files']}
    missing = sorted(set(paths) - set(files))
    if missing:
        raise ValueError('selected paths absent from verified archive: ' + repr(missing))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        selected = {name: archive.read(name) for name in sorted(paths)}
    result = WRITER.build(selected)
    target = INSPECT.inspect_stream(io.BytesIO(result), limits)
    retained = [files[name] for name in sorted(paths)]
    if target['files'] != retained:
        raise ValueError('subset payload differs from verified source')
    return result, {
        'format': 'handoff-subset-v1', 'verified': True,
        'source_archive_sha256': source['archive_sha256'],
        'source_archive_bytes': source['archive_bytes'],
        'source_file_count': source['file_count'],
        'source_trusted_digest_matched': source['trusted_digest_matched'],
        'subset_archive_sha256': target['archive_sha256'],
        'subset_archive_bytes': target['archive_bytes'],
        'file_count': target['file_count'], 'payload_bytes': target['payload_bytes'],
        'selected_files': retained,
        'omitted_paths': sorted(set(files) - set(paths)),
        'note': 'All source payloads were verified, including omitted files. '
                'Selection uses exact paths, without renaming or dependency inference. '
                'The new ZIP has its own manifest and digest. This receipt does not '
                'authenticate a sender or prove that a subset is runnable or safe.',
    }


def select_path(archive, paths, expected=None, limits=None):
    limits = limits or INSPECT.Limits()
    limits.validate()
    data = WRITER.regular_bytes(WRITER.workspace_path(archive), limits.archive_bytes)
    return select_bytes(data, paths, expected, limits)


def save_new(raw, data):
    """Write a new workspace file only; refuse existing files and symlinks."""
    output = WRITER.workspace_path(raw, must_exist=False)
    # Parent directories must already exist. No extraction or directory creation.
    with output.open('xb') as handle:
        try:
            handle.write(data)
        except BaseException:
            output.unlink()
            raise


def demo():
    first, receipt = select_path('line-2/handoff.zip', ['README.md'])
    second, _ = select_path('line-2/handoff.zip', ['README.md'])
    if first != second:
        raise ValueError('subset did not reproduce')
    receipt['demo'] = 'actual inherited README selected; reproducible; no files written'
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('demo')
    select = commands.add_parser('select')
    select.add_argument('archive', help='relative workspace archive path')
    select.add_argument('--file', action='append', required=True, dest='paths',
                        help='exact payload path; repeat for each selected file')
    select.add_argument('--sha256', help='independently retained source archive digest')
    select.add_argument('--output', help='optional new workspace ZIP; never overwritten')
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
            limits = INSPECT.Limits(archive_bytes=args.max_archive_bytes,
                                   payload_bytes=args.max_payload_bytes, files=args.max_files)
            data, receipt = select_path(args.archive, args.paths, args.sha256, limits)
            if args.output is not None:
                save_new(args.output, data)
                receipt['output'] = args.output
        print(json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=True))
        return 0
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError,
            zipfile.BadZipFile, EOFError, NotImplementedError, struct.error) as error:
        print('handoff-subset: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
