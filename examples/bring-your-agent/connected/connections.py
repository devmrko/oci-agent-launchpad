"""App-owned connections for the bounded calculator example, not a platform SDK."""
import asyncio
import json
import os
import re
import time
from urllib.parse import urlsplit
import httpx

PROMPT = ('Select the multiply tool for a multiplication request. Return ONLY JSON '
          '{"tool":"multiply","arguments":{"a":6,"b":7}} with the requested integers. '
          'Both integers must be within -1000..1000. No other tools, keys, code or markdown.')


def endpoint(value):
    url=urlsplit(value)
    if url.username or url.password or url.query or url.fragment or not url.hostname:
        raise ValueError('Invalid configured endpoint')
    if url.scheme!='https' and not (url.scheme=='http' and url.hostname in {'127.0.0.1','localhost','::1'}):
        raise ValueError('HTTPS required outside loopback')
    return value.rstrip('/')


def plan(message):
    provider=os.environ['AGENT_PROVIDER'];model=os.environ['AGENT_MODEL']
    usage={}
    if provider=='oci-sdk':
        import oci
        from oci.generative_ai_inference import models as m
        region=os.environ['AGENT_OCI_REGION']
        if not re.fullmatch(r'[a-z]+-[a-z]+-\d+',region):raise ValueError('Invalid region')
        config=oci.config.from_file(file_location=os.environ['AGENT_OCI_CONFIG'],profile_name=os.environ.get('AGENT_OCI_PROFILE','DEFAULT'))
        config['region']=region
        client=oci.generative_ai_inference.GenerativeAiInferenceClient(config,
            service_endpoint=f'https://inference.generativeai.{region}.oci.oraclecloud.com',
            timeout=(3,20),retry_strategy=oci.retry.NoneRetryStrategy())
        try:
            response=client.chat(m.ChatDetails(compartment_id=os.environ['AGENT_OCI_COMPARTMENT'],
                serving_mode=m.OnDemandServingMode(model_id=model),chat_request=m.GenericChatRequest(
                    max_tokens=256,temperature=0,messages=[m.SystemMessage(content=[m.TextContent(text=PROMPT)]),m.UserMessage(content=[m.TextContent(text=message)])])))
            data=oci.util.to_dict(response.data.chat_response);choice=data['choices'][0]
            if choice.get('finish_reason')!='stop':raise ValueError('Incomplete model output')
            raw=''.join(c['text'] for c in choice['message']['content'] if c['type']=='TEXT')
            # Provider SDK versions differ; report only available numeric counts.
            for name in ('prompt_tokens','completion_tokens','total_tokens'):
                if type((data.get('usage') or {}).get(name)) is int:usage[name]=data['usage'][name]
        finally:client.base_client.session.close()
    elif provider=='openai-compatible':
        base=endpoint(os.environ['AGENT_BASE_URL'])
        auth_mode=os.environ.get('AGENT_OPENAI_AUTH','api-key');options={}
        if auth_mode=='api-key':options['headers']={'Authorization':'Bearer '+os.environ['AGENT_API_KEY']}
        elif auth_mode=='oci-config':
            from oci_genai_auth import OciUserPrincipalAuth
            options['auth']=OciUserPrincipalAuth(config_file=os.environ['AGENT_OCI_CONFIG'],profile_name=os.environ.get('AGENT_OCI_PROFILE','DEFAULT'))
        else:raise ValueError('Unsupported authentication mode')
        if os.environ.get('AGENT_OCI_COMPARTMENT'):
            options.setdefault('headers',{})['CompartmentId']=os.environ['AGENT_OCI_COMPARTMENT']
        with httpx.Client(timeout=httpx.Timeout(20,connect=3),follow_redirects=False,trust_env=False,**options) as client:
            response=client.post(base+'/chat/completions',json={
                'model':model,'max_tokens':256,'temperature':0,
                'messages':[{'role':'system','content':PROMPT},{'role':'user','content':message}]})
            response.raise_for_status();data=response.json();choice=data['choices'][0]
            if choice.get('finish_reason')!='stop':raise ValueError('Incomplete model output')
            raw=choice['message']['content']
            usage={k:v for k,v in data.get('usage',{}).items() if k in {'prompt_tokens','completion_tokens','total_tokens'} and type(v) is int}
    else:raise ValueError('Unsupported provider')
    return validate(raw),usage


def validate(raw):
    value=json.loads(raw)
    if not isinstance(value,dict) or set(value)!={'tool','arguments'} or value['tool']!='multiply':
        raise ValueError('Tool not allowed')
    args=value['arguments']
    if not isinstance(args,dict) or set(args)!={'a','b'} or any(type(v) is not int or not -1000<=v<=1000 for v in args.values()):
        raise ValueError('Invalid tool arguments')
    return value


async def call_tool(decision):
    from mcp.client import Client
    from mcp.client.streamable_http import streamable_http_client
    import httpx2
    validate(json.dumps(decision))
    url=endpoint(os.environ['AGENT_MCP_URL'])
    headers={}
    if os.environ.get('AGENT_MCP_TOKEN'):headers['Authorization']='Bearer '+os.environ['AGENT_MCP_TOKEN']
    async with asyncio.timeout(8):
        async with httpx2.AsyncClient(headers=headers,trust_env=False,timeout=5) as http:
            async with Client(streamable_http_client(url,http_client=http),read_timeout_seconds=5) as client:
                available=await client.list_tools()
                if not any(t.name=='multiply' for t in available.tools):raise ValueError('Required MCP tool missing')
                # Session call does not enable the convenience client's input-required replay loop.
                result=await client.session.call_tool('multiply',decision['arguments'])
                if result.is_error:raise ValueError('MCP tool failed')
                content=result.structured_content
                if content is None:
                    content=json.loads(next(c.text for c in result.content if c.type=='text'))
                if not isinstance(content,dict) or set(content)!={'result'} or type(content['result']) is not int:
                    raise ValueError('Invalid tool result')
                if content['result']!=decision['arguments']['a']*decision['arguments']['b']:
                    raise ValueError('Incorrect tool result')
                return content


def export(trace_id,stages,status,usage):
    if not os.environ.get('AGENT_LANGFUSE_URL'):return 'disabled'
    parent=trace_id[:16];spans=[]
    def span(name,kind,start,end,span_id,parent_id=None,error=False):
        attrs={'langfuse.observation.type':kind,'langfuse.trace.name':'connected-agent.request',
               'langfuse.observation.metadata.app_id':'connected-agent',
               'langfuse.observation.metadata.version':os.environ.get('APP_VERSION','unknown')}
        item={'traceId':trace_id,'spanId':span_id,'name':name,'kind':1,
              'startTimeUnixNano':str(start),'endTimeUnixNano':str(end),
              'attributes':[{'key':k,'value':{'stringValue':v}} for k,v in attrs.items()],
              'status':{'code':2 if error else 1}}
        if parent_id:item['parentSpanId']=parent_id
        return item
    import secrets
    spans.append(span('connected-agent.request','agent',stages[0]['start_ns'],time.time_ns(),parent,error=status!='SUCCEEDED'))
    for stage in stages:
        item=span(stage['stage'],'generation' if stage['stage']=='model' else 'tool',stage['start_ns'],stage['end_ns'],secrets.token_hex(8),parent,stage['status']!='SUCCEEDED')
        item['attributes'].append({'key':'langfuse.observation.metadata.duration_ms','value':{'intValue':stage['duration_ms']}})
        if stage['stage']=='model':
            item['attributes'].append({'key':'langfuse.observation.model.name','value':{'stringValue':os.environ.get('AGENT_MODEL','unknown')}})
            mapped={k:usage[key] for k,key in [('input','prompt_tokens'),('output','completion_tokens'),('total','total_tokens')] if key in usage}
            if mapped:item['attributes'].append({'key':'langfuse.observation.usage_details','value':{'stringValue':json.dumps(mapped)}})
        spans.append(item)
    payload={'resourceSpans':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':'connected-agent'}}]},'scopeSpans':[{'scope':{'name':'connected-agent'},'spans':spans}]}]}
    try:
        with httpx.Client(timeout=2,trust_env=False,follow_redirects=False) as client:
            response=client.post(endpoint(os.environ['AGENT_LANGFUSE_URL'])+'/api/public/otel/v1/traces',
                auth=(os.environ['AGENT_LANGFUSE_PUBLIC'],os.environ['AGENT_LANGFUSE_SECRET']),
                headers={'x-langfuse-ingestion-version':'4'},json=payload)
            response.raise_for_status()
            if response.json().get('partialSuccess',{}).get('rejectedSpans'):raise ValueError('Partial export')
        return 'exported'
    except Exception:return 'failed'


def run(message,trace_id):
    if not isinstance(message,str) or not 1<=len(message.strip())<=1000:raise ValueError('Invalid message')
    stages=[];out={'model':os.environ.get('AGENT_MODEL'),'trace_id':trace_id,'provider':os.environ.get('AGENT_PROVIDER'),'status':'FAILED'}
    def step(name,operation):
        start=time.time_ns();stage={'stage':name,'start_ns':start,'status':'FAILED'}
        try:
            result=operation();stage['status']='SUCCEEDED';return result
        except Exception:
            stage['error']='MODEL_FAILED' if name=='model' else 'MCP_FAILED'
            raise
        finally:
            stage['end_ns']=time.time_ns();stage['duration_ms']=(stage['end_ns']-start)//1000000;stages.append(stage)
    try:
        decision,usage=step('model',lambda:plan(message))
        result=step('mcp.multiply',lambda:asyncio.run(call_tool(decision)))
        out.update(status='SUCCEEDED',answer=str(result['result']),usage=usage,tool='multiply')
    except Exception:
        out['error']=stages[-1]['error']
    out['telemetry']=export(trace_id,stages,out['status'],out.get('usage',{}))
    out['stages']=[{k:v for k,v in stage.items() if k not in {'start_ns','end_ns'}} for stage in stages]
    # No input, output, credentials, exception bodies or remote URL in durable logs.
    print(json.dumps({k:v for k,v in out.items() if k!='answer'}),flush=True)
    return out
