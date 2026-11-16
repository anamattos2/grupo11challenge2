"""Falhas que comprometeriam a contagem ou identidade do corpus."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('catalogo', Path(__file__).resolve().parents[1] / 'scripts/verificar_catalogo.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.files = {f'{i}.pdf': f'%PDF-1.7 source {i}'.encode() for i in range(20)}
        self.sources = [dict(id=str(i), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), canonical_path=path, aliases=[path], origin={'description': 'Capa'}, use_conditions='Pendente', approved_for_ingestion=False, status='identificado', format='pdf') for i, (path, data) in enumerate(self.files.items())]

    def test_twenty_sources(self):
        self.assertEqual(module.validate(self.sources, self.files.__getitem__)[0], 20)

    def test_changed_content(self):
        self.files['0.pdf'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'divergente'):
            module.validate(self.sources, self.files.__getitem__)

    def test_duplicate_does_not_increase_count(self):
        self.sources.append(copy.deepcopy(self.sources[0]))
        with self.assertRaisesRegex(ValueError, 'duplicado'):
            module.validate(self.sources, self.files.__getitem__)

    def test_unverified_source_not_counted(self):
        self.sources[0]['status'] = 'origem_pendente'
        with self.assertRaisesRegex(ValueError, 'mínimo'):
            module.validate(self.sources, self.files.__getitem__)

    def test_ingestion_requires_separate_review(self):
        self.sources[0]['approved_for_ingestion'] = True
        with self.assertRaisesRegex(ValueError, 'não autoriza'):
            module.validate(self.sources, self.files.__getitem__)


if __name__ == '__main__':
    unittest.main()
