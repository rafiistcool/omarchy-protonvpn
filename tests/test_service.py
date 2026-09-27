"""Exercise actual QML with a fake VPN helper; never touches a tunnel."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('qs'), 'requires Quickshell')
class ServiceTests(unittest.TestCase):
    def test_connection_is_confirmed_and_stale_status_cannot_overwrite_it(self):
        with tempfile.TemporaryDirectory(prefix='vpn-qml-') as temp:
            root = Path(temp)
            for name in ('Vpn', 'Commons', 'runtime'):
                (root / name).mkdir(mode=0o700)
            for name in ('Service.qml', 'Model.js'):
                shutil.copy2(ROOT / name, root / 'Vpn' / name)
            (root / 'Commons/qmldir').write_text('module qs.Commons\nsingleton Util 1.0 Util.qml\n')
            (root / 'Commons/Util.qml').write_text('pragma Singleton\nimport QtQml\nQtObject { function execArgv(argv) {} }\n')
            (root / 'Vpn/ctl.py').write_text('''import json,sys,time,os
from pathlib import Path
root=Path(os.environ['VPN_TEST_ROOT'])
command=sys.argv[1]
if command == 'countries':
 print(json.dumps({'ok':True,'countries':[]}))
elif command == 'status':
 if (root/'queried').exists(): time.sleep(.4)
 (root/'queried').touch()
 print(json.dumps({'ok':True,'loggedIn':True,'connected':False}))
else:
 assert sys.argv[1:] == ['connect','city','Shared City','--country','US'], sys.argv
 time.sleep(.15)
 print(json.dumps({'ok':True,'loggedIn':True,'connected':True,'country':'US','city':'Shared City'}))
''')
            (root / 'shell.qml').write_text('''import QtQuick
import Quickshell
import "Vpn" as Vpn
ShellRoot {
  Vpn.Service { id: service }
  property int stage: 0
  property double connectedAt: 0
  Timer {
    interval: 20; running: true; repeat: true
    onTriggered: {
      if (stage === 0 && service.loggedIn && !service.busy) {
        service.refresh(false)
        service.connectCity("US", "Shared City")
        if (service.active) { console.log("VPN_TEST_EARLY_ACTIVE"); Qt.quit(); return }
        stage = 1
      } else if (stage === 1 && service.connected && !service.toggling) {
        connectedAt = Date.now()
        stage = 2
      } else if (stage === 2 && Date.now() - connectedAt > 500) {
        if (service.active && service.country === "US") console.log("VPN_TEST_PASS")
        else console.log("VPN_TEST_STALE_STATUS")
        Qt.quit()
      }
    }
  }
}
''')
            env = dict(os.environ, QT_QPA_PLATFORM='offscreen', XDG_RUNTIME_DIR=str(root / 'runtime'), VPN_TEST_ROOT=str(root))
            result = subprocess.run(['qs', '-p', str(root), '--no-color'], env=env,
                                    capture_output=True, text=True, timeout=8)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('VPN_TEST_PASS', result.stdout + result.stderr)

if __name__ == '__main__': unittest.main()
