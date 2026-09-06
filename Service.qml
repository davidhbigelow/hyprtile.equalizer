import QtQuick
import Quickshell

Item {
  id: root

  // Injected by the shell service loader when present.
  property var omarchyPath
  property var shell
  property var manifest
  property var pluginRegistry

  readonly property string scriptsDir: String(Qt.resolvedUrl("scripts")).replace(/^file:\/\//, "")
  readonly property string python: "/usr/bin/python3"
  readonly property string bindingScript: scriptsDir + "/equalize-binding"
  readonly property string watcherScript: scriptsDir + "/equalize-watch"

  function maintain() {
    Quickshell.execDetached([root.python, root.bindingScript, "ensure"])
    Quickshell.execDetached([root.python, root.watcherScript])
  }

  function teardown() {
    Quickshell.execDetached([root.python, root.bindingScript, "remove"])
    Quickshell.execDetached([root.python, root.watcherScript, "--stop"])
  }

  Timer {
    id: maintainTimer
    interval: 5 * 60 * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.maintain()
  }

  Component.onDestruction: root.teardown()
}