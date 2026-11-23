"""Segmenta o texto limpo de um relatório de extração JSON por página."""

import argparse
import hashlib
import json
from pathlib import Path


DEFAULT_SIZE = 1000
DEFAULT_OVERLAP = 150
ALGORITHM = 'page-char-window-v1'


def chunk_report(
    report: dict,
    *,
    size: int = DEFAULT_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> dict:
    """Gera janelas sobre o texto limpo com offsets e IDs reproduzíveis."""
    if type(size) is not int or type(overlap) is not int or not 0 <= overlap < size:
        raise ValueError('use inteiros com 0 <= sobreposição < tamanho')
    if report['schema_version'] != 1:
        raise ValueError('versão do relatório de extração não suportada')

    document_id = report['document_id']
    source_sha256 = report['source_sha256']
    parameters = {'algorithm': ALGORITHM, 'size': size, 'overlap': overlap}
    chunks = []
    for page in report['pages']:
        if page['status'] != 'ok' or not page['text']:
            continue
        page_number = page['page_number']
        text = page['text']
        for start in range(0, len(text), size - overlap):
            end = min(start + size, len(text))
            content = text[start:end]
            identity = [
                ALGORITHM, size, overlap, document_id, source_sha256,
                page_number, start, end, content,
            ]
            encoded = json.dumps(identity, ensure_ascii=False, separators=(',', ':'))
            chunks.append({
                'chunk_id': hashlib.sha256(encoded.encode('utf-8')).hexdigest(),
                'document_id': document_id,
                'source_sha256': source_sha256,
                'page_number': page_number,
                'start': start,
                'end': end,
                'text': content,
            })
            if end == len(text):
                break

    return {
        'schema_version': 1,
        'document_id': document_id,
        'source_sha256': source_sha256,
        'extractor': report['extractor'],
        'cleaning_version': report['cleaning_version'],
        'extraction_status': report['status'],
        'extraction_issues': report['issues'],
        'parameters': parameters,
        'chunks': chunks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path, help='relatório da extração em JSON')
    parser.add_argument('--size', type=int, default=DEFAULT_SIZE)
    parser.add_argument('--overlap', type=int, default=DEFAULT_OVERLAP)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding='utf-8'))
        result = chunk_report(report, size=args.size, overlap=args.overlap)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(f'relatório ou parâmetros inválidos: {exc}')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
