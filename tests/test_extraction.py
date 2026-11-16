"""PDFs fictícios: rastreabilidade, limpeza e falhas sem dados reais."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
from finance_ai.extraction import clean_text, extract_pdf


class ExtractionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'synthetic.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((72, 72), 'Reserva ficticia: R$ 1.234,56\nMeta: 6 meses')
            pdf.new_page()
            pdf.new_page().insert_text((72, 72), 'Pagina final: saldo -20,00')
            pdf.save(self.path)

    def test_cleanup_keeps_meaning_and_paragraphs(self):
        raw = '  Educac\u0327a\u0303o\t  financeira\r\n\r\n\r\nR$\u00a01.234,56\x00\n-20,00  '
        self.assertEqual(clean_text(raw), 'Educação financeira\n\nR$ 1.234,56\n-20,00')
        self.assertEqual(clean_text('reser-\nva'), 'reser-\nva')
        self.assertEqual(clean_text(clean_text(raw)), clean_text(raw))

    def test_pages_and_hash_are_traceable(self):
        before = self.path.read_bytes()
        digest = hashlib.sha256(before).hexdigest()
        report = extract_pdf(self.path, 'SYN001', digest)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['page_count'], 3)
        self.assertEqual([p['page_number'] for p in report['pages']], [1, 2, 3])
        for page in report['pages']:
            self.assertEqual(page['source_sha256'], digest)
            self.assertEqual(page['document_id'], 'SYN001')
        self.assertIn('R$ 1.234,56', report['pages'][0]['text'])
        self.assertIn('-20,00', report['pages'][2]['text'])
        self.assertEqual(report['issues'], [{'code': 'no_text', 'page_number': 2}])
        self.assertEqual(report['pages'][1]['status'], 'empty')
        self.assertEqual(self.path.read_bytes(), before)

    def test_wrong_hash_stops_extraction(self):
        report = extract_pdf(self.path, 'SYN001', '0' * 64)
        self.assertEqual(report['issues'], [{'code': 'hash_mismatch'}])
        self.assertEqual(report['pages'], [])

    def test_cli_success_with_extensionless_pdf(self):
        path = self.path.with_name('extensionless')
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((72, 72), 'Documento ficticio completo')
            pdf.save(path)
        process = subprocess.run([sys.executable, '-m', 'finance_ai.extraction', str(path), '--document-id', 'SYN'], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(report['status'], 'ok')
        self.assertEqual(report['issues'], [])
        self.assertIn('Documento ficticio completo', report['pages'][0]['raw_text'])

    def test_missing_and_invalid_files(self):
        self.assertEqual(extract_pdf(self.path.with_name('missing.pdf'), 'SYN')['issues'][0]['code'], 'read_failed')
        self.path.write_bytes(b'not a PDF')
        self.assertEqual(extract_pdf(self.path, 'SYN')['issues'][0]['code'], 'not_pdf')
        self.path.write_bytes(b'%PDF-1.7\nbroken')
        self.assertEqual(extract_pdf(self.path, 'SYN')['issues'][0]['code'], 'open_failed')

    def test_encrypted_pdf_is_reported(self):
        locked = self.path.with_name('locked.pdf')
        with pymupdf.open(self.path) as pdf:
            pdf.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='synthetic')
        self.assertEqual(extract_pdf(locked, 'SYN')['issues'], [{'code': 'password_required'}])

    def test_page_failure_does_not_hide_remaining_pages(self):
        original = pymupdf.Page.get_text

        def fail_middle(page, *args, **kwargs):
            if page.number == 1:
                raise RuntimeError('simulated failure')
            return original(page, *args, **kwargs)

        with patch.object(pymupdf.Page, 'get_text', fail_middle):
            report = extract_pdf(self.path, 'SYN')
        self.assertEqual(report['pages'][1]['status'], 'error')
        self.assertEqual(report['pages'][2]['status'], 'ok')
        self.assertEqual(report['issues'][0]['code'], 'page_failed')

    def test_cli_reports_partial_and_error_exit_codes(self):
        for path, code in ((self.path, 2), (self.path.with_name('absent'), 1)):
            process = subprocess.run([sys.executable, '-m', 'finance_ai.extraction', str(path), '--document-id', 'SYN'], capture_output=True, text=True)
            self.assertEqual(process.returncode, code, process.stderr)
            self.assertEqual(json.loads(process.stdout)['document_id'], 'SYN')


if __name__ == '__main__':
    unittest.main()
