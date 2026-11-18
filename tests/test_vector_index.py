"""Reconstrução Chroma com fontes e catálogo fictícios."""

import hashlib
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finance_ai.vector_index import CONFIG, rebuild_index


class VectorIndexTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.catalog = self.root / 'catalog.json'
        self.db = self.root / 'chroma'

    def write_catalog(self, sources):
        self.catalog.write_text(json.dumps({'schema_version': 1, 'sources': sources}))

    def write_pdf(self, text):
        import pymupdf

        path = self.root / 'ficticio.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((72, 72), text)
            pdf.new_page()
            pdf.save(path)
        return {'id': 'SYN001', 'format': 'pdf', 'canonical_path': path.name,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'approved_for_ingestion': True}

    def test_unapproved_sources_are_not_read(self):
        self.write_catalog([{'approved_for_ingestion': False}])
        result = rebuild_index(self.catalog, self.root, self.db)
        self.assertEqual(result['status'], 'no_approved_sources')
        self.assertFalse(self.db.exists())

    def test_checksum_mismatch_does_not_open_chroma(self):
        source = self.write_pdf('Investimento ficticio')
        self.write_catalog([{**source, 'sha256': '0' * 64}])
        with self.assertRaisesRegex(ValueError, 'hash_mismatch'):
            rebuild_index(self.catalog, self.root, self.db)
        self.assertFalse(self.db.exists())

    @unittest.skipUnless(
        find_spec('chromadb') and find_spec('sentence_transformers'), 'requer o extra vector',
    )
    def test_rebuild_reuses_chunks_and_keeps_collections(self):
        import chromadb
        import numpy as np

        self.write_catalog([self.write_pdf('Reserva ficticia')])
        with patch('finance_ai.vector_index._load_encoder') as load:
            load.return_value.encode.return_value = np.ones((1, CONFIG['dimension']))
            first = rebuild_index(self.catalog, self.root, self.db)
            second = rebuild_index(self.catalog, self.root, self.db)
            self.assertEqual(load.call_count, 1)
            load.return_value.encode.assert_called_once_with(
                ['passage: Reserva ficticia'], batch_size=32,
                normalize_embeddings=True, precision='float32', show_progress_bar=False,
            )
            self.write_catalog([self.write_pdf('Orcamento ficticio')])
            changed = rebuild_index(self.catalog, self.root, self.db)

        self.assertEqual(first['written_chunks'], 1)
        self.assertEqual(second['written_chunks'], 0)
        self.assertEqual(first['collection'], second['collection'])
        self.assertNotEqual(first['collection'], changed['collection'])
        self.assertEqual(first['sources'][0]['issues'], [{'code': 'no_text', 'page_number': 2}])
        client = chromadb.PersistentClient(path=str(self.db))
        old = client.get_collection(first['collection'], embedding_function=None)
        new = client.get_collection(changed['collection'], embedding_function=None)
        self.assertEqual(old.count(), 1)
        self.assertEqual(new.count(), 1)
        stored = old.get(include=['documents', 'metadatas', 'embeddings'])
        self.assertEqual(stored['documents'], ['Reserva ficticia'])
        self.assertEqual(stored['metadatas'][0]['document_id'], 'SYN001')
        self.assertEqual(stored['metadatas'][0]['page_number'], 1)
        self.assertEqual(stored['embeddings'].shape, (1, 384))
        self.assertEqual(json.loads(old.metadata['configuration']), first['configuration'])
        self.assertEqual(first['configuration']['revision'], CONFIG['revision'])
