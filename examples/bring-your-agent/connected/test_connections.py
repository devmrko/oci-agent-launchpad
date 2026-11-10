import asyncio
import json
import os
from unittest import TestCase,main
from unittest.mock import patch
import connections as c

class ConnectionTests(TestCase):
    def test_rejects_unapproved_tools_and_arguments(self):
        for decision in ({'tool':'shell','arguments':{}},{'tool':'multiply','arguments':{'a':True,'b':7}},{'tool':'multiply','arguments':{'a':1001,'b':7}}):
            with self.assertRaises(ValueError):c.validate(json.dumps(decision))
        for url in ('http://remote.example/mcp','https://user:pass@example.com/mcp','https://example.com/mcp?key=x'):
            with self.assertRaises(ValueError):c.endpoint(url)

    def test_model_timeout_does_not_call_tool_or_leak_error(self):
        with patch.object(c,'plan',side_effect=TimeoutError('private-key')),patch.object(c,'call_tool') as tool,patch.object(c,'export',return_value='disabled'),patch('builtins.print'):
            result=c.run('private input','a'*32)
        self.assertEqual(result['error'],'MODEL_FAILED');tool.assert_not_called()
        self.assertNotIn('private',json.dumps(result))

    def test_failed_telemetry_does_not_turn_success_into_failure(self):
        async def tool(_):return {'result':42}
        with patch.object(c,'plan',return_value=({'tool':'multiply','arguments':{'a':6,'b':7}},{'total_tokens':15})),patch.object(c,'call_tool',side_effect=tool),patch.object(c,'export',return_value='failed'),patch('builtins.print'):
            result=c.run('private input','a'*32)
        self.assertEqual(result['answer'],'42');self.assertEqual(result['telemetry'],'failed')
        self.assertEqual(result['status'],'SUCCEEDED')

    def test_export_contains_model_and_usage_but_no_prompt(self):
        with patch.dict(os.environ,{'AGENT_LANGFUSE_URL':'http://127.0.0.1:18080','AGENT_LANGFUSE_PUBLIC':'public','AGENT_LANGFUSE_SECRET':'secret','AGENT_MODEL':'model'}),patch.object(c.httpx,'Client') as client:
            client.return_value.__enter__.return_value.post.return_value.json.return_value={}
            status=c.export('a'*32,[{'stage':'model','start_ns':1,'end_ns':2,'duration_ms':1,'status':'SUCCEEDED'}],'SUCCEEDED',{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15})
            payload=client.return_value.__enter__.return_value.post.call_args.kwargs['json']
        self.assertEqual(status,'exported')
        attrs=payload['resourceSpans'][0]['scopeSpans'][0]['spans'][1]['attributes']
        self.assertIn({'key':'langfuse.observation.model.name','value':{'stringValue':'model'}},attrs)
        self.assertTrue(any(a['key']=='langfuse.observation.usage_details' for a in attrs))
        self.assertNotIn('secret',json.dumps(payload));self.assertNotIn('observation.input',json.dumps(payload))

if __name__=='__main__':main()
