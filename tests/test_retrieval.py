"""Contrato de busca com fontes fictícias e Chroma persistente."""

from contextlib import nullcontext
import hashlib
from importlib.util import find_spec
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from finance_ai.retrieval import DEFAULT_MIN_SCORE, search_evidence
from finance_ai.vector_index import rebuild_index


class RetrievalInputTest(unittest.TestCase):
    def test_empty_query_and_missing_index(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / 'chroma'
            self.assertEqual(search_evidence(db, 'fixture', ' \n')['status'], 'empty_query')
            self.assertEqual(search_evidence(db, 'fixture', 'reserva')['error'], 'index_not_found')
            self.assertFalse(db.exists())
            with self.assertRaises(ValueError):
                search_evidence(db, 'fixture', 'reserva', limit=0)


@unittest.skipUnless(
    find_spec('chromadb') and find_spec('sentence_transformers'), 'requer o extra vector',
)
class RetrievalTest(unittest.TestCase):
    def setUp(self):
        import pymupdf

        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.db = self.root / 'chroma'
        self.catalog = self.root / 'catalog.json'
        self.reserve = 'Uma reserva de emergência cobre despesas essenciais em situações imprevistas.'
        sources = []
        for name, text in [
            ('RESERVA', self.reserve),
            ('SEGURO', 'A apólice fictícia de seguro automotivo inclui cobertura para colisões.'),
        ]:
            path = self.root / f'{name}.pdf'
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((72, 72), text)
                pdf.save(path)
            sources.append({
                'id': name, 'format': 'pdf', 'canonical_path': path.name,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'approved_for_ingestion': True,
            })
        self.reserve_sha = sources[0]['sha256']
        self.catalog.write_text(json.dumps({'schema_version': 1, 'sources': sources}))

    def test_relevant_evidence_and_provenance(self):
        import numpy as np

        real_model = os.getenv('FINANCE_AI_TEST_REAL_MODEL') == '1'
        index_mock = nullcontext() if real_model else patch('finance_ai.vector_index._load_encoder')
        search_mock = nullcontext() if real_model else patch('finance_ai.retrieval._load_encoder')
        with index_mock as index_loader, search_mock as search_loader:
            if not real_model:
                vectors = np.eye(2, 384)
                index_loader.return_value.encode.return_value = vectors
                search_loader.return_value.encode.return_value = vectors[:1]
            index = rebuild_index(self.catalog, self.root, self.db)
            args = (self.db, index['collection'], 'Para que serve a reserva de emergência?')
            result = search_evidence(*args)
            self.assertEqual(result['status'], 'ok', result)
            evidence = result['evidencias'][0]
            self.assertEqual(evidence['document_id'], 'RESERVA')
            self.assertEqual(evidence['source_sha256'], self.reserve_sha)
            self.assertEqual(evidence['page_number'], 1)
            self.assertEqual(evidence['text'], self.reserve)
            self.assertEqual((evidence['start'], evidence['end']), (0, len(self.reserve)))
            self.assertEqual(len(evidence['chunk_id']), 64)
            self.assertGreaterEqual(evidence['score'], DEFAULT_MIN_SCORE)
            self.assertEqual(result['evidencias'], [evidence])
            self.assertEqual(search_evidence(*args, document_id='AUSENTE')['status'], 'no_results')
            if not real_model:
                self.assertEqual(search_evidence(*args, document_id='SEGURO')['status'], 'no_results')
                search_loader.side_effect = RuntimeError('falha fictícia')
                self.assertEqual(search_evidence(*args)['error'], 'embedding_failed')

        missing = search_evidence(self.db, 'colecao-ausente', args[2])
        self.assertEqual(missing['error'], 'collection_not_found')
