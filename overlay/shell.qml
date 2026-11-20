// Dungeon Maps live tracker, Linux overlay: runs the tracker (python3 -m dungeonmaps) and draws your
// arrow (with your facing; size from the addon's settings) and your group's dots (class colours, like
// the addon's own group dots) on top of the Dungeon Maps addon's dungeon map. The window covers exactly
// the map's canvas (the tracker reads where it is from the addon's beacon), lets every click through,
// and only exists while the map is open.
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
    //   friends: [ { name, u, v, color, fresh, guess } ] }
    property var st: ({ show: false })

    Process {
        id: tracker
        command: ["python3", "-B", "-m", "dungeonmaps"]
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
            restart.start()
        }
    }
    Timer { id: restart; interval: 3000; onTriggered: tracker.running = true }

    // your arrow (gold; its size is the addon's "Your arrow size" setting)
    component Marker: Item {
        id: m
        required property var who
        required property real mapW
        required property real mapH
        property color fill: "#ffd24d"
        property string label: "You"
        readonly property bool hasHeading: who.heading !== null && who.heading !== undefined
        readonly property real s: Math.max(20, 26 * mapW / 1002) * (who.size || 1)
        width: s
        height: s
        x: who.u * mapW - width / 2
        y: who.v * mapH - height / 2
        // dimmed: no minimap for a while, or found by walking only (right-click the map to confirm)
        opacity: who.fresh === false || who.guess === true ? 0.55 : 1

        Item {
            anchors.fill: parent
            visible: m.hasHeading
            rotation: m.who.heading || 0
            Behavior on rotation { RotationAnimation { duration: 25; direction: RotationAnimation.Shortest } }
            Canvas {
                anchors.fill: parent
                property color c: m.fill
                onCChanged: requestPaint()
                onWidthChanged: requestPaint()
                onPaint: {
                    const g = getContext("2d"), w = width, h = height
                    g.reset()
                    g.beginPath()
                    g.moveTo(w * 0.5, h * 0.04)
                    g.lineTo(w * 0.88, h * 0.94)
                    g.lineTo(w * 0.5, h * 0.72)
                    g.lineTo(w * 0.12, h * 0.94)
                    g.closePath()
                    g.lineJoin = "round"
                    g.lineWidth = Math.max(2, w * 0.1)
                    g.strokeStyle = "#000000"
                    g.stroke()
                    g.fillStyle = c
                    g.fill()
                }
            }
        }
        Rectangle {
            anchors.centerIn: parent
            visible: !m.hasHeading
            width: parent.width * 0.7
            height: width
            radius: width / 2
            color: m.fill
            border.color: "#000000"
            border.width: 2
        }
        Text {
            anchors.left: parent.right
            anchors.leftMargin: 3
            anchors.verticalCenter: parent.verticalCenter
            text: m.label + (m.who.guess === true ? "?" : "")
            color: m.fill
            font.pixelSize: Math.max(12, 13 * m.mapW / 1002)
            font.bold: true
            style: Text.Outline
            styleColor: "#000000"
        }
    }

    // a friend: a dot in their class colour with a black ring and their name, as the addon draws
    // group members (14 map pixels across, on the 1002-pixel-wide map)
    component FriendDot: Item {
        id: fd
        required property var who
        required property real mapW
        required property real mapH
        readonly property real d: Math.max(9, 14 * mapW / 1002)
        width: d
        height: d
        x: who.u * mapW - width / 2
        y: who.v * mapH - height / 2
        opacity: who.fresh === false || who.guess === true ? 0.55 : 1
        Rectangle {
            anchors.centerIn: parent
            width: fd.d + 4
            height: width
            radius: width / 2
            color: "#000000"
            Rectangle {
                anchors.centerIn: parent
                width: fd.d
                height: width
                radius: width / 2
                color: fd.who.color || "#cccccc"
            }
        }
        Text {
            anchors.left: parent.right
            anchors.leftMargin: 3
            anchors.verticalCenter: parent.verticalCenter
            text: fd.who.name + (fd.who.guess === true ? "?" : "")
            color: fd.who.color || "#cccccc"
            font.pixelSize: Math.max(11, 13 * fd.mapW / 1002)
            font.bold: true
            style: Text.Outline
            styleColor: "#000000"
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

            anchors { top: true; left: true }
            margins {
                left: Math.round(root.st.cx || 0)
                top: Math.round(root.st.cy || 0)
            }
            implicitWidth: Math.max(1, Math.round(root.st.cw || 1))
            implicitHeight: Math.max(1, Math.round(root.st.ch || 1))

            // friends first, so your arrow is drawn on top
            Repeater {
                model: root.st.friends || []
                FriendDot {
                    required property var modelData
                    who: modelData
                    mapW: win.width
                    mapH: win.height
                }
            }
            Loader {
                active: !!root.st.me
                sourceComponent: Marker {
                    who: root.st.me
                    mapW: win.width
                    mapH: win.height
                }
            }
        }
    }
}
