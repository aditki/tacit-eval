import copy
import importlib
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage
from pydantic import ValidationError
import agent
import evaluate


class InvestigatorTests(unittest.TestCase):
    def state(self):
        return copy.deepcopy(agent.initial_state)

    def test_no_tool_calls_abstain_without_analysis(self):
        with patch.object(agent.ChatOllama, 'bind_tools') as bind, patch.object(agent.ChatOllama, 'with_structured_output', side_effect=AssertionError('analysis must not run')):
            bind.return_value.invoke.return_value = AIMessage(content='No tools')
            result = agent.graph.invoke(self.state())
        self.assertTrue(result['abstained'])
        self.assertIsNone(result['operational_bottleneck'])
        self.assertIn('payments-db', result['reasoning'])

    def test_complete_graph_preserves_evidence_and_analysis_configuration(self):
        state = self.state()
        state['scenario_id'] = 'clear_db'
        calls = [{'name':'get_metrics','args':{'service':name},'id':str(i)} for i, name in enumerate(state['candidates'])]
        with patch.object(agent, 'ChatOllama') as model:
            model.return_value.bind_tools.return_value.invoke.return_value = AIMessage(content='', tool_calls=calls)
            model.return_value.with_structured_output.return_value.invoke.return_value = agent.InvestigationResult(
                leading_candidate='payments-db', operational_bottleneck='payments-db', reasoning='DB saturation')
            result = agent.graph.invoke(state)
            self.assertEqual(model.call_args.kwargs['reasoning'], False)
        self.assertEqual(len(result['evidence']), 3)
        self.assertEqual(len(result['observations']), 4)
        self.assertEqual(result['culprit'], result['operational_bottleneck'])
        self.assertFalse(result['abstained'])

    def test_missing_evidence_reports_missing_only(self):
        state = self.state()
        state['evidence'] = [agent.Evidence(service='checkout-api', metrics={'cpu': '30%'}, tool_call_id='a')]
        self.assertFalse(agent.has_complete_evidence(state))
        result = agent.abstain_node(state)
        self.assertIn('payments-db', result['reasoning'])
        self.assertNotIn('checkout-api', result['reasoning'])

    def test_provenance_ignores_errors_unknown_calls_and_invalid_results(self):
        state = self.state()
        state['messages'] = [AIMessage(content='', tool_calls=[{'name':'get_metrics','args':{'service':'redis'},'id':'r'}]),
            ToolMessage(content='{"p95_latency":"9ms"}', tool_call_id='r'),
            ToolMessage(content='{"cpu":1}', tool_call_id='unknown'),
            ToolMessage(content='{}', tool_call_id='r'),
            ToolMessage(content='not json', tool_call_id='r'),
            ToolMessage(content='{"error":1}', tool_call_id='r', status='error')]
        evidence = agent.extract_evidence(state)['evidence']
        self.assertEqual(len(evidence), 1)
        self.assertEqual((evidence[0].service, evidence[0].tool_call_id), ('redis', 'r'))

    def test_normalization_and_units(self):
        state = self.state()
        state['evidence'] = [agent.Evidence(service='checkout-api', tool_call_id='a', metrics={
            'p95_latency':'145ms','baseline_p95_latency':'150ms',
            'error_rate':'0.1%','baseline_error_rate':'0.1%',
            'query_latency':'2s','baseline_query_latency':'40ms'})]
        observations = agent.normalize_evidence(state)['observations']
        self.assertEqual([(o.deviation_pct, o.direction) for o in observations], [(-3.33,'decreased'),(0,'unchanged'),(4900,'increased')])
        self.assertTrue(all(o.tool_call_id == 'a' for o in observations))
        with self.assertRaises(ValueError): agent.calculate_deviation(1, 0)
        state['evidence'][0].metrics = {'x':'1ms','baseline_x':'1%'}
        with self.assertRaises(ValueError): agent.normalize_evidence(state)

    def test_validation_rejects_contradictions_and_unknown_services(self):
        with self.assertRaises(ValidationError):
            agent.InvestigationResult(leading_candidate='redis', operational_bottleneck='payments-db', reasoning='x')
        with patch.object(agent.ChatOllama, 'with_structured_output') as structured:
            structured.return_value.invoke.return_value = agent.InvestigationResult(leading_candidate='invented', operational_bottleneck=None, reasoning='x')
            with self.assertRaises(ValueError): agent.analyze_evidence(self.state())

    def test_fixture_context_is_app_controlled(self):
        runtime = SimpleNamespace(state={'scenario_id':'healthy'})
        result = agent.get_metrics.func('payments-db', runtime)
        self.assertEqual(result['query_latency'], '38ms')
        with self.assertRaises(ValueError):
            agent.get_metrics.func('payments-db', SimpleNamespace(state={'scenario_id':'../secret'}))

    def test_evaluators_handle_failed_runs_and_missing_references(self):
        for value in (None, {}, [], ''):
            self.assertFalse(evaluate.execution_success(value)['score'])
            self.assertFalse(evaluate.culprit_correct(value, None)['score'])
            self.assertFalse(evaluate.abstention_correct(value, None)['score'])
        good = {'leading_candidate':None,'culprit':None,'abstained':True,'reasoning':'Healthy'}
        self.assertTrue(evaluate.execution_success(good)['score'])
        self.assertTrue(evaluate.culprit_correct(good, {'culprit':None})['score'])
        self.assertTrue(evaluate.abstention_correct(good, {'abstained':True})['score'])
        self.assertFalse(evaluate.culprit_correct(good, {})['score'])
        self.assertFalse(evaluate.abstention_correct({**good,'abstained':1}, {'abstained':True})['score'])
        self.assertFalse(evaluate.execution_success({**good,'culprit':'redis'})['score'])

    def test_imports_do_not_start_network_work(self):
        with patch('langsmith.Client', side_effect=AssertionError('Client constructed on import')), patch.object(agent.ChatOllama,'invoke', side_effect=AssertionError('Model invoked on import')):
            import create_dataset
            importlib.reload(create_dataset)
            importlib.reload(evaluate)


if __name__ == '__main__':
    unittest.main()
