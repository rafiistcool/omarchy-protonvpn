"""CLI contract tests; all subprocesses use a fake protonvpn, never a tunnel."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ctl', ROOT / 'ctl.py')
ctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctl)

COUNTRIES = '''Server list is outdated, updating... This may take a moment.
Country                           Code
--------------------------------  ------
United States                     US
Canada                            CA
'''
CONNECTED = 'Status: Connected\nServer: US#10 in Shared City, United States\nLoad: 37%\nProtocol: wireguard\n'


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'],
                        XDG_CACHE_HOME=str(self.root / 'cache'), FAKE_ROOT=str(self.root))
        executable = self.root / 'protonvpn'
        executable.write_text('''#!/usr/bin/env python3
import json,os,sys,time
from pathlib import Path
root=Path(os.environ['FAKE_ROOT'])
args=sys.argv[1:]
with (root/'calls').open('a') as f: f.write(json.dumps(args)+'\\n')
responses=json.loads((root/'responses').read_text())
response=responses.get(json.dumps(args))
if response is None:
 print('Error: Unexpected CLI arguments', file=sys.stderr);sys.exit(99)
time.sleep(response.get('delay',0))
print(response.get('stdout',''))
print(response.get('stderr',''),file=sys.stderr)
sys.exit(response.get('code',0))
''')
        executable.chmod(0o755)
        self.responses = {}
        self.reply(['info'], "Account: 'test-account'")
        self.reply(['status'], 'Status: Disconnected')
        self.reply(['countries', 'list'], COUNTRIES)
        self.reply(['cities', 'list', 'US'], 'Cities in United States:\nCity         Features\n-----------  --------\nShared City  P2P')
        def server(**kwargs):
            return dict(dict(Name='US#10', ExitCountry='US', City='Shared City', Tier=1,
                             Status=1, Features=0, Score=10), **kwargs)
        self.cache = {'MaxTier': 1, 'LogicalServers': [
            server(Name='CA#1', ExitCountry='CA', Score=1),
            server(Name='US#1', Status=0, Score=1),
            server(Name='US#2', Tier=2, Score=1),
            server(Name='US#3', Features=1, Score=1),
            server(Name='US#4', Features=2, Score=1), server()]}
        cache = self.root / 'cache/Proton/VPN/serverlist.json'
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps(self.cache))

    def reply(self, args, output='', **kwargs):
        self.responses[json.dumps(args)] = dict(stdout=output, **kwargs)
        (self.root / 'responses').write_text(json.dumps(self.responses))

    def run_helper(self, *args):
        result = subprocess.run(['/usr/bin/python3', str(ROOT/'ctl.py'), *args],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stderr, '')
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0 if payload['ok'] else 1)
        return payload

    def calls(self):
        return [json.loads(line) for line in (self.root/'calls').read_text().splitlines()]

    def test_status_uses_cli_and_does_not_disclose_account(self):
        result = self.run_helper('status')
        self.assertTrue(result['loggedIn'])
        self.assertFalse(result['connected'])
        self.assertNotIn('test-account', json.dumps(result))
        self.reply(['info'], "Account: 'None'")
        self.assertFalse(self.run_helper('status')['loggedIn'])

    def test_connected_status_with_refresh_preamble_and_cache_metadata(self):
        self.reply(['status'], 'Server list is outdated, updating...\n' + CONNECTED)
        result = self.run_helper('status')
        self.assertTrue(result['connected'])
        self.assertEqual((result['country'], result['city'], result['load']), ('US', 'Shared City', 37))
        self.assertNotIn(['info'], self.calls())

    def test_country_names_and_city_counts(self):
        result = self.run_helper('countries')
        self.assertEqual(result['countries'][0], {'code':'US','name':'United States','servers':1,
                                                 'cities':[{'name':'Shared City','servers':1}]})

    def test_city_uses_explicit_server_in_selected_country(self):
        self.reply(['connect', '--', 'US#10'], 'Connected to US#10 in Shared City, United States.')
        self.reply(['status'], CONNECTED)
        result = self.run_helper('connect', 'city', 'Shared City', '--country', 'US')
        self.assertTrue(result['connected'])
        self.assertEqual(self.calls(), [['cities','list','US'], ['connect','--','US#10'], ['status']])

    def test_city_without_country_is_rejected(self):
        result = self.run_helper('connect', 'city', 'Shared City')
        self.assertFalse(result['ok'])
        self.assertFalse((self.root/'calls').exists())

    def test_missing_cache_does_not_connect_city_somewhere_else(self):
        (self.root/'cache/Proton/VPN/serverlist.json').unlink()
        self.assertFalse(self.run_helper('connect','city','Shared City','--country','US')['ok'])
        self.assertEqual(self.calls(), [['cities','list','US']])

    def test_zero_exit_gui_guard_and_nonzero_error_are_reported(self):
        self.reply(['status'], 'Error: Proton VPN desktop app is currently running')
        result = self.run_helper('status')
        self.assertFalse(result['ok'])
        self.assertIn('desktop app', result['error'])
        self.reply(['status'], stderr='Error: Authentication required.', code=2)
        self.assertEqual(self.run_helper('status')['error'], 'Authentication required.')

    def test_unknown_status_is_not_claimed_as_disconnected(self):
        self.reply(['status'], 'Status: Connecting')
        self.assertFalse(self.run_helper('status')['ok'])

    def test_connect_requires_confirmation_and_actual_connected_status(self):
        self.reply(['connect'], 'Your plan does not support this operation.')
        self.assertFalse(self.run_helper('connect','fastest')['ok'])
        self.reply(['connect'], 'Connected to US#10 in Shared City, United States.')
        self.assertFalse(self.run_helper('connect','fastest')['ok'])

    def test_country_connect_uses_documented_option(self):
        self.reply(['connect','--country','US'], 'Connected to US#10 in Shared City, United States.')
        self.reply(['status'], CONNECTED)
        self.assertTrue(self.run_helper('connect','country','us')['connected'])

    def test_disconnect_checks_actual_state_without_country_refresh(self):
        self.reply(['disconnect'], 'Disconnected.')
        self.reply(['status'], CONNECTED)
        self.assertFalse(self.run_helper('disconnect')['ok'])
        self.reply(['status'], 'Status: Disconnected')
        self.assertFalse(self.run_helper('disconnect')['connected'])
        self.assertNotIn(['countries','list'], self.calls())

    def test_timeout_is_bounded(self):
        self.reply(['status'], 'Status: Disconnected', delay=1)
        with patch.dict(os.environ, self.env):
            with self.assertRaisesRegex(ctl.CliError, 'timed out'):
                ctl.CLI(seconds=.1).run('status')


if __name__ == '__main__': unittest.main()
