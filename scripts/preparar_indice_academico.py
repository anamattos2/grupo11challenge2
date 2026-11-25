"""Instala o ambiente vetorial e reconstrói localmente o acervo acadêmico."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
ENVIRONMENT = RUNTIME / 'venv-indice'
DB = RUNTIME / 'chroma-academico-local'

# Páginas físicas das fontes adicionais usadas no protótipo acadêmico.
PAGES = {
    'F002': [5], 'F003': [4], 'F005': [4, 7], 'F008': [5], 'F009': [7, 8],
    'F010': [7], 'F012': [9], 'F013': [9], 'F015': [2], 'F016': [6],
    'F017': [5, 6], 'F021': [5], 'F022': [4], 'F023': [6], 'F024': [8],
}


def prepare_environment() -> None:
    interpreter = ENVIRONMENT / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not interpreter.is_file():
        venv.EnvBuilder(with_pip=True).create(ENVIRONMENT)
    package = ROOT / 'packages/ai'
    requirements = hashlib.sha256((package / 'pyproject.toml').read_bytes()).hexdigest()
    marker = ENVIRONMENT / '.vector-install'
    if not marker.is_file() or marker.read_text() != requirements:
        subprocess.run(
            [str(interpreter), '-m', 'pip', 'install', '-e', f'{package}[vector]'], check=True,
        )
        marker.write_text(requirements)
    subprocess.run([str(interpreter), str(Path(__file__).resolve())], check=True)


def rebuild_local_collection() -> dict:
    import pymupdf
    from finance_ai.vector_index import rebuild_index

    catalog = json.loads((ROOT / 'knowledge/catalogo.json').read_text(encoding='utf-8'))
    for source in catalog['sources']:
        sid = source['id']
        if sid not in PAGES or source['approved_for_ingestion']:
            continue
        citation = '. '.join(str(value) for value in (
            source['author'], source['title'], source['year'],
            source['origin']['url'] or source['canonical_path'],
        ) if value)
        note = 'Seleção para consulta acadêmica local, não comercial, sem distribuição do índice.'
        if sid == 'F024':
            note += ' Glossário histórico de 2006. Consultar a SUSEP atual para regras e procedimentos.'
            citation += '. Glossário histórico, edição de 2006'
        source['approved_for_ingestion'] = True
        source['ingestion_review'] = {
            'scope': 'academic_local',
            'pages': PAGES[sid],
            'evidence': note,
            'citation': citation + '. Trecho extraído e normalizado.',
        }
    approved = [source for source in catalog['sources'] if source['approved_for_ingestion']]
    if len(approved) != 20 or any(
        source['format'] != 'pdf' or source['status'] != 'identificado' for source in approved
    ):
        raise ValueError('a seleção acadêmica requer os 20 PDFs identificados')

    catalog_path = RUNTIME / 'catalogo-academico-local.json'
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Evita mensagens internas do MuPDF durante a reconstrução.
    pymupdf.TOOLS.mupdf_display_errors(False)
    report = rebuild_index(catalog_path, ROOT, DB, academic_local=True)
    if len(report.get('sources', [])) != len(approved):
        raise ValueError('o índice retornou uma seleção incompleta de fontes')
    report_path = RUNTIME / 'indice-academico-local.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> None:
    if Path(sys.prefix).resolve() != ENVIRONMENT.resolve():
        prepare_environment()
        return
    report = rebuild_local_collection()
    print(f"{len(report['sources'])} fontes, {report['chunks']} trechos, "
          f"{report['written_chunks']} novas gravações")
    print(report['collection'])


if __name__ == '__main__':
    main()
