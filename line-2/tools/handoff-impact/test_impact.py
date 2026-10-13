#!/usr/bin/env python3
"""Offline behavioral checks; all fixtures remain in test/scratch."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('tested_impact',
    Path('line-2/tools/handoff-impact/impact.py'))
impact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impact)


class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.files = {'root': b'root', 'mid': b'mid', 'leaf': b'leaf', 'other': b'other'}
        self.document = {'format': 'handoff-impact-graph-v1', 'roots': ['root', 'other'],
                         'dependencies': {'root': ['mid'], 'mid': ['leaf'],
                                          'leaf': [], 'other': []}}
        Path('test/scratch').mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir='test/scratch')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).relative_to(Path.cwd())

    def analyze(self, files=None, document=None, **kwargs):
        return impact.analyze_bytes(impact.WRITER.build(self.files),
            impact.WRITER.build(self.files if files is None else files),
            self.document if document is None else document, **kwargs)

    def changed(self, **updates):
        return dict(self.files, **updates)

    def test_transitive_same_size_edit(self):
        report = self.analyze(self.changed(leaf=b'LEAF'))
        self.assertEqual(report['affected_roots'], ['root'])
        self.assertEqual(report['affected_declared_paths'], ['leaf', 'mid', 'root'])
        self.assertEqual(report['direct_modified_paths'], ['leaf'])
        self.assertEqual(report['unaffected_roots'], ['other'])
        self.assertTrue(report['requires_review'])

    def test_direct_root_edit(self):
        report = self.analyze(self.changed(root=b'ROOT'))
        self.assertEqual(report['affected_declared_paths'], ['root'])

    def test_removal_is_diagnostic(self):
        files = dict(self.files)
        del files['leaf']
        report = self.analyze(files)
        self.assertEqual(report['missing_dependency_paths'], ['leaf'])
        self.assertEqual(report['affected_roots'], ['root'])

    def test_removed_root(self):
        files = dict(self.files)
        del files['root']
        report = self.analyze(files)
        self.assertEqual(report['affected_roots'], ['root'])
        self.assertEqual(report['missing_dependency_paths'], ['root'])

    def test_multiple_roots_shared_dependency(self):
        self.document['dependencies']['other'] = ['leaf']
        self.assertEqual(self.analyze(self.changed(leaf=b'x'))['affected_roots'], ['other', 'root'])

    def test_cycle_terminates(self):
        self.document['dependencies']['leaf'] = ['root']
        report = self.analyze(self.changed(mid=b'x'))
        self.assertEqual(report['affected_declared_paths'], ['leaf', 'mid', 'root'])

    def test_self_edge(self):
        self.document['dependencies']['other'] = ['other']
        self.assertEqual(self.analyze(self.changed(other=b'x'))['affected_roots'], ['other'])

    def test_additions_are_visible_but_not_inferred(self):
        report = self.analyze(self.changed(new=b'new'))
        self.assertFalse(report['requires_review'])
        self.assertEqual(report['comparison']['added'][0]['path'], 'new')

    def test_outside_closure(self):
        self.document['roots'] = ['root']
        report = self.analyze(self.changed(other=b'x'))
        self.assertEqual(report['changed_outside_closure'], ['other'])
        self.assertEqual(report['affected_declared_paths'], [])

    def test_unchanged(self):
        report = self.analyze()
        self.assertFalse(report['requires_review'])
        self.assertTrue(report['comparison']['same_archive'])

    def test_metadata_only_change(self):
        packed = impact.WRITER.build(self.files)
        modified = io.BytesIO(packed)
        with zipfile.ZipFile(modified, 'a') as archive:
            archive.comment = b'New transport metadata'
        report = impact.analyze_bytes(packed, modified.getvalue(), self.document)
        self.assertFalse(report['comparison']['same_archive'])
        self.assertTrue(report['comparison']['same_payload'])
        self.assertFalse(report['requires_review'])

    def test_undeclared_leaf_refused(self):
        del self.document['dependencies']['leaf']
        with self.assertRaisesRegex(ValueError, 'undeclared'):
            self.analyze()

    def test_baseline_absent_graph_node_refused(self):
        self.document['dependencies']['ghost'] = []
        with self.assertRaisesRegex(ValueError, 'baseline'):
            self.analyze()

    def test_graph_invalid_shapes_and_paths(self):
        for document in ([], {}, dict(self.document, extra=True),
                         dict(self.document, roots=['../escape']),
                         dict(self.document, roots=['root', 'root']),
                         dict(self.document, dependencies={'root': ['HANDOFF.json']})):
            with self.subTest(document=document), self.assertRaises((ValueError, TypeError)):
                self.analyze(document=document)

    def test_json_duplicates_constants_and_size(self):
        limits = impact.INSPECT.Limits()
        for data in (b'{"format":"x","format":"y"}', b'{"roots":NaN}',
                     b'\xff', b' ' * (impact.DEP.MAX_GRAPH_BYTES + 1)):
            with self.subTest(data=data[:40]), self.assertRaises(ValueError):
                impact.parse_graph(data, limits)

    def test_deterministic_order_and_root_digest(self):
        first = self.analyze(self.changed(leaf=b'x'))
        reordered = dict(self.document, roots=list(reversed(self.document['roots'])),
                         dependencies=dict(reversed(list(self.document['dependencies'].items()))))
        self.assertEqual(first, self.analyze(self.changed(leaf=b'x'), reordered))
        reordered['roots'] = ['root']
        self.assertNotEqual(first['graph_sha256'], self.analyze(document=reordered)['graph_sha256'])

    def test_trusted_digest(self):
        packed = impact.WRITER.build(self.files)
        digest = hashlib.sha256(packed).hexdigest()
        report = self.analyze(before_sha256=digest, after_sha256=digest)
        self.assertTrue(report['comparison']['before']['trusted_digest_matched'])
        with self.assertRaisesRegex(ValueError, 'trusted digest'):
            self.analyze(after_sha256='0' * 64)

    def test_corrupt_unselected_file_refused(self):
        self.document['roots'] = ['root']
        packed = impact.WRITER.build(self.files)
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(packed)) as archive, zipfile.ZipFile(output, 'w') as target:
            for entry in archive.infolist():
                target.writestr(entry, b'WRONG' if entry.filename == 'other' else archive.read(entry.filename))
        for left, right in ((packed, output.getvalue()), (output.getvalue(), packed)):
            with self.subTest(), self.assertRaises(ValueError):
                impact.analyze_bytes(left, right, self.document)

    def test_limits_and_report_budget(self):
        with self.assertRaisesRegex(ValueError, 'bounded'):
            self.analyze(limits=impact.INSPECT.Limits(archive_bytes=1))
        with patch.object(impact, 'MAX_REPORT_BYTES', 1), self.assertRaisesRegex(ValueError, 'report'):
            self.analyze()
        with self.assertRaisesRegex(ValueError, 'positive'):
            self.analyze(limits=impact.INSPECT.Limits(files=0))

    def fixtures(self):
        before, after, graph = (self.folder / name for name in ('before.zip', 'after.zip', 'graph.json'))
        before.write_bytes(impact.WRITER.build(self.files))
        after.write_bytes(impact.WRITER.build(self.changed(leaf=b'x')))
        graph.write_text(json.dumps(self.document))
        return [str(before), str(after), str(graph)]

    def cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = impact.main(argv)
        return status, out.getvalue(), err.getvalue()

    def test_cli_exits(self):
        paths = self.fixtures()
        status, out, err = self.cli(['check', *paths, '--fail-on-impact'])
        self.assertEqual(status, 2)
        self.assertTrue(json.loads(out)['requires_review'])
        self.assertFalse(err)
        self.assertEqual(self.cli(['check', *paths])[0], 0)
        Path(paths[1]).write_bytes(b'corrupt')
        status, out, err = self.cli(['check', *paths])
        self.assertEqual(status, 1)
        self.assertEqual(out, '')
        self.assertIn('handoff-impact', err)

    def test_paths_symlinks_fifo_and_traversal(self):
        paths = self.fixtures()
        alias = self.folder / 'alias'
        alias.symlink_to('before.zip')
        for before in (str(alias), '../outside', '/etc/passwd'):
            with self.subTest(before=before), self.assertRaises(ValueError):
                impact.analyze_paths(before, paths[1], paths[2])
        import os
        fifo = self.folder / 'fifo'
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, 'regular'):
            impact.analyze_paths(str(fifo), paths[1], paths[2])

    def test_invalid_graph_before_archive_reads(self):
        paths = self.fixtures()
        Path(paths[2]).write_text('{}')
        reads = []
        real_read = impact.WRITER.regular_bytes
        def read(path, limit):
            reads.append(path.name)
            return real_read(path, limit)
        with patch.object(impact.WRITER, 'regular_bytes', read), self.assertRaises(ValueError):
            impact.analyze_paths(*paths)
        self.assertEqual(reads, ['graph.json'])

    def test_each_file_captured_once(self):
        paths = self.fixtures()
        reads = []
        real_read = impact.WRITER.regular_bytes
        def read(path, limit):
            reads.append(path.name)
            data = real_read(path, limit)
            path.write_bytes(b'replaced after read')
            return data
        with patch.object(impact.WRITER, 'regular_bytes', read):
            report = impact.analyze_paths(*paths)
        self.assertEqual(reads, ['graph.json', 'before.zip', 'after.zip'])
        self.assertEqual(report['affected_roots'], ['root'])

    def test_real_inherited_archive_and_demo(self):
        report = impact.analyze_paths('line-2/handoff.zip', 'line-2/handoff.zip',
            'line-2/tools/handoff-impact/example-graph.json')
        self.assertFalse(report['requires_review'])
        self.assertEqual(report['comparison']['before']['file_count'], 2)
        self.assertEqual(impact.demo()['affected_roots'], ['README.md'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
