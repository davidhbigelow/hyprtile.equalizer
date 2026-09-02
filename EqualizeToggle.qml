import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "hyprtile.equalize"
  ipcTarget: "hyprtile.equalize"

  property bool liveOn: false
  property bool fillRemainder: false
  property bool refreshPending: false
  property string focusSection: "header"
  property bool cursorActive: false

  readonly property string scriptsDir: {
    var url = Qt.resolvedUrl("scripts")
    return String(url).replace(/^file:\/\//, "")
  }

  readonly property color panelForeground: bar ? bar.foreground : Color.foreground
  readonly property string panelFontFamily: bar ? (bar.fontFamily || Style.font.family) : Style.font.family

  property int headerSelectedIndex: 0
  readonly property bool headerHasCursor: cursorActive && focusSection === "header"
  readonly property bool optionHasCursor: cursorActive && focusSection === "option"

  function refresh() {
    if (stateProc.running) {
      refreshPending = true
      return
    }
    refreshPending = false
    stateProc.running = true
  }

  function refreshPreferences() {
    if (prefsGetProc.running) return
    prefsGetProc.running = true
  }

  function toggleLive() {
    if (toggleProc.running) return
    toggleProc.running = true
  }

  function ensureMode(targetOn) {
    if (targetOn === root.liveOn) return
    root.toggleLive()
  }

  function toggleFill() {
    if (prefsToggleProc.running) return
    prefsToggleProc.running = true
  }

  function setHeaderCursor() {
    cursorActive = true
    focusSection = "header"
  }

  function headerModeOn() {
    return headerSelectedIndex === 0
  }

  function moveCursor(dx, dy) {
    if (focusSection === "header") {
      if (dx !== 0) {
        headerSelectedIndex = Math.max(0, Math.min(1, headerSelectedIndex + dx))
      } else if (dy > 0) {
        focusSection = "option"
      }
    } else if (focusSection === "option") {
      if (dy < 0) focusSection = "header"
    }
  }

  function activateCursor() {
    if (focusSection === "header") root.ensureMode(root.headerModeOn())
    else if (focusSection === "option") root.toggleFill()
  }

  onOpenedChanged: {
    if (opened) {
      refresh()
      refreshPreferences()
    }
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    id: stateProc
    command: [root.scriptsDir + "/equalize-state"]
    onRunningChanged: if (!running && root.refreshPending) root.refresh()
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.liveOn = text.trim() === "1"
    }
  }

  Process {
    id: toggleProc
    command: [root.scriptsDir + "/equalize-toggle"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.liveOn = text.trim() === "1"
    }
  }

  Process {
    id: prefsGetProc
    command: [root.scriptsDir + "/equalize-settings", "get", "fill-remainder"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.fillRemainder = text.trim() === "1"
    }
  }

  Process {
    id: prefsToggleProc
    command: [root.scriptsDir + "/equalize-settings", "toggle", "fill-remainder"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.fillRemainder = text.trim() === "1"
    }
  }

  Timer {
    id: pollTimer
    interval: 1500
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.liveOn ? "󰕮" : "󰀻"
    active: root.liveOn
    useActiveColor: false
    tooltipText: root.liveOn
      ? "Live equalize ON — click for controls"
      : "Live equalize OFF — click for controls"
    onPressed: function(b) {
      if (b === Qt.RightButton) {
        root.toggleLive()
      } else {
        root.toggle()
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
    contentWidth: panel.fittedContentWidth(Style.space(300))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onMoveRequested: function(dx, dy) {
        if (!root.cursorActive) {
          root.cursorActive = true
          return
        }
        root.moveCursor(dx, dy)
      }
      onActivateRequested: root.activateCursor()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "e" || t === "E") root.toggleLive()
        else if (t === "f" || t === "F") root.toggleFill()
      }

      Column {
        id: column
        width: parent.width
        spacing: Style.space(14)

        Column {
          width: parent.width
          spacing: Style.space(4)

          Text {
            text: "HyprTile Equalizer"
            color: root.panelForeground
            font.family: root.panelFontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            width: parent.width
          }

          Text {
            textFormat: Text.PlainText
            text: root.liveOn ? "GRID MODE ACTIVE" : "DEFAULT TILING"
            color: Qt.darker(root.panelForeground, 1.4)
            font.family: root.panelFontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
            font.letterSpacing: 1.2
            horizontalAlignment: Text.AlignHCenter
            width: parent.width
          }
        }

        Row {
          id: modeRow
          width: parent.width
          spacing: Style.space(10)

          readonly property real cellWidth: (width - spacing * (modeButtons.count - 1)) / modeButtons.count

          Repeater {
            id: modeButtons
            model: [
              { label: "Equalized", icon: "󰀻", targetOn: true },
              { label: "Default", icon: "󰕮", targetOn: false }
            ]
            delegate: Button {
              id: modeButton
              required property var modelData
              required property int index
              readonly property bool targetOn: !!modelData.targetOn
              width: modeRow.cellWidth
              height: Style.space(32)
              iconText: modelData.icon
              iconSize: Style.font.body
              text: modelData.label
              fontSize: Style.font.bodySmall
              bordered: true
              foreground: root.panelForeground
              fontFamily: root.panelFontFamily
              active: targetOn ? root.liveOn : !root.liveOn
              hasCursor: root.headerHasCursor && root.headerSelectedIndex === index
              onClicked: root.ensureMode(targetOn)
              onHovered: function(on) {
                if (on) {
                  root.cursorActive = true
                  root.focusSection = "header"
                  root.headerSelectedIndex = index
                }
              }
            }
          }
        }

        PanelSeparator {
          foreground: root.panelForeground
        }

        Item {
          id: fillRow
          width: parent.width
          height: fillSwitch.implicitHeight

          property bool enabled: root.liveOn

          Text {
            id: fillLabel
            textFormat: Text.PlainText
            text: "Stretch Last Tile to Fill"
            color: fillRow.enabled ? root.panelForeground : Qt.darker(root.panelForeground, 1.4)
            font.family: root.panelFontFamily
            font.pixelSize: Style.font.body
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: fillSwitch.left
            anchors.rightMargin: Style.space(12)
            elide: Text.ElideRight
          }

          ToggleSwitch {
            id: fillSwitch
            checked: root.fillRemainder
            enabled: fillRow.enabled
            interactive: fillRow.enabled
            cursorRing: false
            hasCursor: root.optionHasCursor
            foreground: fillRow.enabled ? root.panelForeground : Qt.darker(root.panelForeground, 1.4)
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            onToggled: root.toggleFill()
          }

          MouseArea {
            id: fillMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            enabled: fillRow.enabled
            onContainsMouseChanged: if (containsMouse && enabled) {
              root.cursorActive = true
              root.focusSection = "option"
            }
            onClicked: if (enabled) root.toggleFill()
          }
        }
      }
    }
  }
}