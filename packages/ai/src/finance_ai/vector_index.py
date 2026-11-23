"""Reconstrói uma coleção Chroma local a partir dos PDFs aprovados no catálogo."""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path

from .chunking import chunk_report
from .extraction import extract_pdf


CONFIG = {
    'model': 'intfloat/multilingual-e5-small',
    'revision': 'fd1525a9fd15316a2d503bf26ab031a61d056e98',
    'dimension': 384,
    'max_tokens': 512,
    'passage_prefix': 'passage: ',
    'query_prefix': 'query: ',
    'normalize': True,
    'device': 'cpu',
    'precision': 'float32',
    'distance': 'cosine',
    'batch_size': 32,
}


def _load_encoder():
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        CONFIG['model'], revision=CONFIG['revision'], device=CONFIG['device'],
        model_kwargs={'use_safetensors': True},
    )
    model.max_seq_length = CONFIG['max_tokens']
    return model


def rebuild_index(
    catalog_path: Path, root: Path, db_path: Path, *, academic_local: bool = False,
) -> dict:
    """Persiste uma coleção por conjunto de chunks e configuração de embeddings."""
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    if catalog['schema_version'] != 1:
        raise ValueError('versão do catálogo não suportada')

    sources = sorted(
        (
            source for source in catalog['sources']
            if source['approved_for_ingestion'] is True
            and (academic_local or (source.get('ingestion_review') or {}).get('scope') is None)
        ),
        key=lambda source: source['id'],
    )
    if not sources:
        return {'status': 'no_approved_sources', 'collection': None, 'chunks': 0}
    if len({source['id'] for source in sources}) != len(sources):
        raise ValueError('IDs repetidos entre fontes aprovadas')

    root = root.resolve()
    chunks = []
    source_reports = []
    for source in sources:
        source_id = source['id']
        path = (root / source['canonical_path']).resolve()
        if source['format'] != 'pdf' or not path.is_relative_to(root):
            raise ValueError(f'{source_id}: esperado um PDF dentro da raiz do catálogo')
        digest = source['sha256']
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f'{source_id}: SHA-256 ausente ou inválido')
        report = extract_pdf(path, source_id, digest)
        review = source.get('ingestion_review')
        if review is not None and report['status'] != 'error':
            pages = review['pages']
            if (not isinstance(pages, list) or not pages
                    or any(type(page) is not int or not 1 <= page <= report['page_count']
                           for page in pages)):
                raise ValueError(f'{source_id}: páginas aprovadas inválidas')
            selected = set(pages)
            report['pages'] = [page for page in report['pages'] if page['page_number'] in selected]
            report['issues'] = [issue for issue in report['issues']
                                if issue.get('page_number') in selected]
        if report['status'] == 'error' or any(
            issue['code'] != 'no_text' for issue in report['issues']
        ):
            raise ValueError(f'extração de {source_id} falhou: {report["issues"]}')
        segmented = chunk_report(report)
        if not segmented['chunks']:
            raise ValueError(f'{source_id}: PDF sem texto segmentável')
        citation = review['citation'] if review is not None else ''
        chunks.extend({**chunk, 'citation': citation} for chunk in segmented['chunks'])
        source_reports.append({
            'document_id': source_id,
            'source_sha256': digest,
            'extractor': report['extractor'],
            'cleaning_version': report['cleaning_version'],
            'parameters': segmented['parameters'],
            'issues': report['issues'],
            'approved_pages': review['pages'] if review is not None else None,
            'scope': review.get('scope') if review is not None else None,
            'citation': citation or None,
        })

    import chromadb

    packages = ('chromadb', 'sentence-transformers', 'torch', 'transformers', 'tokenizers')
    configuration = {**CONFIG, 'libraries': {package: version(package) for package in packages}}
    ids = [chunk['chunk_id'] for chunk in chunks]
    snapshot = json.dumps([configuration, ids], sort_keys=True, separators=(',', ':'))
    fingerprint = hashlib.sha256(snapshot.encode('utf-8')).hexdigest()
    name = f'educativo-{fingerprint}'
    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_or_create_collection(
        name=name,
        embedding_function=None,
        metadata={'configuration': json.dumps(configuration, sort_keys=True),
                  'fingerprint': fingerprint},
        configuration={'hnsw': {'space': CONFIG['distance']}},
    )
    existing = set(collection.get(include=[])['ids'])
    missing = [chunk for chunk in chunks if chunk['chunk_id'] not in existing]
    if missing:
        model = _load_encoder()
        batch_size = CONFIG['batch_size']
        for start in range(0, len(missing), batch_size):
            batch = missing[start:start + batch_size]
            documents = [chunk['text'] for chunk in batch]
            embeddings = model.encode(
                [CONFIG['passage_prefix'] + text for text in documents],
                batch_size=batch_size,
                normalize_embeddings=CONFIG['normalize'],
                precision=CONFIG['precision'],
                show_progress_bar=False,
            )
            if embeddings.shape != (len(batch), CONFIG['dimension']):
                raise ValueError('dimensão inesperada no lote de embeddings')
            collection.upsert(
                ids=[chunk['chunk_id'] for chunk in batch],
                documents=documents,
                embeddings=embeddings.tolist(),
                metadatas=[
                    {key: chunk[key] for key in ('document_id', 'source_sha256',
                                                'page_number', 'start', 'end', 'citation')}
                    for chunk in batch
                ],
            )
    return {
        'status': 'ok',
        'collection': name,
        'configuration': configuration,
        'sources': source_reports,
        'chunks': len(chunks),
        'written_chunks': len(missing),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=Path('knowledge/catalogo.json'))
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--academic-local', action='store_true',
                        help='inclui fontes restritas a uso acadêmico local não comercial')
    args = parser.parse_args()
    try:
        result = rebuild_index(args.catalog, args.root, args.db, academic_local=args.academic_local)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
