"""Verifica seleção de frases e proveniência numa coleção fictícia."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from finance_ai.llm_rag_explained import (
    OUTPUT_FORMAT, _sentence_context, _structured_response, run_rag_explained,
)


EVIDENCE = [{
    'chunk_id': 'trecho-ficticio', 'document_id': 'SYN001',
    'source_sha256': 'a' * 64, 'page_number': 2, 'start': 0, 'end': 31,
    'text': 'Receitas são\nentradas de caixa.', 'score': 0.91,
}]


def generated(ids, missing=None):
    return {
        'response': json.dumps({'sentence_ids': ids, 'missing_information': missing or []}),
        'done_reason': 'stop',
    }


class RagExplanationTest(unittest.TestCase):
    def test_keeps_selected_sentence_and_reports_unknown_id(self):
        _, candidates = _sentence_context(EVIDENCE)
        result = _structured_response(generated([1, 9], ['Valor recebido no período']), candidates)
        self.assertEqual(result['response'], 'Receitas são entradas de caixa. [1]')
        explanation = result['explanation']
        supported, unsupported = explanation['claims']
        self.assertEqual(supported['status'], 'supported')
        self.assertEqual(supported['evidence'][0]['document_id'], 'SYN001')
        self.assertEqual(supported['evidence'][0]['page_number'], 2)
        self.assertEqual(supported['evidence'][0]['source_sha256'], 'a' * 64)
        self.assertEqual(unsupported['reason'], 'invalid_sentence_id')
        self.assertEqual(unsupported['evidence'], [])
        self.assertEqual(explanation['missing_information'], ['Valor recebido no período'])
        self.assertTrue(explanation['limits'])

    def test_no_selection_preserves_missing_information(self):
        result = _structured_response(generated([], ['Total das despesas']), [])
        self.assertEqual(result['status'], 'abstained')
        self.assertEqual(result['explanation']['missing_information'], ['Total das despesas'])

    def test_invalid_or_truncated_generation_abstains(self):
        for done, reason in [('stop', 'invalid_explanation'), ('length', 'generation_truncated')]:
            with self.subTest(done=done):
                result = _structured_response({'response': '{', 'done_reason': done}, [])
                self.assertEqual(result['status'], 'abstained')
                self.assertEqual(result['abstention_reason'], reason)
                self.assertTrue(result['explanation']['limits'])

    def test_sentence_boundaries_offsets_and_deduplication(self):
        chunk = {**EVIDENCE[0], 'start': 15,
                 'text': 'fragmento anterior. Dr. Silva exemplificou. Outro fragmento'}
        snippets, candidates = _sentence_context([chunk, chunk])
        self.assertEqual(snippets, '[1] Dr. Silva exemplificou.')
        self.assertEqual(len(candidates), 1)
        ref = candidates[0]['evidence']
        self.assertEqual(ref['number'], 1)
        self.assertEqual(chunk['text'][ref['start']-15:ref['end']-15], 'Dr. Silva exemplificou.')

    def test_run_preserves_schema_and_skips_generation_without_complete_sentences(self):
        answer = generated([1])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / 'dataset.json'
            dataset.write_text(json.dumps({
                'dataset_version': 'teste', 'cases': [
                    {'id': str(i), 'split': 'calibracao', 'question': f'Pergunta {i}?'}
                    for i in range(3)
                ],
            }))
            with (
                patch('finance_ai.llm_rag.search_evidence', side_effect=[
                    {'status': 'ok', 'evidencias': EVIDENCE, 'error': None},
                    {'status': 'no_results', 'evidencias': [], 'error': None},
                    {'status': 'ok', 'evidencias': [{**EVIDENCE[0], 'text': 'Trecho sem fim'}],
                     'error': None},
                ]),
                patch('finance_ai.llm_baseline._request', side_effect=[
                    {'version': '0.0.1'},
                    {'models': [{'name': 'qwen2.5:0.5b', 'digest': 'ficticio'}]},
                    {'done': True, 'message': {'content': answer['response']}, 'done_reason': 'stop'},
                ]) as request,
            ):
                path, failures = run_rag_explained(
                    dataset, root, db_path=root / 'chroma', collection='fixture',
                )
            run, first, second, third, summary = [
                json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
            ]
        self.assertEqual(failures, 0)
        self.assertEqual(run['variant'], 'llm_rag_explicacao')
        self.assertEqual(run['output_format'], OUTPUT_FORMAT)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(request.call_args.args[-1]['format'], OUTPUT_FORMAT)
        self.assertIn('[1] Receitas são entradas de caixa.',
                      request.call_args.args[-1]['messages'][1]['content'])
        self.assertEqual(first['evidence'], EVIDENCE)
        self.assertEqual(second['abstention_reason'], 'no_results')
        self.assertEqual(third['abstention_reason'], 'no_complete_sentences')
        self.assertIsNone(second['generation_ms'])
        self.assertIsNone(third['generation_ms'])
        self.assertEqual(summary['ok'], 1)
        self.assertEqual(summary['abstained'], 2)
