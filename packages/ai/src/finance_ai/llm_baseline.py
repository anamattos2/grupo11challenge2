"""Executa a variante de LLM puro do dataset RAG com um Ollama local."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection, HTTPException
import json
from pathlib import Path
import platform
import subprocess
from tempfile import NamedTemporaryFile
from time import perf_counter


SYSTEM_PROMPT = (
    'Você responde perguntas de educação financeira em português do Brasil. '
    'Responda de forma direta. Se faltarem informações para responder, diga quais. '
    'Se o pedido estiver fora da educação financeira, explique o limite. '
    'Não invente dados pessoais e não afirme ter acessado contas ou realizado ações.'
)
PROMPTS = {
    'original-v1': SYSTEM_PROMPT,
    'direto-v2': (
        'Você atende apenas perguntas de educação financeira. Escreva em português do Brasil '
        'e use no máximo três frases. Antes de responder, identifique a situação:\n'
        '1. Pedido fora de educação financeira ou para executar uma ação: diga que está fora '
        'do escopo e encerre.\n'
        '2. Faltam dados para concluir: diga qual dado falta e faça uma pergunta objetiva '
        'para obtê-lo. Não estime valores nem afirme ter consultado registros.\n'
        '3. Pergunta educativa com informação suficiente: responda diretamente, justifique '
        'em uma frase e encerre. Evite acrescentar regras, garantias ou condições sem apoio.'
    ),
}
OPTIONS = {'temperature': 0, 'seed': 42, 'num_predict': 256, 'num_ctx': 2048}
SPLITS = ('calibracao', 'avaliacao')
REQUEST_ERRORS = (OSError, HTTPException, ValueError, KeyError, TypeError)


def _request(port: int, timeout: float, path: str, payload: dict | None = None) -> dict:
    connection = HTTPConnection('127.0.0.1', port, timeout=timeout)
    try:
        if payload is None:
            connection.request('GET', path)
        else:
            connection.request(
                'POST', path, body=json.dumps(payload),
                headers={'Content-Type': 'application/json'},
            )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f'Ollama respondeu HTTP {response.status} em {path}')
        data = json.loads(response.read())
        if not isinstance(data, dict):
            raise ValueError('resposta Ollama precisa ser um objeto JSON')
        return data
    finally:
        connection.close()


def _read_cases(path: Path, split: str) -> tuple[dict, list]:
    if split not in SPLITS:
        raise ValueError(f'partição inválida: {split}')
    raw = path.read_bytes()
    dataset = json.loads(raw)
    cases = [
        {'id': case['id'], 'question': case['question']} for case in dataset['cases']
        if case['split'] == split
    ]
    if not cases or any(
        not isinstance(case['id'], str) or not case['id'].strip()
        or not isinstance(case['question'], str) or not case['question'].strip()
        for case in cases
    ):
        raise ValueError('a partição precisa conter IDs e perguntas preenchidos')
    if len({case['id'] for case in cases}) != len(cases):
        raise ValueError('a partição tem IDs duplicados')
    metadata = {
        'path': str(path), 'version': dataset['dataset_version'],
        'sha256': hashlib.sha256(raw).hexdigest(), 'split': split,
    }
    return metadata, cases


def _code_version() -> dict:
    try:
        commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL, text=True,
        ).strip()
        dirty = bool(subprocess.check_output(
            ['git', 'status', '--porcelain'], stderr=subprocess.DEVNULL, text=True,
        ).strip())
        return {'commit': commit, 'dirty': dirty}
    except (OSError, subprocess.CalledProcessError):
        return {'commit': None, 'dirty': None}


def run_baseline(
    dataset_path: Path,
    output_dir: Path,
    *,
    split: str = 'calibracao',
    model: str = 'qwen2.5:0.5b',
    prompt: str = 'original-v1',
    port: int = 11434,
    timeout: float = 120,
) -> tuple[Path, int]:
    """Grava metadados, uma linha por caso e um resumo de execução em JSONL."""
    return _run_evaluation(
        dataset_path, output_dir, split=split, model=model, prompt=prompt, port=port,
        timeout=timeout, variant='llm_puro', case_handler=_baseline_case,
    )


def _baseline_case(question, generate) -> dict:
    return {'status': 'ok', **generate(question)}


def _run_evaluation(
    dataset_path, output_dir, *, split, model, prompt, port, timeout,
    variant, case_handler, metadata=None,
) -> tuple[Path, int]:
    if not 1 <= port <= 65535 or not 0 < timeout < float('inf'):
        raise ValueError('porta ou timeout inválido')
    if prompt not in PROMPTS:
        raise ValueError(f'prompt inválido: {prompt}')
    system_prompt = PROMPTS[prompt]
    dataset, cases = _read_cases(dataset_path, split)
    started = datetime.now(timezone.utc)
    model_info = {'name': model, 'digest': None, 'details': None, 'ollama_version': None}
    startup_error = None
    try:
        model_info['ollama_version'] = _request(port, timeout, '/api/version')['version']
        models = _request(port, timeout, '/api/tags')['models']
        selected = next((item for item in models if item['name'] == model), None)
        if selected is None or not selected['digest'] or selected.get('remote_host'):
            raise ValueError(f'modelo local indisponível: {model}; confira ollama list')
        model_info.update(digest=selected['digest'], details=selected.get('details'))
    except REQUEST_ERRORS as exc:
        startup_error = {'type': type(exc).__name__, 'message': str(exc)}

    def generate(question: str, instruction: str = '') -> dict:
        result = _request(port, timeout, '/api/chat', {
            'model': model, 'stream': False, 'options': OPTIONS,
            'messages': [
                {'role': 'system', 'content': system_prompt + instruction},
                {'role': 'user', 'content': question},
            ],
        })
        content = result['message']['content']
        if result['done'] is not True or not isinstance(content, str) or not content.strip():
            raise ValueError('geração incompleta ou resposta vazia')
        return {'response': content, 'done_reason': result.get('done_reason')}

    output_dir.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode='w', encoding='utf-8', dir=output_dir, delete=False, suffix='.jsonl',
        prefix=f"{variant.replace('_', '-')}-{split}-{started:%Y%m%dT%H%M%SZ}-",
    ) as output:
        def write(record: dict) -> None:
            output.write(json.dumps(record, ensure_ascii=False) + '\n')
            output.flush()

        write({
            'type': 'run', 'schema_version': 1, 'variant': variant,
            'started_at': started.isoformat(), 'dataset': dataset,
            'code': _code_version(), 'environment': {
                'platform': platform.platform(), 'python': platform.python_version(),
            },
            'model': model_info, 'prompt_id': prompt, 'system_prompt': system_prompt,
            'options': OPTIONS,
            'timeout_seconds': timeout, 'planned_cases': len(cases),
            'startup_error': startup_error,
            **(metadata or {}),
        })
        counts = Counter()
        for case in cases:
            record = {
                'type': 'case', **case, 'status': 'not_run', 'latency_ms': None,
                'response': None, 'done_reason': None, 'error': startup_error,
            }
            if startup_error is None:
                start = perf_counter()
                try:
                    record.update(case_handler(case['question'], generate))
                except REQUEST_ERRORS as exc:
                    record.update(status='error', error={'type': type(exc).__name__, 'message': str(exc)})
                record['latency_ms'] = round((perf_counter() - start) * 1000, 3)
            counts[record['status']] += 1
            write(record)

        write({
            'type': 'summary', 'planned': len(cases), 'ok': counts['ok'],
            'errors': counts['error'], 'not_run': counts['not_run'],
            **({'abstained': counts['abstained']} if variant == 'llm_rag' else {}),
        })
        return Path(output.name), counts['error'] + counts['not_run']


def _evaluation_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--dataset', type=Path, default=Path('evaluations/rag/dataset.json'))
    parser.add_argument('--output-dir', type=Path, default=Path('.runtime/avaliacoes'))
    parser.add_argument('--split', choices=SPLITS, default='calibracao')
    parser.add_argument('--model', default='qwen2.5:0.5b', help='tag exata do modelo em ollama list')
    parser.add_argument('--prompt', choices=PROMPTS, default='original-v1')
    parser.add_argument('--port', type=int, default=11434)
    parser.add_argument('--timeout', type=float, default=120)
    return parser


def main() -> int:
    parser = _evaluation_parser(__doc__)
    args = parser.parse_args()
    try:
        path, failures = run_baseline(
            args.dataset, args.output_dir, split=args.split, model=args.model,
            prompt=args.prompt, port=args.port, timeout=args.timeout,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(path)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
