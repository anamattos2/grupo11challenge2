"""Valida identidade das fontes sem alterar arquivos ou normalizar aliases Git."""
import hashlib
import json
from pathlib import Path
import subprocess
import unicodedata

ROOT = Path(__file__).resolve().parents[1]


def validate(sources, read):
    ids, hashes, aliases, normalized = set(), set(), set(), {}
    count = 0
    for source in sources:
        sid, digest = source['id'], source['sha256']
        if sid in ids or digest in hashes:
            raise ValueError('ID ou conteúdo duplicado no catálogo')
        ids.add(sid)
        hashes.add(digest)
        if source['canonical_path'] not in source['aliases']:
            raise ValueError(f'{sid}: caminho canônico ausente dos aliases')
        if not source['origin']['description'] or not source['use_conditions']:
            raise ValueError(f'{sid}: origem ou condições de uso ausentes')
        if source['approved_for_ingestion']:
            raise ValueError(f'{sid}: este catálogo inicial não autoriza ingestão')
        for alias in source['aliases']:
            if alias in aliases or Path(alias).is_absolute() or '..' in Path(alias).parts:
                raise ValueError(f'{sid}: alias duplicado ou inválido')
            aliases.add(alias)
            data = read(alias)
            if len(data) != source['bytes'] or hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f'{sid}: conteúdo divergente em {alias}')
            if source['format'] == 'pdf' and not data.startswith(b'%PDF-'):
                raise ValueError(f'{sid}: assinatura PDF inválida')
            norm = unicodedata.normalize('NFC', alias)
            if norm in normalized and normalized[norm] != digest:
                raise ValueError(f'{sid}: colisão Unicode com conteúdos diferentes')
            normalized[norm] = digest
        if source['status'] == 'identificado' and source['format'] == 'pdf':
            count += 1
    if count < 20:
        raise ValueError(f'Apenas {count} PDFs identificados; mínimo: 20')
    return count, aliases


def main():
    sources = json.loads((ROOT / 'knowledge/catalogo.json').read_text())['sources']
    index = {}
    for record in subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=ROOT).split(b'\0'):
        if record:
            meta, raw_path = record.split(b'\t', 1)
            index[raw_path.decode()] = meta.split()[1].decode()
    cache = {}

    def read(alias):
        # Verifica alterações locais também. No macOS, nomes NFC/NFD podem
        # compartilhar o mesmo arquivo; os blobs preservam a identidade de ambos.
        local = (ROOT / alias).read_bytes()
        if alias not in index:
            return local
        blob = index[alias]
        if blob not in cache:
            cache[blob] = subprocess.check_output(['git', 'cat-file', 'blob', blob], cwd=ROOT)
        if local != cache[blob]:
            raise ValueError(f'Arquivo local difere do índice: {alias}')
        return cache[blob]

    count, aliases = validate(sources, read)
    historical = {p for p in index if p.startswith(('fontes/', 'RAG/projeto-rag/docs/'))}
    if historical - aliases:
        raise ValueError(f'Fontes históricas não catalogadas: {sorted(historical - aliases)}')
    print(f'{len(sources)} conteúdos únicos; {count} PDFs identificados; '
          f'{len(aliases)} caminhos preservados; 0 fontes aprovadas para ingestão.')


if __name__ == '__main__':
    main()
