"""Consulta evidências documentais em uma coleção Chroma educativa."""

import argparse
import json
import math
from pathlib import Path

from .vector_index import CONFIG, _index_configuration, _load_encoder


DEFAULT_LIMIT = 5
DEFAULT_MIN_SCORE = 0.85


def _response(status: str, *, evidencias: list | None = None, error: str | None = None) -> dict:
    return {'schema_version': 1, 'status': status, 'evidencias': evidencias or [], 'error': error}


def search_evidence(
    db_path: Path,
    collection_name: str,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    min_score: float = DEFAULT_MIN_SCORE,
    document_id: str | None = None,
) -> dict:
    """Retorna evidências ordenadas por similaridade de cosseno."""
    if type(limit) is not int or limit < 1 or not -1 <= min_score <= 1:
        raise ValueError('use limite inteiro positivo e score mínimo entre -1 e 1')
    query = query.strip()
    if not query:
        return _response('empty_query')
    if not (db_path / 'chroma.sqlite3').is_file():
        return _response('error', error='index_not_found')

    try:
        import chromadb
        from chromadb.errors import NotFoundError

        expected = _index_configuration()
    except ImportError:
        return _response('error', error='dependency_unavailable')

    try:
        client = chromadb.PersistentClient(path=str(db_path))
        collection = client.get_collection(collection_name, embedding_function=None)
        stored = json.loads((collection.metadata or {}).get('configuration', 'null'))
        if stored != expected:
            return _response('error', error='incompatible_collection')
        if not collection.count():
            return _response('no_results')
    except NotFoundError:
        return _response('error', error='collection_not_found')
    except (ValueError, TypeError):
        return _response('error', error='incompatible_collection')
    except Exception:
        return _response('error', error='index_read_failed')

    try:
        model = _load_encoder()
        vector = model.encode(
            [CONFIG['query_prefix'] + query],
            normalize_embeddings=CONFIG['normalize'],
            precision=CONFIG['precision'],
            show_progress_bar=False,
        )
        if vector.shape != (1, CONFIG['dimension']):
            return _response('error', error='embedding_failed')
    except Exception:
        return _response('error', error='embedding_failed')

    try:
        result = collection.query(
            query_embeddings=vector.tolist(),
            n_results=limit,
            where={'document_id': document_id} if document_id is not None else None,
            include=['documents', 'metadatas', 'distances'],
        )
        evidencias = []
        for chunk_id, text, metadata, distance in zip(
            result['ids'][0], result['documents'][0], result['metadatas'][0],
            result['distances'][0], strict=True,
        ):
            if not math.isfinite(distance):
                return _response('error', error='index_query_failed')
            score = max(-1.0, min(1.0, 1.0 - distance))
            if score >= min_score:
                evidencias.append({
                    'chunk_id': chunk_id,
                    'document_id': metadata['document_id'],
                    'source_sha256': metadata['source_sha256'],
                    'page_number': metadata['page_number'],
                    'start': metadata['start'],
                    'end': metadata['end'],
                    'text': text,
                    'score': score,
                })
    except Exception:
        return _response('error', error='index_query_failed')
    return _response('ok' if evidencias else 'no_results', evidencias=evidencias)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--collection', required=True)
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT)
    parser.add_argument('--min-score', type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument('--document-id')
    parser.add_argument('query')
    args = parser.parse_args()
    try:
        result = search_evidence(
            args.db, args.collection, args.query,
            limit=args.limit, min_score=args.min_score, document_id=args.document_id,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['status'] == 'error' else 0


if __name__ == '__main__':
    raise SystemExit(main())
