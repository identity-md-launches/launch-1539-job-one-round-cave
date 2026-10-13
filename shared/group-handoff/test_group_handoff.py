#!/usr/bin/env python3
"""Behavioral checks; public fixtures live only under test/scratch."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import group_handoff as kit


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (kit.HERE / 'examples/zto-window.json').read_bytes()
        cls.capture = json.loads(cls.raw)
        cls.archive = kit.build(cls.raw)

    def setUp(self):
        Path('test/scratch').mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=str(Path.cwd() / 'test/scratch'))
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).relative_to(Path.cwd())

    def files(self, data=None):
        with zipfile.ZipFile(io.BytesIO(data or self.archive)) as archive:
            return {name: archive.read(name) for name in kit.DEPENDENCIES}

    def test_real_groups_and_zero_net_router(self):
        result = kit.inspect_bytes(self.archive)
        report = result['groups']
        self.assertEqual(report['token'], 'ZTO')
        self.assertEqual(report['transfer_count'], 3)
        self.assertEqual(report['observed_transaction_count'], 1)
        tx = report['transactions'][0]
        self.assertEqual(tx['log_indexes'], [642, 644, 645])
        router = next(row for row in tx['endpoints'] if row['address'] ==
                      '0x8f10b468b06c6fd214b65f87778827f7d113f996')
        self.assertEqual(router['net_raw'], '0')
        self.assertNotEqual(router['received_raw'], '0')
        self.assertEqual(router['received_raw'], router['sent_raw'])

    def test_exact_bytes_and_reproducibility(self):
        self.assertEqual(self.files()[kit.CAPTURE], self.raw)
        self.assertEqual(self.archive, kit.build(self.raw))
        self.assertEqual(self.archive, kit.writer.build(self.files()))

    def test_offline_demo(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('network')):
            result = kit.demo()
        self.assertTrue(result['unchanged_revision'])
        self.assertFalse(result['network_used'])

    def test_forged_report_with_valid_manifest_refused(self):
        files = self.files()
        report = json.loads(files[kit.REPORT])
        report['transactions'][0]['endpoints'][0]['net_raw'] = '99'
        files[kit.REPORT] = kit.canonical(report)
        forged = kit.writer.build(files)
        kit.inspector.inspect_stream(io.BytesIO(forged), kit.LIMITS)
        with self.assertRaises(ValueError):
            kit.inspect_bytes(forged)
        with self.assertRaises(ValueError):
            kit.compare_bytes(self.archive, forged)

    def test_graph_omission_and_extra_payloads_refused(self):
        files = self.files()
        graph = copy.deepcopy(kit.IMPACT_GRAPH)
        graph['dependencies'][kit.REPORT].remove(kit.CAPTURE)
        files[kit.GRAPH] = kit.canonical(graph)
        with self.assertRaises(ValueError):
            kit.inspect_bytes(kit.writer.build(files))
        for omitted in kit.DEPENDENCIES:
            files = self.files(); del files[omitted]
            with self.assertRaises(ValueError):
                kit.inspect_bytes(kit.writer.build(files))
        files = self.files(); files['extra.py'] = b'raise RuntimeError()'
        with self.assertRaises(ValueError):
            kit.inspect_bytes(kit.writer.build(files))

    def test_false_decoded_capture_refused(self):
        capture = copy.deepcopy(self.capture)
        capture['transfers'][0]['raw_value'] = '1'
        with self.assertRaises(kit.groups.window.RpcError):
            kit.build(kit.canonical(capture))

    def test_transaction_position_conflict_refused(self):
        capture = copy.deepcopy(self.capture)
        capture['raw_logs'][1]['transactionIndex'] = '0xef'
        capture['transfers'], capture['duplicate_count'] = kit.groups.window.validate_logs(
            capture['raw_logs'], capture['decimals'], capture['token_address'],
            capture['from_block'], capture['to_block'])
        with self.assertRaises(kit.groups.window.RpcError):
            kit.build(kit.canonical(capture))

    def test_source_byte_revision_impacts_unchanged_report(self):
        after = kit.build(self.raw + b' \n')
        result = kit.compare_bytes(self.archive, after)
        self.assertFalse(result['group_report_changed'])
        self.assertTrue(result['requires_review'])
        self.assertEqual(result['direct_modified_paths'], [kit.CAPTURE])
        self.assertEqual(result['affected_roots'], [kit.REPORT])

    def test_identical_revision_and_trusted_digests(self):
        sha = hashlib.sha256(self.archive).hexdigest()
        result = kit.compare_bytes(self.archive, self.archive, sha, sha)
        self.assertFalse(result['requires_review'])
        self.assertTrue(result['comparison']['before']['trusted_digest_matched'])
        with self.assertRaises(ValueError):
            kit.inspect_bytes(self.archive, 'a' * 64)

    def test_strict_json_and_limits(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}',
                    b'[' * 65 + b']' * 65, b'\xff', b'x' * 99001):
            with self.assertRaises((ValueError, kit.groups.window.RpcError)):
                kit.build(raw)
        with self.assertRaises(ValueError):
            kit.inspect_bytes(b'x' * 99001)
        with self.assertRaises(ValueError):
            kit.inspect_bytes(bytearray(self.archive))

    def test_corrupt_and_noncanonical_zip_refused(self):
        data = bytearray(self.archive)
        pos = self.archive.index(self.raw)
        data[pos] ^= 1
        with self.assertRaises((ValueError, zipfile.BadZipFile)):
            kit.inspect_bytes(bytes(data))
        buffer = io.BytesIO(self.archive)
        with zipfile.ZipFile(buffer, 'a') as archive:
            archive.comment = b'different serialization'
        with self.assertRaises(ValueError):
            kit.inspect_bytes(buffer.getvalue())

    def test_empty_window(self):
        capture = copy.deepcopy(self.capture)
        capture.update(raw_logs=[], transfers=[], transfer_count=0, duplicate_count=0)
        result = kit.inspect_bytes(kit.build(kit.canonical(capture)))
        self.assertEqual(result['groups']['transactions'], [])

    def test_no_follow_file_boundaries(self):
        regular = self.folder / 'source.json'; regular.write_bytes(self.raw)
        link = self.folder / 'link.json'; link.symlink_to(regular.name)
        fifo = self.folder / 'fifo'; os.mkfifo(fifo)
        directory_link = self.folder / 'alias'; directory_link.symlink_to('.', target_is_directory=True)
        for path in (link, fifo, self.folder, directory_link / 'source.json',
                     str(regular.absolute()), '../missing', self.folder / '..' / 'missing'):
            with self.assertRaises((OSError, ValueError)):
                kit.read_workspace(path)
        self.assertEqual(kit.read_workspace(regular), self.raw)
        oversized = self.folder / 'large'; oversized.write_bytes(b' ' * 99001)
        with self.assertRaises(ValueError):
            kit.read_workspace(oversized)

    def test_output_never_overwrites_or_follows_links(self):
        target = self.folder / 'a.zip'; kit.save_new(target, self.archive)
        with self.assertRaises(OSError):
            kit.save_new(target, b'replace')
        alias = self.folder / 'alias'; alias.symlink_to('.', target_is_directory=True)
        with self.assertRaises(OSError):
            kit.save_new(alias / 'new.zip', self.archive)
        self.assertFalse((self.folder / 'new.zip').exists())
        self.assertEqual(target.read_bytes(), self.archive)

    def test_standalone_cli_and_revision_exit(self):
        bundle = self.folder / 'copied'; shutil.copytree(kit.HERE, bundle)
        script = str((bundle / 'group_handoff.py').absolute())
        demo = subprocess.run([sys.executable, '-B', script, 'demo'], cwd=bundle,
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(demo.returncode, 0, demo.stderr)
        (bundle / 'before.zip').write_bytes(self.archive)
        (bundle / 'after.zip').write_bytes(kit.build(self.raw + b'\n'))
        result = subprocess.run([sys.executable, '-B', script, 'compare',
                                 'before.zip', 'after.zip', '--fail-on-impact'], cwd=bundle,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(json.loads(result.stdout)['requires_review'])
        (bundle / 'bad.zip').write_bytes(b'not a zip')
        result = subprocess.run([sys.executable, '-B', script, 'check', 'bad.zip'],
                                cwd=bundle, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')

    def test_provenance(self):
        for entry in json.loads((kit.HERE / 'PROVENANCE.json').read_text()):
            self.assertEqual(hashlib.sha256(Path(entry['source']).read_bytes()).hexdigest(),
                             entry['source_sha256'])
            self.assertEqual(hashlib.sha256((kit.HERE / entry['copy']).read_bytes()).hexdigest(),
                             entry['copy_sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
