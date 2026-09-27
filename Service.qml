import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import "Model.js" as Model

Item {
  id: root

  property var settings: ({})

  property bool loggedIn: false
  property bool connected: false
  readonly property bool active: connected
  property int stateRevision: 0
  property int statusRevision: 0
  property bool refreshing: false
  property bool toggling: false
  property string country: ""
  property string countryName: ""
  property string city: ""
  property string server: ""
  property var load: null
  property var countries: []
  property string actionStatus: ""
  property string lastError: ""

  readonly property int refreshIntervalSec: intSetting("refreshIntervalSec", 15, 5, 3600)
  readonly property bool busy: statusProcess.running || countriesProcess.running || actionProcess.running
  readonly property string helperPath: Model.fileUrlToPath(Qt.resolvedUrl("ctl.py"))
  readonly property bool helperReady: helperPath !== "" && helperPath.indexOf("ctl.py") !== -1

  property string _statusOutput: ""
  property string _statusError: ""
  property string _countriesOutput: ""
  property string _countriesError: ""
  property string _actionOutput: ""
  property string _actionError: ""

  function setting(name, fallback) {
    var value = settings ? settings[name] : undefined
    return value === undefined || value === null ? fallback : value
  }

  function intSetting(name, fallback, min, max) {
    var n = parseInt(String(setting(name, fallback)), 10)
    if (!isFinite(n)) n = fallback
    if (n < min) n = min
    if (n > max) n = max
    return n
  }

  function elideStatus(text) {
    var value = String(text || "").replace(/\s+/g, " ").trim()
    return value.length > 140 ? value.substring(0, 137) + "…" : value
  }

  function showOsd(message) {
    var text = String(message || "")
    if (text === "") return
    Util.execArgv(["omarchy-shell", "-q", "osd", "show", JSON.stringify({
      icon: "󰒃",
      message: text,
      duration: 1400
    })])
  }

  function applyStatus(raw) {
    var parsed = Model.parseStatus(raw)
    if (!parsed.ok) {
      lastError = parsed.error || "Status error"
      return
    }
    loggedIn = parsed.loggedIn
    connected = parsed.connected
    country = parsed.country
    countryName = parsed.countryName
    city = parsed.city
    server = parsed.server
    load = parsed.load
    if (parsed.error) lastError = parsed.error
    else if (!toggling) lastError = ""
  }

  function applyCountries(raw) {
    var parsed = Model.parseCountries(raw)
    if (!parsed.ok) {
      lastError = parsed.error || "Could not list countries"
      return
    }
    countries = parsed.countries
  }

  function refresh(withCountries) {
    if (actionProcess.running) return
    if (!helperReady) {
      lastError = "Proton VPN helper is missing"
      return
    }
    if (!statusProcess.running) {
      _statusOutput = ""
      _statusError = ""
      refreshing = true
      statusRevision = stateRevision
      statusProcess.command = ["timeout", "--kill-after=2s", "15s", "/usr/bin/python3", helperPath, "status"]
      statusProcess.running = true
    }
    if (withCountries === true && !countriesProcess.running) {
      _countriesOutput = ""
      _countriesError = ""
      countriesProcess.command = ["timeout", "--kill-after=2s", "15s", "/usr/bin/python3", helperPath, "countries"]
      countriesProcess.running = true
    }
  }

  function runAction(args, label) {
    if (!helperReady || actionProcess.running) return
    _actionOutput = ""
    _actionError = ""
    stateRevision++
    toggling = true
    lastError = ""
    actionStatus = label || ""
    actionStatusTimer.stop()
    actionProcess.command = ["timeout", "--kill-after=2s", "60s", "/usr/bin/python3", helperPath].concat(args)
    actionProcess.running = true
  }

  function connectFastest() {
    runAction(["connect", "fastest"], "Connecting to fastest server…")
  }

  function connectCountry(code) {
    var countryCode = String(code || "").toUpperCase()
    if (!/^[A-Z]{2}$/.test(countryCode)) return
    var found = Model.findCountry(countries, countryCode)
    var label = found ? String(found.name || countryCode) : countryCode
    runAction(["connect", "country", countryCode], "Connecting to " + label + "…")
  }

  function connectCity(countryCode, cityName) {
    var city = String(cityName || "").trim()
    if (city === "") return
    var code = String(countryCode || "").toUpperCase()
    if (!/^[A-Z]{2}$/.test(code)) return
    runAction(["connect", "city", city, "--country", code], "Connecting to " + city + "…")
  }

  function disconnect() {
    runAction(["disconnect"], "Disconnecting…")
  }

  function toggle() {
    if (active) disconnect()
    else {
      var recents = settings && settings.recentCountries instanceof Array ? settings.recentCountries : []
      if (recents.length > 0) connectCountry(recents[0])
      else connectFastest()
    }
  }

  function signIn() {
    Quickshell.execDetached(["omarchy", "launch", "terminal", "bash", Model.fileUrlToPath(Qt.resolvedUrl("signin.sh"))])
  }

  Timer {
    id: refreshTimer
    interval: root.refreshIntervalSec * 1000
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.refresh(root.countries.length === 0)
  }

  Timer {
    id: delayedRefresh
    interval: 700
    repeat: false
    onTriggered: root.refresh(false)
  }

  Timer {
    id: actionStatusTimer
    interval: 2400
    repeat: false
    onTriggered: root.actionStatus = ""
  }

  Process {
    id: statusProcess
    running: false
    command: []
    stdout: StdioCollector { id: statusStdout; waitForEnd: true; onStreamFinished: root._statusOutput = text }
    stderr: StdioCollector { id: statusStderr; waitForEnd: true; onStreamFinished: root._statusError = text }
    onExited: function(exitCode) {
      root.refreshing = false
      var stdout = String(statusStdout.text || root._statusOutput || "")
      var stderr = String(statusStderr.text || root._statusError || "")
      if (!actionProcess.running && root.statusRevision === root.stateRevision) {
        if (exitCode === 0) root.applyStatus(stdout)
        else root.lastError = root.elideStatus((Model.parseJson(stdout) || {}).error || stderr || "Status failed or timed out")
      }
    }
  }

  Process {
    id: countriesProcess
    running: false
    command: []
    stdout: StdioCollector { id: countriesStdout; waitForEnd: true; onStreamFinished: root._countriesOutput = text }
    stderr: StdioCollector { id: countriesStderr; waitForEnd: true; onStreamFinished: root._countriesError = text }
    onExited: function(exitCode) {
      var stdout = String(countriesStdout.text || root._countriesOutput || "")
      var stderr = String(countriesStderr.text || root._countriesError || "")
      if (exitCode === 0) root.applyCountries(stdout)
      else root.lastError = root.elideStatus((Model.parseJson(stdout) || {}).error || stderr || "Could not list countries")
    }
  }

  Process {
    id: actionProcess
    running: false
    command: []
    stdout: StdioCollector { id: actionStdout; waitForEnd: true; onStreamFinished: root._actionOutput = text }
    stderr: StdioCollector { id: actionStderr; waitForEnd: true; onStreamFinished: root._actionError = text }
    onExited: function(exitCode) {
      root.toggling = false
      var stdout = String(actionStdout.text || root._actionOutput || "")
      var stderr = String(actionStderr.text || root._actionError || "")
      var parsed = Model.parseStatus(stdout)
      if (exitCode === 0 && parsed.ok) {
        root.applyStatus(stdout)
        root.lastError = ""
        root.actionStatus = ""
        if (root.connected) {
          var label = root.city || root.countryName || root.country || "Connected"
          root.showOsd(label)
        } else {
          root.showOsd("Disconnected")
        }
      } else {
        root.lastError = parsed.error || root.elideStatus(stderr || stdout || "Proton VPN command failed")
        root.actionStatus = root.lastError
        actionStatusTimer.restart()
      }
      delayedRefresh.restart()
    }
  }
}
