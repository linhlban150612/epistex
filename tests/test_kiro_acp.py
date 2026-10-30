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

# Independent V3 protocol backend modeled on live Kiro CLI 2.33.1 (--agent-engine=v3):
# config options report backend state, unknown values are ignored with success, tools arrive as tags.
BACKEND = r'''
import json, os, sys
assert sys.argv[1:] == ['acp', '--agent-engine=v3', '--auth-method=cli'], sys.argv
effort = 'high'
model = 'claude-opus-5.5'
mode = None
cwd = None
pending_prompt = None
servers = None
unsafe_on_set = False
late = False
def emit(m):
    print(json.dumps({'jsonrpc':'2.0', **m}), flush=True)
def options():
    return [{'type':'select','id':'mode','category':'mode','currentValue':mode,'options':[{'value':v} for v in ('vibe',mode)]},
            {'type':'select','id':'model','category':'model','currentValue':model,
             'options':[{'value':v} for v in ('auto','claude-opus-5.5','claude-sonnet-5.5')]},
            {'type':'select','id':'effortLevel','category':'thought_level','currentValue':effort,
             'options':[{'value':v} for v in ('low','medium','high','max')]},
            {'type':'select','id':'autopilot','currentValue':'on','options':[{'value':'on'},{'value':'off'}]}]
def inventory(extra=()):
    tags = ['read','write','shell','web'] + (['subagent'] if os.getenv('UNSAFE_TOOLS') else []) + list(extra)
    emit({'method':'_kiro/tools/didChange','params':{'sessionId':'seat','tags':[{'source':'x','tag':t} for t in tags]}})
extra = [t for t in os.getenv('EXTRA_TOOLS','').split(',') if t]
for line in sys.stdin:
    m=json.loads(line); method=m.get('method'); p=m.get('params',{}); ident=m.get('id')
    if method == 'initialize':
        emit({'id':ident,'result':{'protocolVersion':1,'agentCapabilities':{'loadSession':True,'_meta':{'kiro':{
              'extensionMethods':['_kiro/session/context','_kiro/session/compact','_kiro/workflow/new']}}},'_meta':{'future':'keep'}}})
    elif method in ('session/new','session/load'):
        cwd=p['cwd']; servers=p.get('mcpServers')
        if method=='session/new': mode=p.get('_meta',{}).get('kiro',{}).get('modeId','vibe'); effort='high'
        if method=='session/load' and mode is None: mode=os.environ['STORED_MODE']  # session saved by an earlier process
        if os.getenv('UNSAFE_MODE'): mode='vibe'
        if method=='session/load' and os.getenv('BAD_LOAD_MODEL'): model='auto'
        if method=='session/load' and os.getenv('LOAD_UNSAFE_AT_CONFIRM'): effort='high'; unsafe_on_set=True
        late = bool(servers) and os.getenv('MCP_LATE')
        if servers: emit({'method':'_kiro/mcp/status','params':{'sessionId':'seat','servers':[{'name':'paseo','status':'connecting' if late else 'connected'}]}})
        inventory([] if late else extra)
        catalog_late = method=='session/new' and os.getenv('CATALOG_LATE')  # model list not loaded yet
        shown = [o for o in options() if not catalog_late or o['id'] not in ('model','effortLevel')]
        result={'modes':{'currentModeId':mode,'availableModes':[{'id':'vibe'},{'id':mode}]},'configOptions':shown,'_meta':{'future':'retain'}}
        if method=='session/new': result['sessionId']='seat'
        emit({'id':ident,'result':result})
        if catalog_late:
            emit({'method':'session/update','params':{'sessionId':'seat','update':{'sessionUpdate':'config_option_update','configOptions':options()}}})
    elif method=='session/set_config_option':
        value=p['value']
        if p['configId']=='effortLevel':
            if os.getenv('REJECT_EFFORT'):
                emit({'id':ident,'error':{'code':-32001,'message':'backend rejected','data':{'why':'quota'}}});continue
            if not os.getenv('IGNORE_EFFORT') and value != os.getenv('IGNORE_VALUE') and value in ('low','medium','high','max'): effort=value
        elif p['configId']=='model':
            if not os.getenv('IGNORE_MODEL'): model=value
            if os.getenv('MODEL_RESETS_EFFORT'): effort='high'
        if unsafe_on_set: inventory(['subagent']); unsafe_on_set=False
        emit({'method':'session/update','params':{'sessionId':'seat','update':{'sessionUpdate':'config_option_update','configOptions':options()}}})
        emit({'id':ident,'result':{'configOptions':options()}})
        if late:  # Paseo's MCP server connects only after the seat's first confirmation round.
            late = False
            emit({'method':'_kiro/mcp/status','params':{'sessionId':'seat','servers':[{'name':'paseo','status':'connected'}]}})
            inventory(extra)
    elif method=='_kiro/session/compact':
        emit({'id':ident,'result':{}})
    elif method=='session/prompt':
        if p['prompt'][-1].get('text')=='wait':
            if os.getenv('MIDPROMPT_UNSAFE'): inventory(['@paseo/kill_agent'])
            if os.getenv('MIDPROMPT_MODE'):
                mode='vibe'
                emit({'method':'session/update','params':{'sessionId':'seat','update':{'sessionUpdate':'current_mode_update','currentModeId':'vibe'}}})
            pending_prompt=ident;continue
        emit({'id':ident,'result':{'stopReason':'end_turn','observed':{'effort':effort,'model':model,'mode':mode,'cwd':cwd,'prompt':p['prompt'],'pid':os.getpid(),'servers':servers}}})
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
LEAD_POLICY = ['list_workspaces', 'list_providers', 'list_models', 'list_profiles', 'create_agent',
               'send_agent_prompt', 'cancel_agent', 'archive_agent',
               'list_pending_permissions', 'respond_to_permission', 'set_agent_mode']
LEAD_TAGS = ','.join('@paseo/' + t for t in LEAD_POLICY)


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
        c = Client({**self.env, 'STORED_MODE': 'epistex_' + role, **flags}, self.cwd, role=role)
        self.clients.append(c)
        result = c.call('initialize', protocolVersion=1, clientCapabilities={})
        self.assertEqual(result['result']['_meta'], {'future': 'keep'})
        return c

    def new(self, client, servers=()):
        return client.call('session/new', cwd=str(self.cwd), mcpServers=list(servers))

    def effort(self, client, value):
        return client.call('session/set_config_option', sessionId='seat', configId='effortLevel', value=value)

    def model(self, client, value):
        return client.call('session/set_config_option', sessionId='seat', configId='model', value=value)

    def prompt(self, client, text='inspect'):
        return client.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':text}])

    @staticmethod
    def current(response, config_id):
        return next(o['currentValue'] for o in response['result']['configOptions'] if o['id'] == config_id)

    def test_model_effort_role_cwd_cancel_load_and_unknown_metadata(self):
        c = self.client()
        created = self.new(c)
        # V3 defaults to effort "high"; the seat pins "low" and exposes only its own choices.
        self.assertEqual(self.current(created, 'effortLevel'), 'low')
        self.assertEqual({o['id']: [v['value'] for v in o['options']] for o in created['result']['configOptions']},
                         {'mode': ['epistex_peer'], 'model': ['claude-opus-5.5', 'claude-sonnet-5.5'],
                          'effortLevel': ['low', 'medium']})
        self.assertEqual(created['result']['modes']['availableModes'], [{'id': 'epistex_peer'}])
        for model in ('claude-sonnet-5.5', 'claude-opus-5.5'):
            self.assertEqual(self.current(self.model(c, model), 'model'), model)
            for effort in ('medium', 'low'):
                self.assertEqual(self.current(self.effort(c, effort), 'effortLevel'), effort)
                observed = self.prompt(c)['result']['observed']
                self.assertEqual((observed['model'], observed['effort'], observed['mode'], observed['cwd']),
                                 (model, effort, 'epistex_peer', str(self.cwd)))
                if model == 'claude-sonnet-5.5' and effort == 'medium':
                    self.assertEqual(observed['prompt'][0]['text'], 'Role instructions for this session:\n'
                                     + (ROOT / 'agents/contract/COMMON.md').read_text().rstrip() + '\n\n'
                                     + (ROOT / 'agents/PEER.md').read_text())
                else: self.assertEqual(observed['prompt'], [{'type':'text','text':'inspect'}])
        updates = [m['params']['update'] for m in c.notifications if m.get('method') == 'session/update']
        self.assertTrue(updates and all({o['id'] for o in u['configOptions']} == {'mode', 'model', 'effortLevel'}
                                        for u in updates if u['sessionUpdate'] == 'config_option_update'))
        c.send('session/prompt', {'sessionId':'seat','prompt':[{'type':'text','text':'wait'}]}, 'waiting')
        c.send('session/cancel', {'sessionId':'seat'})
        self.assertEqual(c.response('waiting')['result']['stopReason'], 'cancelled')
        self.assertTrue(any(m.get('method') == 'session/update' and m['params']['update'].get('_meta')=={'opaque':5} for m in c.notifications))
        loaded = c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=[])
        self.assertEqual(loaded['result']['_meta'], {'future':'retain'})
        self.assertEqual((self.current(loaded, 'model'), self.current(loaded, 'effortLevel')), ('claude-opus-5.5', 'low'))
        # The loaded history already holds the role; Paseo idle release resumes sessions this way.
        observed = self.prompt(c, 'after load')['result']['observed']
        self.assertEqual(observed['prompt'], [{'type': 'text', 'text': 'after load'}])

    def test_selection_requires_backend_confirmation(self):
        with self.subTest('initial effort pin ignored by backend'):
            c = self.client(IGNORE_EFFORT='1')
            self.assertIn('error', self.new(c))
            self.assertIn('error', self.prompt(c))
        with self.subTest('backend error is forwarded'):
            c = self.client(REJECT_EFFORT='1')
            self.assertEqual(self.new(c)['error'], {'code':-32001,'message':'backend rejected','data':{'why':'quota'}})
            self.assertIn('error', self.prompt(c))
        with self.subTest('ignored effort on confirmed session refuses prompts'):
            c = self.client(IGNORE_VALUE='medium')  # V3 answers success but keeps the old value.
            self.assertIn('result', self.new(c))
            self.assertIn('result', self.prompt(c))
            self.assertEqual(self.effort(c, 'medium')['error']['message'], 'Kiro did not confirm selected effortLevel')
            self.assertIn('error', self.prompt(c))
        with self.subTest('ignored model switch refuses prompts'):
            c = self.client(IGNORE_MODEL='1')
            self.new(c)
            self.assertIn('error', self.model(c, 'claude-sonnet-5.5'))
            self.assertIn('error', self.prompt(c))
        with self.subTest('model switch retains medium when backend resets effort'):
            c = self.client(MODEL_RESETS_EFFORT='1')
            self.new(c)
            self.effort(c, 'medium')
            response = self.model(c, 'claude-sonnet-5.5')
            self.assertEqual((self.current(response, 'model'), self.current(response, 'effortLevel')), ('claude-sonnet-5.5', 'medium'))
            observed = self.prompt(c)['result']['observed']
            self.assertEqual((observed['model'], observed['effort']), ('claude-sonnet-5.5', 'medium'))
        with self.subTest('waits for model catalog that loads after the response'):
            c = self.client(CATALOG_LATE='1')
            created = self.new(c)
            self.assertEqual((self.current(created, 'model'), self.current(created, 'effortLevel')), ('claude-opus-5.5', 'low'))
            observed = self.prompt(c)['result']['observed']
            self.assertEqual((observed['model'], observed['effort']), ('claude-opus-5.5', 'low'))

    def test_failed_load_keeps_pending_state_or_clears_authorization(self):
        with self.subTest('inventory changed while confirming a same-process load'):
            c = self.client(LOAD_UNSAFE_AT_CONFIRM='1')
            self.assertIn('result', self.new(c))
            self.assertEqual(c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=[])['error']['message'],
                             'Kiro exposed tools outside the Peer allowlist')
            self.assertIn('error', self.prompt(c))
        with self.subTest('rejected load does not disturb a pending selection'):
            c = self.client()
            self.assertIn('result', self.new(c))
            c.send('session/set_config_option',
                   {'sessionId': 'seat', 'configId': 'effortLevel', 'value': 'medium'}, 'e')
            self.assertEqual(c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=['paseo'])
                             ['error']['message'], 'Kiro Peer does not accept injected MCP servers')
            self.assertIn('result', c.response('e'))
        with self.subTest('load restoring an unsupported model clears authorization'):
            c = self.client(BAD_LOAD_MODEL='1')
            self.assertIn('result', self.new(c))
            self.effort(c, 'medium')
            self.assertEqual(c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=[])
                             ['error']['message'], 'Kiro restored an unsupported mode/model')
            self.assertIn('error', self.prompt(c, 'x'))

    def test_resume_validates_servers_and_cwd_for_both_roles(self):
        bad = [{'command': 'x'},
               {'type': 'http', 'name': 'x', 'url': 'http://x/mcp/agents?callerAgentId=x', 'headers': []},
               PASEO]
        for role in ('peer', 'lead'):
            c = self.client(role)
            for servers in bad:
                with self.subTest(role=role, servers=servers):
                    r = c.call('session/resume', sessionId='seat', cwd=str(self.cwd), mcpServers=servers)
                    self.assertIn('error', r)
                    self.assertNotEqual(r['error']['message'], 'unknown')
            with self.subTest(role=role, servers=[]):
                r = c.call('session/resume', sessionId='seat', cwd=str(self.cwd), mcpServers=[])
                self.assertEqual(r['error']['message'], 'unknown')  # forwarded to backend
        with self.subTest('lead resume rejects bad cwd and forwarded resume clears session'):
            c = self.client('lead', EXTRA_TOOLS=LEAD_TAGS)
            self.assertIn('result', self.new(c, [PASEO]))
            self.effort(c, 'medium')
            self.assertEqual(c.call('session/resume', sessionId='seat', cwd='/nope', mcpServers=[])
                             ['error']['message'], 'Kiro Lead requires an existing absolute CWD')
            self.assertEqual(c.call('session/resume', sessionId='seat', cwd=str(self.cwd), mcpServers=[])
                             ['error']['message'], 'unknown')
            self.assertIn('error', self.prompt(c, 'x'))

    def test_peer_tool_inventory_and_mcp_rejection(self):
        with self.subTest('seat-owned Peer config'):
            peer = json.loads((ROOT / 'setup/kiro-peer.json').read_text())
            self.assertFalse([t for t in peer['tools'] if t.startswith('@') or t in ('subagent', '*')])
            self.assertNotIn('allowedTools', peer)  # V3 skips profiles with allowedTools but no permissions.
            self.assertEqual((peer['name'], peer['mcpServers'], peer['includeMcpJson']), ('epistex_peer', {}, False))
        c = self.client()
        for method in ('session/new', 'session/load'):
            with self.subTest(method=method):
                response = c.call(method, sessionId='seat', cwd=str(self.cwd), mcpServers=[PASEO])
                self.assertEqual(response['error']['message'], 'Kiro Peer does not accept injected MCP servers')
        for tool in ('list_agents', '@paseo/list_agents', 'subagent'):
            with self.subTest(tool=tool):
                c = self.client(EXTRA_TOOLS=tool)
                self.assertEqual(self.new(c)['error']['message'], 'Kiro exposed tools outside the Peer allowlist')
                self.assertIn('error', self.prompt(c))
        with self.subTest('backend switches to an unsafe mode'):
            self.assertIn('error', self.new(self.client(UNSAFE_MODE='1')))
        with self.subTest('workspace agent override'):
            c = self.client()
            self.assertIn('result', self.new(c))
            override = self.cwd / '.kiro/agents'
            override.mkdir(parents=True)
            (override / 'epistex_peer.md').write_text('---\ntools: ["*"]\n---\n')
            self.assertEqual(self.new(c)['error']['message'],
                             'Workspace agent overrides the seat-owned Kiro Peer configuration')

    def test_lead_accepts_exact_paseo_server_and_probe_sessions_refuse_prompts(self):
        for server in (PASEO, {**PASEO, 'url': 'http://[::1]:6767/mcp/agents?callerAgentId=x'},
                       {**PASEO, 'url': 'http://localhost:1/mcp/agents?callerAgentId=x'},
                       {**PASEO, 'headers': [{'name': 'Authorization', 'value': 'Bearer 0f1e'}]}):
            with self.subTest(server=server):
                c = self.client('lead', EXTRA_TOOLS=LEAD_TAGS)
                self.assertIn('result', self.new(c, [server]))
                observed = self.prompt(c)['result']['observed']
                self.assertEqual((observed['servers'], observed['mode']), ([server], 'epistex_lead'))
                self.assertEqual(observed['prompt'][0]['text'],
                                 'Role instructions for this session:\n'
                                 + (ROOT / 'agents/contract/COMMON.md').read_text().rstrip() + '\n\n'
                                 + (ROOT / 'agents/LEAD.md').read_text())
                self.assertIn('result', c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=[server]))
        refusal = 'Kiro Lead session has no injected Paseo MCP server; prompts are refused'
        for method in ('session/new', 'session/load'):
            with self.subTest(probe=method):
                c = self.client('lead')
                params = {'cwd': str(self.cwd), 'mcpServers': []}
                if method == 'session/load': params['sessionId'] = 'seat'
                self.assertIn('result', c.call(method, **params))
                self.assertEqual(self.current(self.effort(c, 'medium'), 'effortLevel'), 'medium')
                self.assertIn('result', self.model(c, 'claude-sonnet-5.5'))
                self.assertEqual(self.prompt(c)['error']['message'], refusal)
        with self.subTest(probe='session/load over injected session'):
            c = self.client('lead', EXTRA_TOOLS=LEAD_TAGS)
            self.assertIn('result', self.new(c, [PASEO]))
            self.assertIn('result', c.call('session/load', sessionId='seat', cwd=str(self.cwd), mcpServers=[]))
            self.assertEqual(self.prompt(c)['error']['message'], refusal)

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
        self.assertIn('error', self.prompt(c))

    def test_lead_inventory_policy_and_late_mcp_tools(self):
        with self.subTest('seat-owned Lead config matches the repo Lead policy'):
            lead = json.loads((ROOT / 'setup/kiro-lead.json').read_text())
            peer = json.loads((ROOT / 'setup/kiro-peer.json').read_text())
            paseo = [t[len('@paseo/'):] for t in lead['tools'] if t.startswith('@')]
            self.assertEqual(paseo, LEAD_POLICY)
            self.assertEqual([t for t in lead['tools'] if not t.startswith('@')], peer['tools'])
            script = (ROOT / 'setup/setup-seats.sh').read_text()
            deny = json.loads(script.split("expected_deny_lead='", 1)[1].split("'", 1)[0])
            self.assertEqual(set(deny) & set(paseo), set())
            mcp = [r for r in lead['permissions']['rules'] if r['capability'] == 'mcp']
            self.assertEqual(mcp, [{'capability': 'mcp', 'match': ['paseo/' + t for t in LEAD_POLICY], 'effect': 'allow'}])
            self.assertEqual([r for r in lead['permissions']['rules'] if r['capability'] != 'mcp'], peer['permissions']['rules'])
            self.assertEqual((lead['name'], lead['mcpServers'], lead['includeMcpJson']), ('epistex_lead', {}, False))
        missing_one = LEAD_TAGS.rsplit(',', 1)[0]  # connected Paseo server missing one policy tool
        for tool in ('@paseo/kill_agent', 'list_workspaces', '@other/list_agents', 'subagent', missing_one):
            with self.subTest(tool=tool):
                c = self.client('lead', EXTRA_TOOLS=tool)
                self.assertEqual(self.new(c, [PASEO])['error']['message'], 'Kiro exposed tools outside the Lead allowlist')
                self.assertIn('error', self.prompt(c))
        with self.subTest('Paseo tools connect after the session response'):
            c = self.client('lead', EXTRA_TOOLS=LEAD_TAGS, MCP_LATE='1')
            self.assertIn('result', self.new(c, [PASEO]))
            self.assertIn('result', self.prompt(c))
        with self.subTest('late Paseo tools missing one policy tool'):
            c = self.client('lead', EXTRA_TOOLS=missing_one, MCP_LATE='1')
            self.assertEqual(self.new(c, [PASEO])['error']['message'], 'Kiro exposed tools outside the Lead allowlist')
        with self.subTest('workspace agent override'):
            c = self.client('lead')
            (self.cwd / '.kiro/agents').mkdir(parents=True)
            (self.cwd / '.kiro/agents/epistex_lead.json').write_text('{"tools":["*"]}')
            self.assertEqual(self.new(c, [PASEO])['error']['message'],
                             'Workspace agent overrides the seat-owned Kiro Lead configuration')

    def test_hidden_options_extensions_unknown_methods_and_compact_gate(self):
        c = self.client()
        with self.subTest('compact before confirmation'):
            self.assertEqual(c.call('_kiro/session/compact', sessionId='seat')['error']['message'],
                             'Kiro Peer session/mode/model/effort/tool policy is not confirmed')
        init = c.call('initialize', protocolVersion=1, clientCapabilities={})
        self.assertEqual(init['result']['agentCapabilities']['_meta']['kiro']['extensionMethods'],
                         ['_kiro/session/context', '_kiro/session/compact'])
        self.assertIn('result', self.new(c))
        with self.subTest('compact after confirmation'):
            self.assertIn('result', c.call('_kiro/session/compact', sessionId='seat'))
        for config_id, value in (('autopilot', 'off'), ('mode', 'vibe'), ('mode', 'epistex_peer'),
                                 ('memoryReflection', 'on'), ('model', 'auto'), ('effortLevel', 'high')):
            with self.subTest(config_id=config_id, value=value):
                self.assertIn('error', c.call('session/set_config_option', sessionId='seat', configId=config_id, value=value))
        for method in ('_kiro/workflow/new', '_kiro/mcp/resetServer', '_kiro.dev/commands/execute', '_session/steer',
                       '_session/spawn', 'session/set_model', 'session/set_mode', 'session/fork', 'session/delete',
                       'session/list'):
            with self.subTest(method=method):
                self.assertEqual(c.call(method, sessionId='seat', cwd=str(self.cwd), mcpServers=[], modeId='vibe',
                                        modelId='claude-sonnet-5.5')['error']['code'], -32601)
        observed = self.prompt(c)['result']['observed']
        self.assertEqual((observed['mode'], observed['model'], observed['effort']), ('epistex_peer', 'claude-opus-5.5', 'low'))
        lead = self.client('lead')
        for method in ('session/set_mode', 'session/fork', 'session/delete', 'session/list'):
            with self.subTest(role='lead', method=method):
                self.assertEqual(lead.call(method, sessionId='seat', cwd=str(self.cwd), mcpServers=[], modeId='vibe')
                                 ['error']['code'], -32601)

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
        for method in ('unsupported/request', '_kiro/auth/getAccessToken', '_kiro/openExternalUrl'):
            response = c.call('authenticate', method=method)
            self.assertEqual(response['result']['reply']['error']['code'], -32601)
        self.assertIn('error', c.call('authenticate', exit=1))
        self.assertEqual(c.process.wait(timeout=5), 7)
        c = self.client()
        self.new(c)
        observed = self.prompt(c)['result']['observed']
        c.process.terminate()
        self.assertNotEqual(c.process.wait(timeout=5), 0)
        with self.assertRaises(ProcessLookupError):
            os.kill(observed['pid'], 0)

    def test_mid_prompt_revocation_and_pipelining(self):
        for flags in ({'MIDPROMPT_UNSAFE': '1'}, {'MIDPROMPT_MODE': '1'}):
            with self.subTest(flags=flags):
                c = self.client(**flags)
                self.assertIn('result', self.new(c))
                self.effort(c, 'medium')
                c.send('session/prompt', {'sessionId': 'seat', 'prompt': [{'type': 'text', 'text': 'wait'}]}, 'w')
                self.assertEqual(c.response('w')['result']['stopReason'], 'cancelled')
                self.assertIn('error', self.prompt(c, 'x'))
        with self.subTest('pipelined session/new and session/load'):
            c = self.client()
            c.send('session/new', {'cwd': str(self.cwd), 'mcpServers': []}, 'n')
            c.send('session/load', {'sessionId': 'seat', 'cwd': str(self.cwd), 'mcpServers': []}, 'l')
            self.assertIn('result', c.response('n'))
            self.assertIn('result', c.response('l'))


@unittest.skipUnless(os.getenv('EPISTEX_REAL_KIRO_PROBE') == '1', 'real metadata probe is opt-in; no model prompts')
class RealKiroMetadataTest(unittest.TestCase):
    def test_four_selections_and_load_without_model_prompts(self):
        current = KiroACPTest.current
        c = Client(os.environ.copy(), ROOT, trace=True)
        try:
            init = c.call('initialize', protocolVersion=1, clientCapabilities={})
            self.assertTrue(init['result']['agentCapabilities']['loadSession'])
            result = c.call('session/new', cwd=str(ROOT), mcpServers=[])
            self.assertEqual((result['result']['modes']['currentModeId'], current(result, 'mode')),
                             ('epistex_peer', 'epistex_peer'))
            self.assertIn(current(result, 'effortLevel'), ('low', 'medium'))
            sid = result['result']['sessionId']
            tags = [t['tag'] for m in c.notifications if m.get('method') == '_kiro/tools/didChange'
                    for t in m['params']['tags']]
            self.assertTrue(tags and not [t for t in tags if t.startswith('@') or t == 'subagent'])
            for model in ('claude-opus-5.5','claude-sonnet-5.5'):
                response = c.call('session/set_config_option', sessionId=sid, configId='model', value=model)
                self.assertEqual(current(response, 'model'), model)
                for effort in ('low','medium'):
                    response = c.call('session/set_config_option', sessionId=sid, configId='effortLevel', value=effort)
                    self.assertEqual((current(response, 'model'), current(response, 'effortLevel')), (model, effort))
            for config_id, value in (('mode', 'vibe'), ('effortLevel', 'high'), ('autopilot', 'off')):
                self.assertIn('error', c.call('session/set_config_option', sessionId=sid, configId=config_id, value=value))
            self.assertIn('error', c.call('session/set_mode', sessionId=sid, modeId='vibe'))
            loaded = c.call('session/load', sessionId=sid, cwd=str(ROOT), mcpServers=[])
            self.assertEqual((current(loaded, 'model'), current(loaded, 'effortLevel')), ('claude-sonnet-5.5', 'medium'))
        finally: c.close()
        resumed = Client(os.environ.copy(), ROOT, trace=True)
        try:
            resumed.call('initialize', protocolVersion=1, clientCapabilities={})
            response = resumed.call('session/load', sessionId=sid, cwd=str(ROOT), mcpServers=[])
            self.assertEqual(response['result']['modes']['currentModeId'], 'epistex_peer')
            self.assertEqual((current(response, 'model'), current(response, 'effortLevel')), ('claude-sonnet-5.5', 'medium'))
        finally: resumed.close()


if __name__ == '__main__':
    unittest.main()
