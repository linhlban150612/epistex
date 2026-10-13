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
unsafe_during_confirmation = False
policy = {'mcpServers': [], 'trusted': []}
def emit(m):
    print(json.dumps({'jsonrpc':'2.0', **m}), flush=True)
for line in sys.stdin:
    m=json.loads(line); method=m.get('method'); p=m.get('params',{}); ident=m.get('id')
    if method == 'initialize':
        emit({'id':ident,'result':{'protocolVersion':1,'agentCapabilities':{'loadSession':True},'_meta':{'future':'keep'}}})
    elif method in ('session/new','session/load'):
        cwd=p['cwd']; mode='kiro_default' if os.getenv('UNSAFE_MODE') else 'epistex_peer'
        result={'modes':{'currentModeId':mode,'availableModes':[{'id':mode,'name':mode}]},
                'models':{'currentModelId':model,'availableModels':[{'modelId':model,'name':model},{'modelId':'claude-sonnet-5.5','name':'Sonnet'}]},
                '_meta':{'future':'retain'}}
        if method=='session/new': result['sessionId']='seat'
        emit({'id':ident,'result':result})
        unsafe_during_confirmation = method=='session/load' and bool(os.getenv('LOAD_UNSAFE_AT_CONFIRM'))
        emit({'method':'_kiro.dev/commands/available','params':{'sessionId':'seat','commands':[{'name':'/effort'}],
              'tools':['read','shell'] + (['subagent'] if os.getenv('UNSAFE_TOOLS') else []),'_meta':{'new':'retain'}}})
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
        if p['prompt'][-1].get('text')=='wait':pending_prompt=ident;continue
        emit({'id':ident,'result':{'stopReason':'end_turn','observed':{'effort':effort,'model':model,'cwd':cwd,'prompt':p['prompt'],'pid':os.getpid()}}})
    elif method=='session/cancel':
        emit({'method':'session/update','params':{'sessionId':'seat','update':{'sessionUpdate':'future_update','_meta':{'opaque':5}}}})
        if pending_prompt is not None:emit({'id':pending_prompt,'result':{'stopReason':'cancelled'}});pending_prompt=None
    elif method=='probe/client-request':
        emit({'id':'backend-ask','method':p['method'],'params':{'sessionId':'seat','options':[]}})
        request_id=ident
    elif not method and ident=='backend-ask':
        emit({'id':request_id,'result':{'reply':m}})
    elif method=='probe/exit':sys.exit(7)
    elif method:
        emit({'id':ident,'error':{'code':-32601,'message':'unknown','data':{'method':method}}})
'''


class Client:
    def __init__(self, env, cwd, trace=False):
        self.trace = trace
        self.process = subprocess.Popen([sys.executable, str(ROOT / 'setup/role-agent'), 'peer', 'kiro'],
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
        shutil.copyfile(ROOT / 'setup/kiro-peer.json', runtime / 'epistex_peer.json')
        binary = self.home / 'kiro-cli'
        binary.write_text('#!' + sys.executable + '\n' + BACKEND)
        binary.chmod(0o755)
        self.env = {**os.environ, 'HOME': str(self.home), 'PATH': str(self.home)}
        self.clients = []

    def tearDown(self):
        for client in self.clients: client.close()
        self.temp.cleanup()

    def client(self, **flags):
        c = Client({**self.env, **flags}, self.cwd)
        self.clients.append(c)
        result = c.call('initialize', protocolVersion=1, clientCapabilities={})
        self.assertEqual(result['result']['_meta'], {'future': 'keep'})
        return c

    def new(self, client):
        return client.call('session/new', cwd=str(self.cwd), mcpServers=[])

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
        c.send('probe/client-request', {'method':'session/request_permission'}, 'permission')
        ask = c.messages.get(timeout=5)
        while ask.get('id') != 'backend-ask': ask = c.messages.get(timeout=5)
        self.assertEqual(ask['method'], 'session/request_permission')
        reply = {'jsonrpc':'2.0','id':'backend-ask','result':{'outcome':{'outcome':'cancelled'}}}
        c.write(reply)
        self.assertEqual(c.response('permission')['result']['reply'], reply)
        response = c.call('probe/client-request', method='unsupported/request')
        self.assertEqual(response['result']['reply']['error']['code'], -32601)
        self.assertIn('error', c.call('probe/exit'))
        self.assertEqual(c.process.wait(timeout=5), 7)
        c = self.client()
        self.new(c)
        observed = c.call('session/prompt', sessionId='seat', prompt=[{'type':'text','text':'inspect'}])['result']['observed']
        c.process.terminate()
        self.assertNotEqual(c.process.wait(timeout=5), 0)
        with self.assertRaises(ProcessLookupError):
            os.kill(observed['pid'], 0)


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
