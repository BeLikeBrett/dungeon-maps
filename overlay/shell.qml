// Dungeon Maps live tracker, Linux overlay: runs the tracker (python3 -m dungeonmaps) and draws your
// arrow (with your facing; size from the addon's settings) and your group's dots (class colours, like
// the addon's own group dots) on top of the Dungeon Maps addon's dungeon map. A fixed transparent surface
// positions markers inside the map canvas, lets every click through,
// and is only visible while the map is open.
//
//   qs -p <repo>/overlay

import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
    id: root

    // last line from the tracker:
    // { show, screen, cx, cy, cw, ch, me: { u, v, heading, fresh, guess, size } | null,
    //   friends: [ { name, u, v, color, fresh, guess, label, size } ] }
    property var st: ({ show: false })
    property bool screenshotRecovery: false

    Process {
        id: tracker
        command: ["python3", "-B", "-m", "dungeonmaps"].concat(root.screenshotRecovery ? ["--screenshots"] : [])
        workingDirectory: Quickshell.shellDir + "/.."
        running: true
        stdout: SplitParser {
            onRead: line => {
                try { root.st = JSON.parse(line) } catch (e) { }
            }
        }
        stderr: SplitParser { onRead: line => console.log("tracker:", line) }
        onExited: function (exitCode, exitStatus) {
            root.st = { show: false }
            // Another capture owner may be finishing an earlier launch. Retry without
            // opening another picker; Python's lock still prevents duplicate capture.
            if (exitCode === 73) console.log("tracker: capture busy; waiting for the current owner")
            root.screenshotRecovery = true // recovery must never reopen the permission picker
            restart.start()
        }
    }
    Timer { id: restart; interval: 3000; onTriggered: tracker.running = true }

    // a friend: a dot in their class colour (black ring, light rim, like a raid blip) with their name
    // in a small dark tag above or below it, on the side away from your arrow (core.py lays this out)
    component FriendDot: Item {
        id: fd
        required property var who
        required property real mapW
        required property real mapH
        readonly property real d: Math.max(10, 13 * mapW / 1002) * (who.size || 1)
        readonly property color c: who.color || "#cccccc"
        width: d
        height: d
        x: who.u * mapW - width / 2
        y: who.v * mapH - height / 2
        opacity: who.fresh === false || who.guess === true ? 0.55 : 1
        Rectangle {
            anchors.centerIn: parent
            width: fd.d + 6
            height: width
            radius: width / 2
            color: "#e8ffffff"
            Rectangle {
                anchors.centerIn: parent
                width: fd.d + 3
                height: width
                radius: width / 2
                color: "#000000"
                Rectangle {
                    anchors.centerIn: parent
                    width: fd.d
                    height: width
                    radius: width / 2
                    color: fd.c
                }
            }
        }
        Rectangle {
            id: tag
            anchors.horizontalCenter: parent.horizontalCenter
            y: fd.who.label === "below" ? fd.d + 5 : -height - 5
            width: name.implicitWidth + 10
            height: name.implicitHeight + 2
            radius: height / 2
            color: "#b3101010"
            border.color: "#40000000"
            Text {
                id: name
                anchors.centerIn: parent
                text: fd.who.name + (fd.who.guess === true ? "?" : "")
                color: fd.c
                font.pixelSize: Math.max(11, 12 * fd.mapW / 1002) * Math.max(0.85, Math.min(1.6, fd.who.size || 1))
                font.bold: true
            }
        }
    }

    Variants {
        model: Quickshell.screens

        PanelWindow {
            id: win
            required property var modelData
            screen: modelData
            visible: root.st.show === true && root.st.screen === modelData.name

            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.namespace: "dungeon-maps"
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
            exclusionMode: ExclusionMode.Ignore
            color: "transparent"
            mask: Region { }   // every click goes to the game

            // Keep the compositor surface fixed. Moving the map only changes a
            // scene-graph translation; no layer-shell configure/reposition cycle.
            anchors { top: true; left: true; right: true; bottom: true }

            Item {
                id: mapCanvas
                x: root.st.cx || 0
                y: root.st.cy || 0
                width: root.st.cw || 1
                height: root.st.ch || 1
                clip: true

                // friends first, so your arrow is drawn on top
                Repeater {
                    model: root.st.friends || []
                    FriendDot {
                        required property var modelData
                        who: modelData
                        mapW: mapCanvas.width
                        mapH: mapCanvas.height
                    }
                }
                Loader {
                    active: !!root.st.me
                    sourceComponent: PlayerMarker {
                        mapKey: root.st.mapKey || ""
                        who: root.st.me
                        mapW: mapCanvas.width
                        mapH: mapCanvas.height
                    }
                }
            }
        }
    }
}
