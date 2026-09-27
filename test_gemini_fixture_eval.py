"""Gemini checks use only authored fixture data and mocked HTTP transport."""
import ast
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import gemini_fixture_eval as evaluation


def envelope(findings, finish='completed'):
    return json.dumps({'status': finish, 'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': json.dumps({'findings': findings})}]}]}).encode()


def fixture_output():
    _, expected = evaluation._fixture()
    return [{key: item[key] for key in ('category', 'value', 'source_url')} for item in expected]


class GeminiFixtureTests(unittest.TestCase):
    def test_offline_mocked_fixture_needs_no_key_or_network(self):
        with patch.dict(os.environ, {}, clear=True), patch('gemini_fixture_eval.http.client.HTTPSConnection') as connection:
            result = evaluation.evaluate_fixture()
            connection.assert_not_called()
        self.assertFalse(result['network_verified'])
        self.assertGreater(result['accepted_findings'], 5)
        self.assertEqual(result['accepted_findings'], result['expected_findings'])
        for finding in result['findings']:
            self.assertIn('demo.corporatemapper.invalid', finding['source_url'])
            self.assertIn('observed_at', finding)
            self.assertNotIn('gemini', finding['method'])

    def test_live_fixture_uses_structured_schema_one_call_and_validates_source(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'synthetic-key', 'GEMINI_MODEL': 'gemini-2.5-flash'}), patch('gemini_fixture_eval.http.client.HTTPSConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status, response.read.return_value = 200, envelope(fixture_output())
            result = evaluation.evaluate_fixture(live=True)
            request = connection.return_value.request
            request.assert_called_once()
            self.assertEqual(request.call_args.args[1], '/v1beta/interactions')
            payload = json.loads(request.call_args.args[2])
            format_config = payload['response_format']
            self.assertEqual(format_config['mime_type'], 'application/json')
            self.assertEqual(format_config['schema']['properties']['findings']['items']['required'], ['category', 'value', 'source_url'])
            self.assertEqual(payload['model'], 'gemini-2.5-flash')
            self.assertFalse(payload['store'])
            self.assertEqual(payload['generation_config']['max_output_tokens'], 4096)
            self.assertEqual(payload['generation_config']['thinking_level'], 'low')
            self.assertNotIn('additionalProperties', format_config['schema'])
            self.assertNotIn('maxItems', format_config['schema']['properties']['findings'])
            self.assertIn('fictional demo person', payload['input'])
            connection.return_value.close.assert_called_once()
        self.assertTrue(result['network_verified'])
        self.assertGreater(result['accepted_findings'], 0)

    def test_current_default_works_without_model_override(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'synthetic-key'}, clear=True), patch('gemini_fixture_eval.http.client.HTTPSConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status, response.read.return_value = 200, envelope(fixture_output())
            result = evaluation.evaluate_fixture(live=True)
            self.assertEqual(result['model'], 'gemini-3.8-flash')
            self.assertEqual(connection.return_value.request.call_args.args[1], '/v1beta/interactions')
            connection.return_value.request.assert_called_once()

    def test_model_404_explains_access_and_env_precedence_without_leaking_body(self):
        cases = [
            (json.dumps({'error': {'message': 'This model is no longer available to new users. synthetic-secret'}}).encode(), 'new users'),
            (b'{"error":{"message":"synthetic-secret"}}', 'unavailable'),
            (b'[]', 'unavailable'),
            (b'not JSON synthetic-secret', 'unavailable'),
        ]
        for body, expected in cases:
            with self.subTest(body=body), patch.dict(os.environ, {'GEMINI_API_KEY':'synthetic-key','GEMINI_MODEL':'gemini-2.5-flash'}), patch('gemini_fixture_eval.http.client.HTTPSConnection') as connection:
                response = connection.return_value.getresponse.return_value
                response.status, response.read.return_value = 404, body
                with self.assertRaises(evaluation.GeminiError) as caught:
                    evaluation.evaluate_fixture(live=True)
                message = str(caught.exception)
                self.assertIn(expected, message)
                self.assertIn('gemini-2.5-flash', message)
                self.assertIn('GEMINI_MODEL', message)
                self.assertIn('overrides .env', message)
                self.assertNotIn('synthetic-secret', message)
                connection.return_value.request.assert_called_once()
                connection.return_value.close.assert_called_once()

    def test_missing_key_and_invalid_model_fail_before_request(self):
        for config, message in [({'GEMINI_API_KEY': ''}, 'GEMINI_API_KEY'),
            ({'GEMINI_API_KEY': 'fixture-key', 'GEMINI_MODEL': 'https://evil.invalid/'}, 'model identifier')]:
            with self.subTest(config=config), patch.dict(os.environ, config, clear=True), patch('gemini_fixture_eval.http.client.HTTPSConnection') as connection:
                with self.assertRaisesRegex(evaluation.GeminiError, message):
                    evaluation.evaluate_fixture(live=True)
                connection.assert_not_called()

    def test_quota_error_and_network_failure_have_no_retry_or_secret(self):
        for status in [402, 429, 500]:
            with self.subTest(status=status), patch.dict(os.environ, {'GEMINI_API_KEY': 'synthetic-key'}), patch('gemini_fixture_eval.http.client.HTTPSConnection') as connection:
                response = connection.return_value.getresponse.return_value
                response.status, response.read.return_value = status, b'synthetic-secret'
                error = evaluation.GeminiQuotaError if status in {402,429} else evaluation.GeminiError
                with self.assertRaises(error) as caught:
                    evaluation.evaluate_fixture(live=True)
                self.assertNotIn('synthetic-secret', str(caught.exception))
                connection.return_value.request.assert_called_once()
                connection.return_value.close.assert_called_once()
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'synthetic-key'}), patch('gemini_fixture_eval.http.client.HTTPSConnection') as connection:
            connection.return_value.request.side_effect = TimeoutError('synthetic-secret')
            with self.assertRaisesRegex(evaluation.GeminiError, 'no retry'):
                evaluation.evaluate_fixture(live=True)
            connection.return_value.request.assert_called_once()

    def test_missing_malformed_unsupported_and_truncated_responses_fail(self):
        output = fixture_output()
        bad_source = dict(output[0], source_url='https://unrelated.invalid/')
        bad_value = dict(output[0], value='A claim absent from the source')
        bad_category = dict(output[0], category='religion')
        cases = [b'not json', b'{}', b'[]', envelope([], 'incomplete'), envelope([]),
                 envelope([output[0]] * 101), envelope(output, 'incomplete'),
                 envelope([bad_source]), envelope([bad_value]), envelope([bad_category]), envelope([dict(output[0], secret='extra')])]
        for body in cases:
            with self.subTest(body=body[:70]), patch.dict(os.environ, {'GEMINI_API_KEY': 'synthetic-key'}), patch('gemini_fixture_eval.http.client.HTTPSConnection') as connection:
                response = connection.return_value.getresponse.return_value
                response.status, response.read.return_value = 200, body
                with self.assertRaises(evaluation.GeminiError):
                    evaluation.evaluate_fixture(live=True)

    def test_thoughts_are_ignored_and_malformed_steps_fail(self):
        body = json.loads(envelope(fixture_output()))
        body['steps'].insert(0, {'type': 'thought', 'content': [{'type': 'text', 'text': 'not JSON'}]})
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'synthetic-key'}), patch('gemini_fixture_eval.http.client.HTTPSConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status, response.read.return_value = 200, json.dumps(body).encode()
            self.assertGreater(evaluation.evaluate_fixture(live=True)['accepted_findings'], 0)
            for steps in [None, [], [None], [{'type': 'model_output', 'content': None}], body['steps'] * 2]:
                response.read.return_value = json.dumps({'status': 'completed', 'steps': steps}).encode()
                with self.assertRaises(evaluation.GeminiError):
                    evaluation.evaluate_fixture(live=True)

    def test_deduplication_preserves_original_support(self):
        page, expected = evaluation._fixture()
        item = {key: expected[0][key] for key in ('category','value','source_url')}
        accepted = evaluation._validate_response({'findings': [item,item]}, expected)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]['source_url'], page.final_url)
        self.assertEqual(accepted[0]['method'], expected[0]['method'])

    def test_cli_accepts_no_arbitrary_person_source_or_file(self):
        for args in [['--demo', '--person', 'someone'], ['--demo', '--source', 'https://example.com'], ['--demo', '--file', '/tmp/people.json']]:
            with self.subTest(args=args), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                evaluation.main(args)
            self.assertEqual(caught.exception.code, 2)
        with self.assertRaises(TypeError):
            evaluation.evaluate_fixture(person='someone')

    def test_production_source_modules_do_not_import_gemini(self):
        for filename in ['enrichment_sources.py', 'enrichment_demo.py', 'enrichment_policy.py', 'api.py', 'pipeline.py']:
            tree = ast.parse(Path(filename).read_text())
            imported = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            imported += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
            self.assertFalse(any('gemini' in (module or '').lower() for module in imported), filename)


if __name__ == '__main__':
    unittest.main()
