import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "rafi.protonvpn"
  ipcTarget: "rafi.protonvpn"
  manageIpc: false

  property string view: "countries"
  property string focusSection: "header"
  property int listIndex: 0
  property bool cursorActive: false
  property bool searchFocused: false
  property string query: ""
  property var selectedCountry: null
  property int phraseIndex: 0

  readonly property var activePhrases: [
    "Hiding the exit",
    "Sealing the hop",
    "Routing quietly",
    "Swapping countries",
    "Guarding packets",
    "Polishing tunnels"
  ]
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color hoverFill: bar ? Style.hoverFillFor(bar.foreground, Color.accent) : "transparent"
  readonly property color selectedFill: bar ? Style.selectedFillFor(bar.foreground, Color.accent) : "transparent"
  readonly property color iconColor: vpn.active ? foreground : dim
  readonly property color barIconColor: vpn.active ? barForeground : Qt.darker(barForeground, 1.55)
  readonly property bool headerHasCursor: cursorActive && focusSection === "header"
  readonly property string toggleHint: vpn.active ? "Turn Proton VPN off" : "Turn Proton VPN on"
  readonly property var recentCodes: settings.recentCountries instanceof Array ? settings.recentCountries : []
  readonly property var filteredCountries: Model.filterCountries(vpn.countries, query)
  readonly property var filteredCities: Model.filterCities(selectedCountry && selectedCountry.cities, query)
  readonly property var listModel: view === "cities" ? filteredCities : filteredCountries
  readonly property string heroTitle: {
    if (!vpn.loggedIn && !vpn.active) return "Proton VPN"
    if (vpn.active) return vpn.countryName || vpn.country || "Proton VPN"
    return "Proton VPN"
  }
  readonly property string heroMeta: {
    if (!vpn.loggedIn && !vpn.active) return "Sign in to connect"
    if (vpn.active) return [vpn.city, vpn.server].filter(function (part) { return part && part !== "" }).join(" · ") || activePhrases[phraseIndex % activePhrases.length]
    return "Proton VPN is disconnected"
  }
  readonly property string barLabel: vpn.active ? (vpn.country || "") : ""

  function persistRecent(code) {
    var next = Model.nextRecents(recentCodes, code)
    if (!root.bar || !root.bar.shell || typeof root.bar.shell.updateEntryInline !== "function") return
    var entry = { id: root.moduleName }
    for (var key in settings) if (key !== "id") entry[key] = settings[key]
    entry.recentCountries = next
    root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  function openCountries() {
    view = "countries"
    selectedCountry = null
    listIndex = 0
    query = ""
    if (searchField) searchField.text = ""
    focusSection = "list"
  }

  function openCities(country) {
    if (!country) return
    selectedCountry = country
    view = "cities"
    listIndex = 0
    query = ""
    if (searchField) searchField.text = ""
    focusSection = "list"
  }

  function chooseCountry(country) {
    if (!country) return
    var cities = country.cities
    if (Array.isArray(cities) && cities.length > 1) {
      openCities(country)
      return
    }
    persistRecent(country.code)
    vpn.connectCountry(country.code)
  }

  function chooseCity(city) {
    if (!city || !selectedCountry) return
    persistRecent(selectedCountry.code)
    vpn.connectCity(selectedCountry.code, city.name)
  }

  function chooseFastest() {
    vpn.connectFastest()
  }

  function ensureCursor() {
    if (listIndex >= listModel.length) listIndex = Math.max(0, listModel.length - 1)
    if (focusSection === "login" && vpn.loggedIn) focusSection = "header"
    if (focusSection === "list" && listModel.length === 0) focusSection = "fastest"
  }

  function selectedItem() {
    if (listModel.length === 0) return null
    return listModel[Math.max(0, Math.min(listIndex, listModel.length - 1))]
  }

  function moveCursor(dx, dy) {
    cursorActive = true
    ensureCursor()
    if (dy === 0) return
    if (focusSection === "header") {
      if (dy > 0) focusSection = vpn.loggedIn ? "fastest" : "login"
    } else if (focusSection === "login") {
      if (dy < 0) focusSection = "header"
      else focusSection = "fastest"
    } else if (focusSection === "fastest") {
      if (dy < 0) focusSection = vpn.loggedIn ? "header" : "login"
      else if (listModel.length > 0) {
        focusSection = "list"
        listIndex = 0
      }
    } else if (focusSection === "list") {
      if (dy < 0) {
        if (listIndex <= 0) focusSection = "fastest"
        else listIndex--
      } else if (listIndex < listModel.length - 1) {
        listIndex++
      }
    }
    ensureCursor()
    scrollCursorIntoView()
  }

  function activateCursor() {
    ensureCursor()
    if (focusSection === "header") vpn.toggle()
    else if (focusSection === "login") vpn.signIn()
    else if (focusSection === "fastest") chooseFastest()
    else if (focusSection === "list") {
      var item = selectedItem()
      if (view === "cities") chooseCity(item)
      else chooseCountry(item)
    }
  }

  function scrollItemIntoView(item) {
    if (!panelFlick || !item) return
    Qt.callLater(function() {
      if (!item) return
      var margin = Style.space(6)
      var point = item.mapToItem(panelFlick.contentItem, 0, 0)
      var top = point.y
      var bottom = top + item.height
      var viewTop = panelFlick.contentY
      var viewBottom = viewTop + panelFlick.height
      var maxY = Math.max(0, panelFlick.contentHeight - panelFlick.height)
      if (top < viewTop + margin) panelFlick.contentY = Math.max(0, top - margin)
      else if (bottom > viewBottom - margin) panelFlick.contentY = Math.min(maxY, bottom + margin - panelFlick.height)
    })
  }

  function scrollCursorIntoView() {
    if (focusSection === "list" && listColumn && listIndex >= 0 && listIndex < listColumn.children.length)
      scrollItemIntoView(listColumn.children[listIndex])
  }

  function setListCursor(index) {
    cursorActive = true
    focusSection = "list"
    listIndex = index
    scrollCursorIntoView()
  }

  function focusSearch() {
    searchFocused = true
    if (searchField) searchField.forceActiveFocus()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onOpenedChanged: if (opened) {
    cursorActive = false
    searchFocused = false
    if (panelFlick) panelFlick.contentY = 0
    vpn.refresh(true)
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }
  onListIndexChanged: scrollCursorIntoView()
  onViewChanged: ensureCursor()
  onListModelChanged: ensureCursor()

  Service {
    id: vpn
    settings: root.settings
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): string { vpn.refresh(true, true); return "ok" }
    function connectCountry(code: string): string { vpn.connectCountry(code); return "ok" }
    function disconnect(): string { vpn.disconnect(); return "ok" }
    function toggleVpn(): string { vpn.toggle(); return "ok" }
    function status(): string {
      return JSON.stringify({
        connected: vpn.connected,
        active: vpn.active,
        country: vpn.country,
        city: vpn.city,
        server: vpn.server,
        loggedIn: vpn.loggedIn,
        backend: "cli",
        error: vpn.lastError
      })
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    labelVisible: false
    hasVisualContent: true
    tooltipText: vpn.active
      ? ((vpn.countryName || vpn.country || "Proton VPN") + (vpn.city ? " · " + vpn.city : ""))
      : (vpn.loggedIn ? "Proton VPN disconnected" : "Sign in to Proton VPN")
    implicitWidth: root.bar && root.bar.vertical ? barSize : Math.max(12, barRow.implicitWidth + scaledHorizontalMargin * 2)

    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) vpn.toggle()
      else if (buttonCode === Qt.MiddleButton) vpn.refresh(true, true)
      else root.toggle()
    }

    Row {
      id: barRow
      anchors.centerIn: parent
      spacing: Style.space(5)

      ProtonVpnIcon {
        iconSize: Style.space(11)
        color: root.barIconColor
        badgeColor: root.urgent
        crossed: !vpn.active && vpn.loggedIn
        warning: !vpn.loggedIn
        anchors.verticalCenter: parent.verticalCenter
      }

      Text {
        visible: root.barLabel !== "" && !(root.bar && root.bar.vertical)
        text: root.barLabel
        color: root.barForeground
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
        anchors.verticalCenter: parent.verticalCenter
      }
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(560))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: root.searchFocused
      onMoveRequested: function(dx, dy) {
        if (!root.cursorActive) { root.cursorActive = true; return }
        root.moveCursor(dx, dy)
      }
      onActivateRequested: if (root.cursorActive) root.activateCursor()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "t" || t === "T") vpn.toggle()
        else if (t === "r" || t === "R") vpn.refresh(true, true)
        else if (t === "b" || t === "B") root.openCountries()
        else if (t === "/") root.focusSearch()
      }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: panelFlick.width
          spacing: Style.space(12)

          Item {
            id: header
            width: parent.width
            implicitHeight: hero.implicitHeight
            readonly property bool ringVisible: root.headerHasCursor
            function focusHero() { root.cursorActive = true; root.focusSection = "header" }

            PanelHero {
              id: hero
              width: parent.width
              title: root.heroTitle
              meta: root.heroMeta
              foreground: root.foreground
              fontFamily: root.fontFamily
              iconOpacity: vpn.active ? 1.0 : 0.5
              iconComponent: Component {
                ProtonVpnIcon {
                  iconSize: Style.font.display
                  color: root.iconColor
                  badgeColor: root.urgent
                  crossed: !vpn.active && vpn.loggedIn
                  warning: !vpn.loggedIn
                }
              }
              trailingControl: Component {
                ToggleSwitch {
                  id: powerSwitch
                  checked: vpn.active
                  busy: vpn.busy
                  hasCursor: header.ringVisible
                  foreground: hero.foreground
                  onHovered: function(on) { if (on) header.focusHero() }
                  onToggled: vpn.toggle()

                  PanelToolTip {
                    visible: powerSwitch.containsMouse
                    text: root.toggleHint
                    fontFamily: hero.fontFamily
                  }
                }
              }
            }
          }

          Text {
            textFormat: Text.PlainText
            visible: vpn.actionStatus !== "" || vpn.lastError !== ""
            width: parent.width
            text: vpn.actionStatus !== "" ? vpn.actionStatus : vpn.lastError
            color: vpn.lastError !== "" && vpn.actionStatus === "" ? root.urgent : root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          CursorSurface {
            visible: !vpn.loggedIn
            width: parent.width
            implicitHeight: loginText.implicitHeight + Style.spacing.rowPaddingX
            foreground: root.foreground
            hasCursor: root.cursorActive && root.focusSection === "login"
            fill: root.hoverFill

            MouseArea {
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onEntered: { root.cursorActive = true; root.focusSection = "login" }
              onClicked: vpn.signIn()
            }

            Text {
              id: loginText
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.margins: Style.space(12)
              text: "Sign in with Proton CLI"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.WordWrap
            }
          }

          PanelSeparator { foreground: root.foreground }

          TextField {
            id: searchField
            width: parent.width
            foreground: root.foreground
            placeholderText: root.view === "cities" ? "Search cities" : "Search countries"
            text: root.query
            onActiveFocusChanged: root.searchFocused = activeFocus
            onTextChanged: {
              root.query = text
              root.listIndex = 0
            }
            onAccepted: {
              root.searchFocused = false
              keyCatcher.forceActiveFocus()
              root.activateCursor()
            }
            Keys.onPressed: function(event) {
              if (event.key === Qt.Key_Down || event.text === "j") {
                root.cursorActive = true
                root.focusSection = root.listModel.length > 0 ? "list" : "fastest"
                root.listIndex = 0
                root.searchFocused = false
                keyCatcher.forceActiveFocus()
                event.accepted = true
                return
              }
              if (event.key === Qt.Key_Escape) {
                root.searchFocused = false
                keyCatcher.forceActiveFocus()
                event.accepted = true
              }
            }
          }

          CursorSurface {
            id: fastestRow
            width: parent.width
            implicitHeight: fastestInner.implicitHeight + Style.spacing.xl
            foreground: root.foreground
            hasCursor: root.cursorActive && root.focusSection === "fastest"
            fill: root.hoverFill
            currentFill: root.selectedFill

            MouseArea {
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onEntered: { root.cursorActive = true; root.focusSection = "fastest" }
              onClicked: root.chooseFastest()
            }

            Row {
              id: fastestInner
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.leftMargin: Style.space(6)
              anchors.rightMargin: Style.space(6)
              spacing: Style.space(8)

              Text {
                text: "󰓅"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                width: Style.space(22)
                horizontalAlignment: Text.AlignHCenter
                anchors.verticalCenter: parent.verticalCenter
              }

              Text {
                text: "Fastest"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                anchors.verticalCenter: parent.verticalCenter
              }
            }
          }

          Column {
            visible: root.recentCodes.length > 0 && root.view === "countries" && String(root.query || "").trim() === ""
            width: parent.width
            spacing: Style.space(6)

            PanelSectionHeader {
              text: "RECENT"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Repeater {
              model: root.recentCodes
              RecentRow {
                required property var modelData
                width: parent.width
                code: String(modelData || "")
              }
            }
          }

          PanelSeparator { foreground: root.foreground }

          Column {
            width: parent.width
            spacing: Style.space(10)

            Row {
              width: parent.width
              spacing: Style.space(8)

              PanelActionButton {
                visible: root.view === "cities"
                iconText: "󰁍"
                tooltipText: "Back"
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.openCountries()
              }

              PanelSectionHeader {
                text: root.view === "cities"
                  ? String((root.selectedCountry && root.selectedCountry.name) || "CITIES").toUpperCase()
                  : "COUNTRIES"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }
            }

            Text {
              visible: root.listModel.length === 0
              width: parent.width
              text: root.view === "cities" ? "No cities found." : "No countries found."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              horizontalAlignment: Text.AlignHCenter
            }

            Column {
              id: listColumn
              width: parent.width
              spacing: Style.space(6)

              Repeater {
                model: root.listModel
                LocationRow {
                  required property var modelData
                  required property int index
                  width: listColumn.width
                  item: modelData
                  rowIndex: index
                  cityMode: root.view === "cities"
                }
              }
            }
          }
        }
      }
    }
  }

  Timer {
    id: phraseTimer
    interval: 2800
    running: root.opened && vpn.active
    repeat: true
    onTriggered: phraseSwap.restart()
  }

  SequentialAnimation {
    id: phraseSwap
    PropertyAnimation {
      target: hero; property: "metaOpacity"
      to: 0.0; duration: 180; easing.type: Easing.OutQuad
    }
    ScriptAction {
      script: root.phraseIndex = (root.phraseIndex + 1) % root.activePhrases.length
    }
    PropertyAnimation {
      target: hero; property: "metaOpacity"
      to: 1.0; duration: 260; easing.type: Easing.InQuad
    }
  }

  component RecentRow: CursorSurface {
    id: recentRow
    property string code: ""
    readonly property var country: Model.findCountry(vpn.countries, code)
    readonly property string label: country ? String(country.name || code) : code
    readonly property bool isCurrent: vpn.country === String(code || "").toUpperCase()

    foreground: root.foreground
    current: isCurrent
    fill: root.hoverFill
    currentFill: root.selectedFill
    implicitHeight: recentInner.implicitHeight + Style.spacing.xl

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: {
        root.persistRecent(recentRow.code)
        vpn.connectCountry(recentRow.code)
      }
    }

    Row {
      id: recentInner
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(6)
      anchors.rightMargin: Style.space(6)
      spacing: Style.space(8)

      Text {
        text: Model.flagEmoji(recentRow.code) || recentRow.code
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        width: Style.space(22)
        horizontalAlignment: Text.AlignHCenter
        anchors.verticalCenter: parent.verticalCenter
      }

      Text {
        text: recentRow.label
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: recentRow.current
        elide: Text.ElideRight
        width: parent.width - Style.space(22) - Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
      }
    }
  }

  component LocationRow: CursorSurface {
    id: locationRow
    property var item: null
    property int rowIndex: 0
    property bool cityMode: false
    readonly property string title: cityMode ? String((item && item.name) || "Unknown") : String((item && item.name) || "Unknown")
    readonly property string subtitle: cityMode
      ? (item && item.servers ? item.servers + " servers" : "")
      : ((item && item.code ? item.code : "") + (item && item.servers ? " · " + item.servers + " servers" : ""))
    readonly property bool isCurrent: (!cityMode && item && vpn.country === String(item.code || "").toUpperCase())
      || (cityMode && vpn.city !== "" && item && String(item.name || "") === vpn.city)

    hasCursor: root.cursorActive && root.focusSection === "list" && root.listIndex === rowIndex
    current: isCurrent
    foreground: root.foreground
    fill: root.hoverFill
    currentFill: root.selectedFill
    implicitHeight: locationInner.implicitHeight + Style.spacing.xl

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onEntered: root.setListCursor(locationRow.rowIndex)
      onClicked: {
        if (locationRow.cityMode) root.chooseCity(locationRow.item)
        else root.chooseCountry(locationRow.item)
      }
    }

    RowLayout {
      id: locationInner
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(6)
      anchors.rightMargin: Style.space(6)
      spacing: Style.space(8)

      Text {
        text: locationRow.cityMode ? "󰌉" : (Model.flagEmoji(item && item.code) || String((item && item.code) || ""))
        color: locationRow.current ? root.foreground : root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        Layout.preferredWidth: Style.space(22)
        horizontalAlignment: Text.AlignHCenter
        Layout.alignment: Qt.AlignVCenter
      }

      ColumnLayout {
        Layout.fillWidth: true
        spacing: Style.space(1)

        Text {
          Layout.fillWidth: true
          text: locationRow.title
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          font.bold: locationRow.current
          elide: Text.ElideRight
        }

        Text {
          Layout.fillWidth: true
          visible: locationRow.subtitle !== ""
          text: locationRow.subtitle
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }
      }
    }
  }
}
