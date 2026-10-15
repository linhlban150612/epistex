import json
import os
import pathlib
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Independent protocol backend: reported effort is derived from its state, not the request.
BACKEND = r'''
import json, os, sys
effort = 'low'
model = 'claude-opus-5.5'
cwd = None
pending_prompt = None
servers = None
agent = sys.argv[sys.argv.index('--agent') + 1]
unsafe_during_confirmation = False
policy = {'mcpServers': [], 'trusted': []}
def emit(m):
    print(json.dumps({'jsonrpc':'2.0', **m}), flush=True)
for line in sys.stdin:
    m=json.loads(line); method=m.get('method'); p=m.get('params',{}); ident=m.get('id')
    if method == 'initialize':
        emit({'id':ident,'result':{'protocolVersion':1,'agentCapabilities':{'loadSession':True},'_meta':{'future':'keep'}}})
    elif method in ('session/new','session/load'):
        cwd=p['cwd']; servers=p.get('mcpServers'); mode='kiro_default' if os.getenv('UNSAFE_MODE') else agent
        result={'modes':{'currentModeId':mode,'availableModes':[{'id':mode,'name':mode}]},
                'models':{'currentModelId':model,'availableModels':[{'modelId':model,'name':model},{'modelId':'claude-sonnet-5.5','name':'Sonnet'}]},
                '_meta':{'future':'retain'}}
        if method=='session/new': result['sessionId']='seat'
        if method=='session/load' and os.getenv('BAD_LOAD_MODEL'): result['models']['currentModelId']='bogus'
        emit({'id':ident,'result':result})
        unsafe_during_confirmation = method=='session/load' and bool(os.getenv('LOAD_UNSAFE_AT_CONFIRM'))
        emit({'method':'_kiro.dev/commands/available','params':{'sessionId':'seat','commands':[{'name':'/effort'}],
              'tools':['read','shell'] + (['subagent'] if os.getenv('UNSAFE_TOOLS') else []) +
              [t for t in os.getenv('EXTRA_TOOLS','').split(',') if t],'_meta':{'new':'retain'}}})
    elif method=='session/set_model':
        if not os.getenv('IGNORE_MODEL'):model=p['modelId']
        effort='high'
        emit({'id':ident,'result':{}})
    elif method=='_kiro.dev/commands/execute':
        command=p['command']
        if command.get('command')=='effort':
            if os.getenv('REJECT_EFFORT'):
                emit({'id':ident,'error':{'code':-32001,'message':'backend rejected','data':{'why':'quota'}}});continue
            if not os.getenv('IGNORE_EFFORT'):effort=command['args']['level']
        elif command.get('command') in ('mcp','tools') and command.get('args'):
            policy['mcpServers']=['injected'] if command['command']=='mcp' else policy['mcpServers']
            policy['trusted']=['*'] if command['command']=='tools' else policy['trusted']
        emit({'id':ident,'result':{'success':True,'policy':policy}})
        emit({'method':'_kiro.dev/metadata','params':{'sessionId':'seat','reasoning':{'effort':effort},'_meta':{'opaque':True}}})
    elif method=='_kiro.dev/commands/options':
        if unsafe_during_confirmation:
            emit({'method':'_kiro.dev/commands/available','params':{'sessionId':'seat','commands':[{'name':'/effort'}],
                  'tools':['read','shell','subagent']}})
            unsafe_during_confirmation=False
        value=effort if p['command']=='effort' else model
        values=['low','medium','high'] if p['command']=='effort' else ['claude-opus-5.5','claude-sonnet-5.5']
        emit({'id':ident,'result':{'options':[{'value':v,'label':v+('  [active]' if v==value else ''),
              'description':'model'+(' [active]' if v==value else '')} for v in values]}})
    elif method=='session/prompt':
        if p['prompt'][-1].get('text')=='wait':
            if os.getenv('MIDPROMPT_UNSAFE'):
                emit({'method':'_kiro.dev/commands/available','params':{'sessionId':'seat','commands':[{'name':'/effort'}],
                      'tools':['read','shell','kill_agent']}})
            pending_prompt=ident;continue
        emit({'id':ident,'result':{'stopReason':'end_turn','observed':{'effort':effort,'model':model,'cwd':cwd,'prompt':p['prompt'],'pid':os.getpid(),'servers':servers}}})
    elif method=='session/cancel':
        emit({'method':'session/update','params':{'sessionId':'seat','update':{'sessionUpdate':'future_update','_meta':{'opaque':5}}}})
        if pending_prompt is not None:emit({'id':pending_prompt,'result':{'stopReason':'cancelled'}});pending_prompt=None
    elif method=='authenticate':
        if p.get('exit'):sys.exit(7)
        emit({'id':'backend-ask','method':p['method'],'params':{'sessionId':'seat','options':[]}})
        request_id=ident
    elif not method and ident=='backend-ask':
        emit({'id':request_id,'result':{'reply':m}})
    elif method:
        emit({'id':ident,'error':{'code':-32601,'message':'unknown','data':{'method':method}}})
'''


PASEO = {'type': 'http', 'name': 'paseo', 'url': 'http://127.0.0.1:6767/mcp/agents?callerAgentId=lead-1', 'headers': []}
LEAD_POLICY = ['list_agents', 'list_workspaces', 'list_providers', 'list_models', 'list_profiles', 'create_agent',
               'send_agent_prompt', 'get_agent_activity', 'get_agent_status', 'cancel_agent', 'archive_agent',
               'list_pending_permissions', 'respond_to_permission', 'set_agent_mode']


class Client:
    def __init__(self, env, cwd, trace=False, role='peer'):
        self.trace = trace
        self.process = subprocess.Popen([sys.executable, str(ROOT / 'setup/role-agent'), role, 'kiro'],
                                        cwd=cwd, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.messages = queue.Queue()
        self.notifications = []
        self.serial = 0
        def read():
            for line in self.process.stdout:
                if trace: print('ACP ' + line.rstrip(), flush=True)
                self.messages.put(json.loads(line))
            self.messages.put(None)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, method, params, ident=None):
        message = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if ident is not None: message['id'] = ident
        self.write(message)

    def write(self, message):
        self.process.stdin.write(json.dumps(message) + '\n')
        self.process.stdin.flush()

    def response(self, ident):
        while True:
            m = self.messages.get(timeout=40)
            if m is None:
                raise AssertionError('ACP exited: ' + self.process.stderr.read())
            if m.get('id') == ident: return m
            self.notifications.append(m)

    def call(self, rpc_method, **params):
        self.serial += 1
        self.send(rpc_method, params, self.serial)
        return self.response(self.serial)

    def close(self):
        if not self.process.stdin.closed:
            self.process.stdin.close()
        if self.process.poll() is None:
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate(); self.process.wait(timeout=5)
        self.reader.join(timeout=5)
        stderr = self.process.stderr.read()
        if self.trace and stderr: print('STDERR ' + stderr)
        self.process.stdout.close(); self.process.stderr.close()


class KiroACPTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
        self.cwd = self.home / 'project'
        self.cwd.mkdir()
        runtime = self.home / '.kiro/agents'
        runtime.mkdir(parents=True)
        for role in ('peer', 'lead'):
            shutil.copyfile(ROOT / f'setup/kiro-{role}.json', runtime / f'epistex_{role}.json')
        binary = self.home / 'kiro-cli'
        binary.write_text('#!' + sys.executable + '\n' + BACKEND)
        binary.chmod(0o755)
        self.env = {**os.environ, 'HOME': str(self.home), 'PATH': str(self.home)}
        self.clients = []

    def tearDown(self):
        for client in self.clients: client.close()
        self.temp.cleanup()

    def client(self, role='peer', **flags):
        c = Client({**self.env, **flags}, self.cwd, role=role)
        self.clients.append(c)
        result = c.call('initialize', protocolVersion=1, clientCapabilities={})
        self.assertEqual(result['result']['_meta'], {'future': 'keep'})
        return c

    def new(self, client, servers=()):
        return client.call('session/new', cwd=str(self.cwd), mcpServers=list(servers))

    def effort(self, client, value):
        return client.call('session/set_config_option', sessionId='seat', configId='epistex_effort', value=value)

    def test_model_effort_role_cwd_cancel_resume_and_unknown_metadata(self):
        c = self.client()
        self.assertEqual(self.new(c)['result']['configOptions'][0]['currentValue'], 'low')
        for model in ('claude-sonnet-5.5', 'claude-opus-5.5'):
            self.assertIn('result', c.call('session/set_model', sessionId='seat', modelId=model))
            for effort in ('medium', 'low'):
                self.assertEqual(self.effort(c, effort)['result']['configOptions'][0]['currentValue'], effort)
                observed = c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}])['result']['observed']
                self.assertEqual((observed['model'], observed['effort'], observed['cwd']), (model, effort, str(self.cwd)))
                if model == 'claude-sonnet-5.5' and effort == 'medium':
                    self.assertEqual(observed['prompt'][0]['text'], 'Role instructions for this session:\n' + (ROOT / 'agents/PEER.md').read_text())
                else: self.assertEqual(observed['prompt'], [{'type':'text','text':'inspect'}])
        c.send('session/prompt', {'sessionId':'seat','prompt':[{'type':'text','text':'wait'}]}, 'waiting')
        c.send('session/cancel', {'sessionId':'seat'})
        self.assertEqual(c.response('waiting')['result']['stopReason'], 'cancelled')
        self.assertTrue(any(m.get('method') == 'session/update' and m['params']['update']['_meta']=={'opaque':5} for m in c.notifications))
        resumed = c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=[])
        self.assertEqual(resumed['result']['_meta'], {'future':'retain'})
        observed = c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'after resume'}])['result']['observed']
        self.assertIn('# Peer', observed['prompt'][0]['text'])

    def test_unconfirmed_effort_and_backend_errors_never_succeed(self):
        for flags in ({'IGNORE_EFFORT':'1'}, {'REJECT_EFFORT':'1'}):
            with self.subTest(flags=flags):
                c = self.client(**flags)
                self.new(c)
                response = self.effort(c, 'medium')
                self.assertIn('error', response)
                if 'REJECT_EFFORT' in flags:
                    self.assertEqual(response['error'], {'code':-32001,'message':'backend rejected','data':{'why':'quota'}})
                self.assertIn('error', c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}]))

    def test_model_switch_retains_medium_when_client_does_not_repeat_selection(self):
        c = self.client()
        self.new(c)
        self.effort(c, 'medium')
        self.assertIn('result', c.call('session/set_model', sessionId='seat', modelId='claude-sonnet-5.5'))
        observed = c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}])['result']['observed']
        self.assertEqual((observed['model'], observed['effort']), ('claude-sonnet-5.5', 'medium'))

    def test_model_success_without_backend_switch_is_rejected(self):
        c = self.client(IGNORE_MODEL='1')
        self.new(c)
        self.assertIn('error', c.call('session/set_model', sessionId='seat', modelId='claude-sonnet-5.5'))
        self.assertIn('error', c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}]))

    def test_same_process_load_rejects_inventory_changed_during_confirmation(self):
        c = self.client(LOAD_UNSAFE_AT_CONFIRM='1')
        self.assertIn('result', self.new(c))
        self.assertIn('error', c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=[]))
        self.assertIn('error', c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}]))

    def test_native_mcp_and_trust_mutations_are_rejected_without_policy_changes(self):
        c = self.client()
        self.new(c)
        for family, operations in (('mcp', ('add','remove')), ('tools', ('trust-all','trust','untrust','reset'))):
            for operation in operations:
                with self.subTest(family=family, operation=operation):
                    self.assertIn('error', c.call('_kiro.dev/commands/execute', sessionId='seat',
                        command={'command':family,'args':{'command':operation,'name':'example'}}))
            with self.subTest(family=family, operation='inspection'):
                response = c.call('_kiro.dev/commands/execute', sessionId='seat', command={'command':family,'args':{}})
                self.assertEqual(response['result']['policy'], {'mcpServers':[], 'trusted':[]})

    def test_native_tools_modes_overrides_and_invalid_selection_fail_closed(self):
        for flags in ({'UNSAFE_TOOLS':'1'}, {'UNSAFE_MODE':'1'}):
            c = self.client(**flags)
            self.assertIn('error', self.new(c))
        c = self.client()
        self.new(c)
        for method, params in (
            ('session/set_mode', {'modeId':'kiro_default'}),
            ('session/set_model', {'modelId':'auto'}),
            ('session/set_config_option', {'configId':'epistex_effort','value':'high'}),
            ('_kiro.dev/commands/execute', {'command':{'command':'agent','args':{'name':'kiro_default'}}}),
            ('_session/spawn', {}),
        ):
            self.assertIn('error', c.call(method, sessionId='seat', **params))
        override = self.cwd / '.kiro/agents'
        override.mkdir(parents=True)
        (override / 'epistex_peer.json').write_text('{"tools":["*"]}')
        self.assertIn('error', self.new(c))

    def test_permissions_unsupported_callbacks_and_early_exit(self):
        c = self.client()
        self.new(c)
        c.send('authenticate', {'method':'session/request_permission'}, 'permission')
        ask = c.messages.get(timeout=5)
        while ask.get('id') != 'backend-ask': ask = c.messages.get(timeout=5)
        self.assertEqual(ask['method'], 'session/request_permission')
        reply = {'jsonrpc':'2.0','id':'backend-ask','result':{'outcome':{'outcome':'cancelled'}}}
        c.write(reply)
        self.assertEqual(c.response('permission')['result']['reply'], reply)
        response = c.call('authenticate', method='unsupported/request')
        self.assertEqual(response['result']['reply']['error']['code'], -32601)
        self.assertIn('error', c.call('authenticate', exit=1))
        self.assertEqual(c.process.wait(timeout=5), 7)
        c = self.client()
        self.new(c)
        observed = c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}])['result']['observed']
        c.process.terminate()
        self.assertNotEqual(c.process.wait(timeout=5), 0)
        with self.assertRaises(ProcessLookupError):
            os.kill(observed['pid'], 0)


    def test_peer_rejects_paseo_server_and_keeps_its_allowlist(self):
        peer = json.loads((ROOT / 'setup/kiro-peer.json').read_text())
        self.assertFalse([t for t in peer['tools'] if t.startswith('@')])
        self.assertEqual((peer['name'], peer['mcpServers'], peer['includeMcpJson']), ('epistex_peer', {}, False))
        c = self.client()
        for method in ('session/new', 'session/load'):
            with self.subTest(method=method):
                response = c.call(method, sessionId='seat', cwd=str(self.cwd), mcpServers=[PASEO])
                self.assertEqual(response['error']['message'], 'Kiro Peer does not accept injected MCP servers')
        for tool in ('list_agents', '@paseo/list_agents'):
            with self.subTest(tool=tool):
                c = self.client(EXTRA_TOOLS=tool)
                self.assertEqual(self.new(c)['error']['message'], 'Kiro exposed tools outside the Peer allowlist')

    def test_lead_tools_match_repo_lead_policy(self):
        lead = json.loads((ROOT / 'setup/kiro-lead.json').read_text())
        peer = json.loads((ROOT / 'setup/kiro-peer.json').read_text())
        paseo = [t[len('@paseo/'):] for t in lead['tools'] if t.startswith('@')]
        self.assertEqual(paseo, LEAD_POLICY)
        self.assertEqual([t for t in lead['tools'] if not t.startswith('@')], peer['tools'])
        script = (ROOT / 'setup/setup-seats.sh').read_text()
        deny = json.loads(script.split("expected_deny_lead='", 1)[1].split("'", 1)[0])
        self.assertEqual((len(deny), set(deny) & set(paseo)), (47, set()))
        self.assertEqual((lead['name'], lead['allowedTools'], lead['mcpServers'], lead['includeMcpJson']),
                         ('epistex_lead', [], {}, False))

    def test_lead_accepts_only_exact_paseo_server_and_primes_lead_role(self):
        for server in (PASEO, {**PASEO, 'url': 'http://[::1]:6767/mcp/agents?callerAgentId=x'},
                       {**PASEO, 'url': 'http://localhost:1/mcp/agents?callerAgentId=x'},
                       {**PASEO, 'headers': [{'name': 'Authorization', 'value': 'Bearer 0f1e'}]}):
            with self.subTest(server=server):
                c = self.client('lead', EXTRA_TOOLS=','.join(LEAD_POLICY))
                self.assertIn('result', self.new(c, [server]))
                observed = c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}])['result']['observed']
                self.assertEqual(observed['servers'], [server])
                self.assertEqual(observed['prompt'][0]['text'],
                                 'Role instructions for this session:\n' + (ROOT / 'agents/LEAD.md').read_text())
                self.assertIn('result', c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=[server]))

    def test_lead_rejects_every_other_mcp_server_shape(self):
        url = lambda u: {**PASEO, 'url': u}
        header = lambda h: {**PASEO, 'headers': h}
        cases = {
            'Kiro Lead requires an injected Paseo MCP server list': [None, 'paseo', [PASEO, PASEO], ['paseo']],
            'Kiro Lead accepts only the Paseo HTTP MCP server': [
                {'type':'stdio','name':'paseo','command':'paseo','args':[],'env':[]}, {**PASEO, 'type':'sse'},
                {**PASEO, 'name':'other'}, {**PASEO, 'extra':1}, {k: v for k, v in PASEO.items() if k != 'headers'},
                url(None)],
            'Kiro Lead rejected a malformed Paseo MCP URL': [
                url('http://127.0.0.1:99999/mcp/agents?callerAgentId=x'),
                url('http://127.0.0.1:6767/mcp/agents?callerAgentId')],
            'Kiro Lead accepts only the loopback Paseo /mcp/agents endpoint': [
                url('https://127.0.0.1:6767/mcp/agents?callerAgentId=x'), url('http://10.0.0.2:6767/mcp/agents?callerAgentId=x'),
                url('http://paseo.example:6767/mcp/agents?callerAgentId=x'), url('http://127.0.0.1/mcp/agents?callerAgentId=x'),
                url('http://u:p@127.0.0.1:6767/mcp/agents?callerAgentId=x'), url('http://127.0.0.1:6767/mcp?callerAgentId=x'),
                url('http://127.0.0.1:6767/mcp/agents/?callerAgentId=x'), url('http://127.0.0.1:6767/mcp/agents?callerAgentId=x#f'),
                url('http://127.0.0.1:6767/mcp/agents?callerAgentId=x&a=b'), url('http://127.0.0.1:6767/mcp/agents?callerAgentId=x&callerAgentId=y'),
                url('http://127.0.0.1:6767/mcp/agents?callerAgentId='), url('http://127.0.0.1:6767/mcp/agents')],
            "Kiro Lead accepts only Paseo's bearer Authorization header": [
                header(None), header({}), header([{'name':'Authorization','value':'Basic eA=='}]),
                header([{'name':'Authorization','value':'Bearer '}]), header([{'name':'X-Api-Key','value':'Bearer x'}]),
                header([{'name':'Authorization','value':'Bearer x'}, {'name':'Cookie','value':'a'}]),
                header([{'name':'Authorization','value':'Bearer x','extra':1}])],
        }
        c = self.client('lead')
        for message, variants in cases.items():
            for servers in variants:
                servers = servers if not isinstance(servers, dict) else [servers]
                for method in ('session/new', 'session/load', 'session/resume'):
                    with self.subTest(method=method, servers=servers):
                        params = {'sessionId':'seat','cwd':str(self.cwd)}
                        if servers is not None: params['mcpServers'] = servers
                        self.assertEqual(c.call(method, **params)['error']['message'], message)
        self.assertIn('error', c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}]))

    def test_lead_probe_sessions_accept_empty_servers_but_refuse_prompts(self):
        refusal = 'Kiro Lead session has no injected Paseo MCP server; prompts are refused'
        for method in ('session/new', 'session/load'):
            with self.subTest(method=method):
                c = self.client('lead')
                params = {'cwd': str(self.cwd), 'mcpServers': []}
                if method == 'session/load': params['sessionId'] = 'seat'
                self.assertIn('result', c.call(method, **params))
                self.assertEqual(self.effort(c, 'medium')['result']['configOptions'][0]['currentValue'], 'medium')
                self.assertIn('result', c.call('session/set_model', sessionId='seat', modelId='claude-sonnet-5.5'))
                self.assertEqual(c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}])
                                 ['error']['message'], refusal)

    def test_lead_probe_load_over_injected_session_refuses_prompt(self):
        c = self.client('lead', EXTRA_TOOLS=','.join(LEAD_POLICY))
        self.assertIn('result', self.new(c, [PASEO]))
        self.assertIn('result', c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=[]))
        self.assertEqual(c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}])
                         ['error']['message'],
                         'Kiro Lead session has no injected Paseo MCP server; prompts are refused')

    def test_lead_inventory_outside_policy_fails_closed(self):
        for tool in ('kill_agent', 'speak', 'create_schedule', '@paseo/list_agents', '@other/list_agents', 'subagent',
                     ','.join(LEAD_POLICY[:-1])):  # last case: missing one policy tool
            with self.subTest(tool=tool):
                c = self.client('lead', EXTRA_TOOLS=tool)
                self.assertEqual(self.new(c, [PASEO])['error']['message'], 'Kiro exposed tools outside the Lead allowlist')
                self.assertIn('error', c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}]))
        c = self.client('lead')
        self.assertIn('error', c.call('session/set_mode', sessionId='seat', modeId='kiro_default'))
        (self.cwd / '.kiro/agents').mkdir(parents=True)
        (self.cwd / '.kiro/agents/epistex_lead.json').write_text('{"tools":["*"]}')
        self.assertEqual(self.new(c, [PASEO])['error']['message'],
                         'Workspace agent overrides the seat-owned Kiro Lead configuration')

    def test_resume_validates_for_both_roles(self):
        for role in ('peer', 'lead'):
            with self.subTest(role=role):
                bad = [{'command': 'x'},
                       {'type': 'http', 'name': 'x', 'url': 'http://x/mcp/agents?callerAgentId=x', 'headers': []},
                       PASEO]
                for servers in bad:
                    with self.subTest(servers=servers):
                        c = self.client(role)
                        r = c.call('session/resume', sessionId='seat', cwd=str(self.cwd), mcpServers=servers)
                        self.assertIn('error', r)
                        self.assertNotEqual(r['error']['message'], 'unknown')
                c = self.client(role)
                r = c.call('session/resume', sessionId='seat', cwd=str(self.cwd), mcpServers=[])
                self.assertEqual(r['error']['message'], 'unknown')  # forwarded to backend

    def test_lead_resume_clears_session_and_bad_cwd_fails(self):
        c = self.client('lead', EXTRA_TOOLS=','.join(LEAD_POLICY))
        self.assertIn('result', self.new(c, [PASEO]))
        self.effort(c, 'medium')
        self.assertEqual(c.call('session/resume', sessionId='seat', cwd='/nope', mcpServers=[])
                         ['error']['message'], 'Kiro Lead requires an existing absolute CWD')
        self.assertEqual(c.call('session/resume', sessionId='seat', cwd=str(self.cwd), mcpServers=[])
                         ['error']['message'], 'unknown')
        self.assertIn('error', c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'x'}]))

    def test_unknown_methods_get_method_not_found(self):
        for role in ('peer', 'lead'):
            c = self.client(role)
            self.assertEqual(c.call('session/fork', sessionId='seat', cwd=str(self.cwd), mcpServers=[])
                             ['error']['code'], -32601)

    def test_compact_follows_the_prompt_gate(self):
        c = self.client()
        self.assertEqual(c.call('_kiro.dev/commands/execute', sessionId='seat',
                                command={'command': 'compact', 'args': {}})
                         ['error']['message'], 'Kiro Peer session/effort/tool policy is not confirmed')
        self.assertIn('result', self.new(c))
        self.assertIn('result', c.call('_kiro.dev/commands/execute', sessionId='seat',
                                     command={'command': 'compact', 'args': {}}))

    def test_unsafe_inventory_mid_prompt_revokes_session(self):
        c = self.client(MIDPROMPT_UNSAFE='1')
        self.assertIn('result', self.new(c))
        self.effort(c, 'medium')
        c.send('session/prompt', {'sessionId': 'seat', 'prompt': [{'type': 'text', 'text': 'wait'}]}, 'w')
        self.assertEqual(c.response('w')['result']['stopReason'], 'cancelled')
        self.assertIn('error', c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'x'}]))

    def test_failed_load_does_not_disturb_pending_or_confirmed_state(self):
        c = self.client()
        self.assertIn('result', self.new(c))
        c.send('session/set_config_option',
               {'sessionId': 'seat', 'configId': 'epistex_effort', 'value': 'medium'}, 'e')
        self.assertEqual(c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=['paseo'])
                         ['error']['message'], 'Kiro Peer does not accept injected MCP servers')
        self.assertIn('result', c.response('e'))

    def test_failed_load_on_reused_sid_clears_authorization(self):
        c = self.client(BAD_LOAD_MODEL='1')
        self.assertIn('result', self.new(c))
        self.effort(c, 'medium')
        self.assertEqual(c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=[])
                         ['error']['message'], 'Kiro restored an unsupported mode/model')
        self.assertIn('error', c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'x'}]))

    def test_pipelined_new_and_load_do_not_crash(self):
        c = self.client()
        c.send('session/new', {'cwd': str(self.cwd), 'mcpServers': []}, 'n')
        c.send('session/load', {'sessionId': 'seat', 'cwd': str(self.cwd), 'mcpServers': []}, 'l')
        self.assertIn('result', c.response('n'))
        self.assertIn('result', c.response('l'))


@unittest.skipUnless(os.getenv('EPISTEX_REAL_KIRO_PROBE') == '1', 'real metadata probe is opt-in; no model prompts')
class RealKiroMetadataTest(unittest.TestCase):
    def test_four_selections_and_resume_without_model_prompts(self):
        c = Client(os.environ.copy(), ROOT, trace=True)
        try:
            c.call('initialize', protocolVersion=1, clientCapabilities={})
            result = c.call('session/new', cwd=str(ROOT), mcpServers=[])
            self.assertIn('result', result)
            sid = result['result']['sessionId']
            for model in ('claude-opus-5.5','claude-sonnet-5.5'):
                self.assertIn('result', c.call('session/set_model', sessionId=sid, modelId=model))
                actual = c.call('_kiro.dev/commands/options', sessionId=sid, command='model')
                self.assertTrue(any(o['value']==model and '[active]' in o.get('description', '') for o in actual['result']['options']))
                for effort in ('low','medium'):
                    response = c.call('session/set_config_option', sessionId=sid, configId='epistex_effort', value=effort)
                    self.assertEqual(response['result']['configOptions'][0]['currentValue'], effort)
                    actual = c.call('_kiro.dev/commands/options', sessionId=sid, command='effort')
                    self.assertTrue(any(o['value']==effort and '[active]' in o['label'] for o in actual['result']['options']))
            self.assertIn('error', c.call('session/set_mode', sessionId=sid, modeId='kiro_default'))
            self.assertIn('error', c.call('session/set_config_option', sessionId=sid, configId='epistex_effort', value='high'))
            loaded = c.call('session/load', sessionId=sid, cwd=str(ROOT), mcpServers=[])
            self.assertEqual(loaded['result']['models']['currentModelId'], 'claude-sonnet-5.5')
            self.assertEqual(loaded['result']['configOptions'][0]['currentValue'], 'medium')
            inventory = c.call('_kiro.dev/commands/execute', sessionId=sid, command={'command':'mcp','args':{}})
            self.assertEqual(inventory['result']['data']['servers'], [])
            inventory = c.call('_kiro.dev/commands/execute', sessionId=sid, command={'command':'tools','args':{}})
            self.assertNotIn('subagent', [t['name'] for t in inventory['result']['data']['tools']])
            self.assertTrue(all(t['status']=='requires-approval' for t in inventory['result']['data']['tools']))
        finally: c.close()
        resumed = Client(os.environ.copy(), ROOT, trace=True)
        try:
            resumed.call('initialize', protocolVersion=1, clientCapabilities={})
            response = resumed.call('session/load', sessionId=sid, cwd=str(ROOT), mcpServers=[])
            self.assertIn('result', response)
            self.assertEqual(response['result']['modes']['currentModeId'], 'epistex_peer')
            self.assertEqual(response['result']['models']['currentModelId'], 'claude-sonnet-5.5')
            self.assertEqual(response['result']['configOptions'][0]['currentValue'], 'medium')
        finally: resumed.close()


if __name__ == '__main__':
    unittest.main()
