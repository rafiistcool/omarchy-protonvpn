"""Verify idle work, event coalescing and on-demand lists in actual QML."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('qs'), 'requires Quickshell')
class IdleTests(unittest.TestCase):
    def test_event_bursts_and_cached_country_lists(self):
        with tempfile.TemporaryDirectory(prefix='vpn-idle-') as temp:
            root = Path(temp)
            for name in ('Vpn', 'Commons', 'runtime', 'bin'):
                (root/name).mkdir(mode=0o700)
            for name in ('Service.qml', 'Model.js', 'Backend.qml', 'qmldir'):
                shutil.copy2(ROOT/name, root/'Vpn'/name)
            (root/'Commons/qmldir').write_text('module qs.Commons\nsingleton Util 1.0 Util.qml\n')
            (root/'Commons/Util.qml').write_text('pragma Singleton\nimport QtQml\nQtObject { function execArgv(argv) {} }\n')
            monitor = root/'bin/nmcli'
            monitor.write_text('#!/usr/bin/python3\nimport time\ntime.sleep(30)\n')
            monitor.chmod(0o755)
            (root/'Vpn/ctl.py').write_text('''import json,sys,os
from pathlib import Path
with (Path(os.environ['VPN_TEST_ROOT'])/'calls').open('a') as f: f.write(sys.argv[1]+'\\n')
if sys.argv[1]=='countries': print(json.dumps({'ok':True,'countries':[]}))
else: print(json.dumps({'ok':True,'connected':False,'loggedIn':True}))
''')
            (root/'shell.qml').write_text('''import QtQuick
import Quickshell
import "Vpn" as Vpn
ShellRoot {
  property var service: Vpn.Backend
  property var otherMonitor: Vpn.Backend
  property int stage: 0
  property double started: Date.now()
  Timer {
    interval: 50; running: true; repeat: true
    onTriggered: {
      if (service.busy || !service.loggedIn) return
      if (stage === 0) {
        if (service !== otherMonitor || service.refreshIntervalSec !== 300 || service.countriesLoadedAt !== 0) {
          console.log("BAD_STARTUP"); Qt.quit(); return
        }
        service.networkChanged(); service.networkChanged(); service.networkChanged()
        started = Date.now(); stage = 1
      } else if (stage === 1 && Date.now() - started > 2400) {
        service.refresh(true); stage = 2
      } else if (stage === 2 && service.countriesLoadedAt > 0) {
        service.refresh(true); stage = 3
      } else if (stage === 3) {
        service.refresh(true, true); stage = 4
      } else if (stage === 4) {
        started = Date.now(); stage = 5
      } else if (stage === 5 && Date.now() - started > 2200) {
        console.log("IDLE_PASS"); Qt.quit()
      }
    }
  }
}
''')
            env = dict(os.environ, QT_QPA_PLATFORM='offscreen', XDG_RUNTIME_DIR=str(root/'runtime'),
                       VPN_TEST_ROOT=str(root), PATH=str(root/'bin')+os.pathsep+os.environ['PATH'])
            result = subprocess.run(['qs','-p',str(root),'--no-color'],env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('IDLE_PASS',result.stdout+result.stderr)
            calls=(root/'calls').read_text().splitlines()
            self.assertEqual(calls.count('status'),5,calls) # startup, one event burst, three explicit refreshes
            self.assertEqual(calls.count('countries'),2,calls) # first open and explicit force only
