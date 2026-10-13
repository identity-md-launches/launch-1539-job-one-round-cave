"""Behavioral checks using retained real headers and deliberately altered copies."""
import copy
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

import header_hash_check as tool

SOURCE = tool.TOOLS / 'snapshot-seal/current-zto.json'


class HeaderHashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.snapshot, _ = tool.seal.load_snapshot(SOURCE)
        cls.block = cls.snapshot['block']

    def test_real_snapshot_offline(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            result = tool.report(SOURCE)
        self.assertTrue(result['all_header_hashes_match'])
        self.assertEqual(result['snapshot_sha256'], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual([x['block_number'] for x in result['headers']], ['26180977'] * 2)
        self.assertEqual(result['headers'][0]['computed_hash'], self.block['hash'])

    def test_keccak_known_answers(self):
        self.assertEqual(tool.keccak256(b'').hex(),
                         'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')
        self.assertEqual(tool.keccak256(b'abc').hex(),
                         '4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45')
        self.assertNotEqual(tool.keccak256(b'abc'), hashlib.sha3_256(b'abc').digest())

    def test_every_header_field_affects_hash(self):
        for field, length in tool.FIELDS:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.block)
                if length is None:
                    changed[field] = hex(int(changed[field], 16) + 1)
                else:
                    data = bytearray.fromhex(changed[field][2:])
                    data[0] ^= 1
                    changed[field] = '0x' + data.hex()
                self.assertFalse(tool.check_header(changed)['matches'])

    def test_missing_fields_refused(self):
        for field, _ in tool.FIELDS:
            with self.subTest(field=field):
                changed = dict(self.block)
                del changed[field]
                with self.assertRaises(ValueError):
                    tool.check_header(changed)

    def test_quantities_are_canonical_and_bounded(self):
        for field, length in tool.FIELDS:
            if length is not None:
                continue
            for value in (True, None, 1, 'latest', '0x', '0x00', '0x01',
                          '0x-1', '0xg', '0x' + '1' * 65):
                with self.subTest(field=field, value=value):
                    changed = dict(self.block, **{field: value})
                    with self.assertRaises(ValueError):
                        tool.check_header(changed)

    def test_bytes_lengths_and_hex(self):
        for field, length in tool.FIELDS:
            if length is None or length == -1:
                continue
            for value in (None, 7, '0x', '0x' + 'ff' * (length + 1),
                          '0x' + 'gg' * length):
                with self.subTest(field=field, value=value):
                    changed = dict(self.block, **{field: value})
                    with self.assertRaises(ValueError):
                        tool.check_header(changed)

    def test_extra_data_limit(self):
        for value in ('0x' + '01' * 33, '0x0', None):
            with self.assertRaises(ValueError):
                tool.check_header(dict(self.block, extraData=value))
        self.assertFalse(tool.check_header(dict(self.block, extraData='0x'))['matches'])

    def test_reported_hash_required(self):
        for value in (None, '0x', '0x' + '00' * 31, '0x' + 'zz' * 32):
            with self.assertRaises(ValueError):
                tool.check_header(dict(self.block, hash=value))

    def test_rpc_nonheader_fields_not_committed(self):
        changed = dict(self.block, transactions=[], withdrawals=[], size='0x0')
        self.assertTrue(tool.check_header(changed)['matches'])

    def test_both_observations_checked(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['block_after']['gasUsed'] = '0x1'
        with patch.object(tool.seal, 'load_snapshot', return_value=(self.raw, snapshot,
                          tool.seal.pinned.inspect(snapshot))):
            result = tool.report(SOURCE)
        self.assertTrue(result['headers'][0]['matches'])
        self.assertFalse(result['headers'][1]['matches'])
        self.assertFalse(result['all_header_hashes_match'])

    def test_no_supply_authentication_claim(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['result'] = '0x' + '00' * 32
        facts = tool.seal.pinned.inspect(snapshot)
        with patch.object(tool.seal, 'load_snapshot', return_value=(self.raw, snapshot, facts)):
            result = tool.report(SOURCE)
        self.assertTrue(result['all_header_hashes_match'])
        self.assertEqual(result['reported_total_supply_base_units'], '0')
        self.assertIn('No trusted hash anchor', result['evidence_limits'])

    def test_rlp_boundary_vectors(self):
        self.assertEqual(tool.rlp_bytes(b''), b'\x80')
        self.assertEqual(tool.rlp_bytes(b'\x00'), b'\x00')
        self.assertEqual(tool.rlp_bytes(b'\x80'), b'\x81\x80')
        self.assertEqual(tool.rlp_bytes(b'a' * 55), b'\xb7' + b'a' * 55)
        self.assertEqual(tool.rlp_bytes(b'a' * 56), b'\xb8\x38' + b'a' * 56)

    def test_cli_demo(self):
        proc = subprocess.run([sys.executable, '-B', str(Path(tool.__file__)), 'demo'],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(json.loads(proc.stdout)['all_header_hashes_match'])

    def test_cli_rejects_bad_path(self):
        proc = subprocess.run([sys.executable, '-B', str(Path(tool.__file__)),
                               'check', '../outside-workspace.json'],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, '')

    def test_fresh_retained_publicnode_capture(self):
        source = Path(tool.__file__).with_name('live-zto.json')
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            result = tool.report(source)
        self.assertTrue(result['all_header_hashes_match'])
        self.assertEqual(result['headers'][0]['block_number'], '26182186')
        self.assertEqual(result['headers'][0]['computed_hash'],
                         '0x548d48bf1517d8775ddc4442f2581ac1df9902e3fc10bc1c45de78193e2e3426')

    def test_cli_conflict_is_diagnostic_exit_two(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['block']['gasUsed'] = '0x1'
        facts = tool.seal.pinned.inspect(snapshot)
        with patch.object(tool.seal, 'load_snapshot', return_value=(self.raw, snapshot, facts)), \
                patch.object(sys, 'argv', ['header_hash_check.py', 'demo']), \
                patch.object(sys, 'stdout', new_callable=io.StringIO) as output:
            self.assertEqual(tool.main(), 2)
            self.assertFalse(json.loads(output.getvalue())['all_header_hashes_match'])


if __name__ == '__main__':
    unittest.main()
