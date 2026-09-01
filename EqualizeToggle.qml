import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Toolbar toggle for live window-equalize mode ("SUPER + E" grid).
// ON: the watcher keeps the active workspace in an equalized floating grid
//     (auto-float new windows, follow active desktop, re-fit on drag/resize).
// OFF (default): stock Hyprland behavior; SUPER+E is a one-shot manual equalize.
BarWidget {
  id: root
  moduleName: "hyprtile.equalize"

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  property bool liveOn: false
  property bool refreshPending: false

  // Resolve this plugin's bundled scripts (scripts/) so the widget is fully
  // self-contained: it never depends on ~/.local/bin being on PATH or on any
  // absolute install path.
  readonly property string scriptsDir: {
    var url = Qt.resolvedUrl("scripts")
    return String(url).replace(/^file:\/\//, "")
  }

  // A query already in flight was asked for before the last one landed, so it
  // may read the state the toggle just replaced. Remember the request and
  // re-run once it finishes rather than dropping it, or the icon would never
  // catch up to the actual mode.
  function refresh() {
    if (stateProc.running) {
      refreshPending = true
      return
    }
    refreshPending = false
    stateProc.running = true
  }

  function toggle() {
    if (root.bar) root.bar.run(root.scriptsDir + "/equalize-toggle")
    root.refreshPending = true
    recheckTimer.restart()
  }

  Process {
    id: stateProc
    command: [root.scriptsDir + "/equalize-state"]
    onRunningChanged: {
      if (!running && root.refreshPending) root.refresh()
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.liveOn = text.trim() === "1"
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

  // Re-read shortly after a toggle so the icon flips promptly.
  Timer {
    id: recheckTimer
    interval: 300
    onTriggered: root.refresh()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    // The icon shows the DESTINATION layout (what a click toggles into):
    // equalize ON  -> view_dashboard ("back to default Hyprland tiling");
    // default OFF  -> view_grid     ("into the equalizer grid").
    text: root.liveOn ? "󰕮" : "󰀻"
    active: root.liveOn
    // Match the other toolbar icons' color: in transparent-bar mode the normal
    // foreground is auto-contrasted against the wallpaper, while the "active"
    // accent color is a fixed theme color that can blend in. The destination-
    // layout glyphs (apps grid vs view_module) already convey the state, so
    // keep the auto-contrast color for both states.
    useActiveColor: false
    tooltipText: root.liveOn
      ? "Live equalize ON — click to return to default tiling"
      : "Live equalize OFF — click to enable the SUPER+E grid"
    onPressed: root.toggle()
  }
}
