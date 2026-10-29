"""CLI contract tests; all subprocesses use a fake protonvpn and nmcli, never a tunnel."""
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
CONNECTED = 'ProtonVPN US#10:wireguard:activated'


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
if isinstance(response, list):
 count=(root/'calls').read_text().splitlines().count(json.dumps(args))
 response=response[min(count, len(response))-1]
time.sleep(response.get('delay',0))
print(response.get('stdout',''))
print(response.get('stderr',''),file=sys.stderr)
sys.exit(response.get('code',0))
''')
        executable.chmod(0o755)
        nmcli = self.root / 'nmcli'
        nmcli.write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
root=Path(os.environ['FAKE_ROOT'])
assert sys.argv[1:] == ['-t','-f','NAME,TYPE,STATE','connection','show','--active'], sys.argv
if (root/'nm_fail').exists(): sys.exit(8)
print((root/'nm').read_text() if (root/'nm').exists() else '', end='')
''')
        nmcli.chmod(0o755)
        self.responses = {}
        self.reply(['info'], "Account: 'test-account'")
        self.reply(['countries', 'list'], COUNTRIES)
        self.reply(['cities', 'list', 'US'], 'Cities in United States:\nCity         Features\n-----------  --------\nShared City  P2P')
        def server(**kwargs):
            return dict(dict(Name='US#10', ExitCountry='US', City='Shared City', Tier=1,
                             Status=1, Features=0, Score=10, Load=37), **kwargs)
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
        self.replies(args, dict(stdout=output, **kwargs))

    def replies(self, args, *responses):
        self.responses[json.dumps(args)] = responses[0] if len(responses) == 1 else list(responses)
        (self.root / 'responses').write_text(json.dumps(self.responses))

    def nm(self, *lines):
        (self.root / 'nm').write_text(''.join(line + '\n' for line in lines))

    def run_helper(self, *args):
        result = subprocess.run(['/usr/bin/python3', str(ROOT/'ctl.py'), *args],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stderr, '')
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0 if payload['ok'] else 1)
        return payload

    def calls(self):
        return [json.loads(line) for line in (self.root/'calls').read_text().splitlines()]

    def test_disconnected_status_checks_account_without_disclosing_it(self):
        self.nm('Office Wi-Fi:802-11-wireless:activated')
        result = self.run_helper('status')
        self.assertTrue(result['loggedIn'])
        self.assertFalse(result['connected'])
        self.assertNotIn('test-account', json.dumps(result))
        self.reply(['info'], "Account: 'None'")
        self.assertFalse(self.run_helper('status')['loggedIn'])

    def test_connected_status_comes_from_networkmanager_without_starting_the_cli(self):
        # `protonvpn status` contacts the server and re-applies the kill switch; routine checks must not.
        self.run_helper('countries')  # remembers country names
        (self.root/'calls').unlink()
        self.nm('Office Wi-Fi:802-11-wireless:activated', CONNECTED)
        result = self.run_helper('status')
        self.assertEqual((result['connected'], result['loggedIn'], result['server'], result['country'],
                          result['countryName'], result['city'], result['load']),
                         (True, True, 'US#10', 'US', 'United States', 'Shared City', 37))
        self.assertFalse((self.root/'calls').exists())

    def test_tunnel_still_activating_is_not_connected(self):
        self.nm('ProtonVPN US#10:wireguard:activating')
        self.assertFalse(self.run_helper('status')['connected'])

    def test_unreadable_networkmanager_is_not_claimed_as_disconnected(self):
        (self.root/'nm_fail').touch()
        self.assertFalse(self.run_helper('status')['ok'])

    def test_country_names_and_city_counts(self):
        result = self.run_helper('countries')
        self.assertEqual(result['countries'][0], {'code':'US','name':'United States','servers':1,
                                                 'cities':[{'name':'Shared City','servers':1}]})

    def test_city_uses_explicit_server_in_selected_country(self):
        self.reply(['connect', '--', 'US#10'], 'Connected to US#10 in Shared City, United States.')
        self.nm(CONNECTED)
        result = self.run_helper('connect', 'city', 'Shared City', '--country', 'US')
        self.assertTrue(result['connected'])
        self.assertEqual(self.calls(), [['cities','list','US'], ['connect','--','US#10']])

    def test_city_without_country_is_rejected(self):
        result = self.run_helper('connect', 'city', 'Shared City')
        self.assertFalse(result['ok'])
        self.assertFalse((self.root/'calls').exists())

    def test_missing_cache_does_not_connect_city_somewhere_else(self):
        (self.root/'cache/Proton/VPN/serverlist.json').unlink()
        self.assertFalse(self.run_helper('connect','city','Shared City','--country','US')['ok'])
        self.assertEqual(self.calls(), [['cities','list','US']])

    def test_zero_exit_gui_guard_and_nonzero_error_are_reported(self):
        self.reply(['info'], 'Error: Proton VPN desktop app is currently running')
        result = self.run_helper('status')
        self.assertFalse(result['ok'])
        self.assertIn('desktop app', result['error'])
        self.reply(['info'], stderr='Error: Authentication required.', code=2)
        self.assertEqual(self.run_helper('status')['error'], 'Authentication required.')

    def test_connect_requires_confirmation_and_actual_connected_status(self):
        self.reply(['connect'], 'Your plan does not support this operation.')
        self.assertFalse(self.run_helper('connect','fastest')['ok'])
        self.reply(['connect'], 'Connected to US#10 in Shared City, United States.')
        self.assertFalse(self.run_helper('connect','fastest')['ok'])

    def test_country_connect_uses_documented_option(self):
        self.reply(['connect','--country','US'], 'Connected to US#10 in Shared City, United States.')
        self.nm(CONNECTED)
        self.assertTrue(self.run_helper('connect','country','us')['connected'])

    def test_connect_retries_once_when_cli_exits_without_a_reason(self):
        # CLI 1.0 rolls back and exits 1 silently when the server misses its 10 s handshake.
        self.replies(['connect','--country','US'], dict(code=1),
                     dict(stdout='Connected to US#10 in Shared City, United States.'))
        self.nm(CONNECTED)
        self.assertTrue(self.run_helper('connect','country','US')['connected'])
        self.assertEqual(self.calls().count(['connect','--country','US']), 2)

    def test_second_silent_connect_failure_is_explained(self):
        self.replies(['connect','--country','US'], dict(code=1), dict(code=1))
        result = self.run_helper('connect','country','US')
        self.assertIn('did not confirm the connection in time', result['error'])
        self.assertEqual(self.calls().count(['connect','--country','US']), 2)

    def test_explicit_connect_errors_are_not_retried(self):
        self.reply(['connect','--country','US'], stderr='Error: Connection failed. Try a different server.', code=1)
        self.assertIn('different server', self.run_helper('connect','country','US')['error'])
        self.assertEqual(self.calls().count(['connect','--country','US']), 1)

    def test_disconnect_checks_actual_state_without_country_refresh(self):
        self.reply(['disconnect'], 'Disconnected.')
        self.nm(CONNECTED)
        self.assertFalse(self.run_helper('disconnect')['ok'])
        self.nm()
        self.assertFalse(self.run_helper('disconnect')['connected'])
        self.assertNotIn(['countries','list'], self.calls())

    def test_timeout_is_bounded(self):
        self.reply(['info'], "Account: 'test-account'", delay=1)
        with patch.dict(os.environ, self.env):
            with self.assertRaisesRegex(ctl.CliError, 'timed out'):
                ctl.CLI(seconds=.1).run('info')


if __name__ == '__main__': unittest.main()
