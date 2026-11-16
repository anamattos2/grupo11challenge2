"""Extração local de PDFs; não aprova fontes nem cria índice vetorial."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata


def clean_text(text: str) -> str:
    """Normaliza espaços e controles sem unir palavras ou remover acentos."""
    text = unicodedata.normalize('NFC', text.replace('\r\n', '\n').replace('\r', '\n'))
    text = ''.join(char for char in text if char in '\n\t' or
                   unicodedata.category(char) not in ('Cc', 'Cf'))
    lines = [re.sub(r'[^\S\n]+', ' ', line).strip() for line in text.split('\n')]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def extract_pdf(path: Path, document_id: str, expected_sha256: str | None = None) -> dict:
    """Retorna relatório JSON serializável, inclusive para erros de arquivo/página.

    Páginas são físicas, começando em 1. O texto bruto permite revisar a limpeza.
    O hash identifica os mesmos bytes usados pelo extrator (leitura única).
    """
    import pymupdf

    if not document_id.strip():
        raise ValueError('document_id deve ser preenchido')
    result = {
        'schema_version': 1, 'document_id': document_id, 'source_path': str(path),
        'source_sha256': None, 'extractor': f'PyMuPDF {pymupdf.VersionBind}',
        'cleaning_version': '1', 'status': 'error', 'page_count': None,
        'pages': [], 'issues': [],
    }
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        result['issues'].append({'code': 'read_failed', 'error_type': type(exc).__name__})
        return result
    result['source_sha256'] = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and expected_sha256 != result['source_sha256']:
        result['issues'].append({'code': 'hash_mismatch'})
        return result
    if not data.startswith(b'%PDF-'):
        result['issues'].append({'code': 'not_pdf'})
        return result
    try:
        document = pymupdf.open(stream=data, filetype='pdf')
    except Exception as exc:
        result['issues'].append({'code': 'open_failed', 'error_type': type(exc).__name__})
        return result
    with document:
        if document.needs_pass:
            result['issues'].append({'code': 'password_required'})
            return result
        result['page_count'] = len(document)
        if not len(document):
            result['issues'].append({'code': 'no_pages'})
            return result
        for index in range(len(document)):
            page = {'document_id': document_id, 'source_sha256': result['source_sha256'],
                    'page_number': index + 1, 'raw_text': None, 'text': None,
                    'status': 'error'}
            try:
                raw = document[index].get_text('text', sort=True)
                page.update(raw_text=raw, text=clean_text(raw))
                page['status'] = 'ok' if page['text'] else 'empty'
                if page['status'] == 'empty':
                    result['issues'].append({'code': 'no_text', 'page_number': index + 1})
            except Exception as exc:
                result['issues'].append({'code': 'page_failed', 'page_number': index + 1,
                                         'error_type': type(exc).__name__})
            result['pages'].append(page)
    result['status'] = 'ok' if not result['issues'] else 'partial'
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--document-id', required=True)
    parser.add_argument('--expected-sha256')
    args = parser.parse_args()
    if not args.document_id.strip():
        parser.error('--document-id não pode ser vazio')
    result = extract_pdf(args.path, args.document_id, args.expected_sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'ok' else 2 if result['status'] == 'partial' else 1


if __name__ == '__main__':
    raise SystemExit(main())
