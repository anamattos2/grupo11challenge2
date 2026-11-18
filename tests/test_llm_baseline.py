"""Confere o registro do baseline com respostas e falhas fictícias."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from finance_ai.llm_baseline import OPTIONS, PROMPTS, run_baseline


class BaselineTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.dataset = self.root / 'dataset.json'
        cases = [
            {'id': 'CAL-01', 'split': 'calibracao', 'question': 'Pergunta fictícia 1?'},
            {'id': 'CAL-02', 'split': 'calibracao', 'question': 'Pergunta fictícia 2?'},
            {'id': 'AVA-01', 'split': 'avaliacao', 'question': 'Caso reservado?'},
        ]
        self.dataset.write_text(json.dumps({'dataset_version': '1.0.0', 'cases': cases}))

    def test_preserves_requests_responses_and_partial_failure(self):
        with patch('finance_ai.llm_baseline._request', side_effect=[
            {'version': '0.0.1'},
            {'models': [{'name': 'qwen2.5:0.5b', 'digest': 'ficticio'}]},
            {'done': True, 'message': {'content': 'Resposta fictícia.'}, 'done_reason': 'stop'},
            TimeoutError('tempo esgotado'),
        ]) as request:
            path, failures = run_baseline(self.dataset, self.root, prompt='direto-v2')
        run, first, second, summary = [
            json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
        ]
        self.assertEqual(run['model']['digest'], 'ficticio')
        self.assertEqual(run['dataset']['split'], 'calibracao')
        self.assertEqual(run['prompt_id'], 'direto-v2')
        self.assertEqual(run['system_prompt'], PROMPTS['direto-v2'])
        self.assertEqual(request.call_args_list[2].args[-1], {
            'model': 'qwen2.5:0.5b', 'stream': False, 'options': OPTIONS,
            'messages': [
                {'role': 'system', 'content': PROMPTS['direto-v2']},
                {'role': 'user', 'content': 'Pergunta fictícia 1?'},
            ],
        })
        self.assertEqual(first['response'], 'Resposta fictícia.')
        self.assertEqual(second['error']['type'], 'TimeoutError')
        self.assertGreaterEqual(first['latency_ms'], 0)
        self.assertGreaterEqual(second['latency_ms'], 0)
        self.assertEqual(summary, {'type': 'summary', 'planned': 2, 'ok': 1, 'errors': 1, 'not_run': 0})
        self.assertEqual(failures, 1)

    def test_startup_failure_records_each_reserved_case(self):
        with patch('finance_ai.llm_baseline._request', side_effect=ConnectionRefusedError):
            path, failures = run_baseline(self.dataset, self.root, split='avaliacao')
            second_path, _ = run_baseline(self.dataset, self.root, split='avaliacao')
        run, case, summary = [
            json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
        ]
        self.assertEqual(run['startup_error']['type'], 'ConnectionRefusedError')
        self.assertEqual(run['prompt_id'], 'original-v1')
        self.assertEqual(case['id'], 'AVA-01')
        self.assertEqual(case['status'], 'not_run')
        self.assertIsNone(case['latency_ms'])
        self.assertEqual(summary['not_run'], 1)
        self.assertEqual(failures, 1)
        self.assertNotEqual(path, second_path)
