"""Confere evidências, abstenções e falhas do relatório da variante RAG."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from finance_ai.llm_rag import ABSTENTION, GENERATION_ABSTENTION, run_rag


class RagEvaluationTest(unittest.TestCase):
    def test_preserves_evidence_and_abstains_with_missing_or_invalid_citations(self):
        evidence = [{
            'chunk_id': 'trecho-ficticio', 'document_id': 'SYN001',
            'source_sha256': 'a' * 64, 'page_number': 2, 'start': 0, 'end': 19,
            'text': 'Trecho de exemplo.', 'score': 0.91,
        }]
        found = {'status': 'ok', 'evidencias': evidence, 'error': None}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / 'dataset.json'
            dataset.write_text(json.dumps({
                'dataset_version': 'teste', 'cases': [
                    {'id': f'SYN-{i}', 'split': 'calibracao', 'question': f'Caso fictício {i}?'}
                    for i in range(6)
                ],
            }))
            with (
                patch('finance_ai.llm_rag.search_evidence', side_effect=[
                    found, {'status': 'no_results', 'evidencias': [], 'error': None},
                    found, {'status': 'error', 'evidencias': [], 'error': 'index_not_found'},
                    found, found,
                ]) as lookup,
                patch('finance_ai.llm_baseline._request', side_effect=[
                    {'version': '0.0.1'},
                    {'models': [{'name': 'qwen2.5:0.5b', 'digest': 'ficticio'}]},
                    {'done': True, 'message': {'content': 'Resposta [1].'}, 'done_reason': 'stop'},
                    {'done': True, 'message': {'content': 'Citação [9].'}, 'done_reason': 'stop'},
                    {'done': True, 'message': {'content': 'Resposta cortada [1]'},
                     'done_reason': 'length'},
                    TimeoutError('tempo esgotado'),
                ]) as request,
            ):
                path, failures = run_rag(dataset, root, db_path=root / 'chroma', collection='fixture')
            run, ok, empty, invalid, failed, truncated, timeout, summary = [
                json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
            ]

        self.assertEqual(run['variant'], 'llm_rag')
        self.assertEqual(run['retrieval']['collection'], 'fixture')
        self.assertEqual(run['prompt_id'], 'direto-v2')
        self.assertEqual(lookup.call_count, 6)
        self.assertEqual(request.call_count, 6)
        self.assertIn('[1] Trecho de exemplo.', request.call_args_list[2].args[-1]['messages'][1]['content'])
        self.assertEqual(ok['evidence'], evidence)
        self.assertEqual(ok['citations'], [{'number': 1, 'chunk_id': 'trecho-ficticio',
                                           'document_id': 'SYN001', 'page_number': 2}])
        self.assertEqual(empty['response'], ABSTENTION)
        self.assertEqual(empty['status'], 'abstained')
        self.assertIsNone(empty['generation_ms'])
        self.assertEqual(invalid['response'], GENERATION_ABSTENTION)
        self.assertEqual(invalid['raw_response'], 'Citação [9].')
        self.assertEqual(invalid['abstention_reason'], 'invalid_citations')
        self.assertEqual(truncated['abstention_reason'], 'generation_truncated')
        self.assertEqual(timeout['evidence'], evidence)
        self.assertEqual(timeout['error']['stage'], 'generation')
        self.assertEqual(failed['error'], {'stage': 'retrieval', 'code': 'index_not_found'})
        self.assertEqual(summary, {
            'type': 'summary', 'planned': 6, 'ok': 1, 'errors': 2,
            'not_run': 0, 'abstained': 3,
        })
        self.assertEqual(failures, 2)
