"""Verifica a segmentação com um relatório de extração fictício."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from finance_ai.chunking import chunk_report


class ChunkingTest(unittest.TestCase):
    def setUp(self):
        self.report = {
            'schema_version': 1,
            'document_id': 'SYN001',
            'source_sha256': 'a' * 64,
            'extractor': 'extrator fictício',
            'cleaning_version': '1',
            'status': 'partial',
            'issues': [
                {'code': 'no_text', 'page_number': 2},
                {'code': 'page_failed', 'page_number': 4},
            ],
            'pages': [
                {'page_number': 1, 'status': 'ok', 'text': 'ábcdefghi'},
                {'page_number': 2, 'status': 'empty', 'text': ''},
                {'page_number': 3, 'status': 'ok', 'text': 'Síntese'},
                {'page_number': 4, 'status': 'error', 'text': None},
            ],
        }

    def test_bounds_overlap_and_provenance(self):
        result = chunk_report(self.report, size=5, overlap=1)
        chunks = result['chunks']
        self.assertEqual(
            [(c['page_number'], c['start'], c['end'], c['text']) for c in chunks],
            [(1, 0, 5, 'ábcde'), (1, 4, 9, 'efghi'),
             (3, 0, 5, 'Sínte'), (3, 4, 7, 'ese')],
        )
        for chunk in chunks:
            self.assertEqual(chunk['document_id'], 'SYN001')
            self.assertEqual(chunk['source_sha256'], 'a' * 64)
        self.assertEqual(result['extraction_status'], 'partial')
        self.assertEqual(result['extraction_issues'], self.report['issues'])

    def test_ids_repeat_and_distinguish_parameters_and_sources(self):
        result = chunk_report(self.report)
        self.assertEqual(result, chunk_report(json.loads(json.dumps(self.report))))
        ids = {chunk['chunk_id'] for chunk in result['chunks']}
        self.assertEqual(len(ids), len(result['chunks']))
        for changed in (
            chunk_report(self.report, overlap=0),
            chunk_report({**self.report, 'source_sha256': 'b' * 64}),
        ):
            self.assertTrue(ids.isdisjoint(c['chunk_id'] for c in changed['chunks']))

    def test_invalid_parameters(self):
        for size, overlap in [(0, 0), (5, -1), (5, 5), (5, 6)]:
            with self.subTest(size=size, overlap=overlap):
                with self.assertRaises(ValueError):
                    chunk_report(self.report, size=size, overlap=overlap)

    def test_cli_writes_chunk_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.json'
            path.write_text(json.dumps(self.report), encoding='utf-8')
            process = subprocess.run(
                [sys.executable, '-m', 'finance_ai.chunking', str(path),
                 '--size', '5', '--overlap', '1'],
                check=True, capture_output=True, encoding='utf-8',
            )
        self.assertEqual(json.loads(process.stdout), chunk_report(self.report, size=5, overlap=1))
