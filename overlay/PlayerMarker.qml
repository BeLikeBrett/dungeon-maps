import QtQuick
import QtQuick.Shapes
import "motion.js" as Motion

Item {
    id: marker
    required property var who
    required property real mapW
    required property real mapH
    property string mapKey: ""
    property color fill: "#ffd24d"
    readonly property bool hasHeading: who && who.heading !== null && who.heading !== undefined
    readonly property real s: Math.max(20, 26 * mapW / 1002) * ((who && who.size) || 1)
    property var motion: new Motion.Track()
    property real drawnU: who ? who.u : 0
    property real drawnV: who ? who.v : 0
    property bool predicting: false

    function advance() {
        if (!motion.last) return;
        const p = motion.at(Date.now());
        drawnU = p.u;
        drawnV = p.v;
        predicting = p.active;
    }
    function accept() {
        if (!who) return;
        motion.feed(who, Date.now(), mapW, mapH, mapKey);
        advance();
    }
    onWhoChanged: accept()
    onMapKeyChanged: { motion.reset(); accept(); }
    Component.onCompleted: accept()
    FrameAnimation {
        running: marker.visible && marker.predicting
        onTriggered: marker.advance()
    }

    width: s
    height: s
    x: drawnU * mapW - width / 2
    y: drawnV * mapH - height / 2
    opacity: who && who.fresh === false ? 0.55 : 1
    // Geometry stays cached while translation/heading use scene-graph transforms.
    // No raster Canvas, blur effect, or rotation animation.
    Shape {
        objectName: "arrowGlyph"
        anchors.fill: parent
        visible: marker.hasHeading
        rotation: (marker.who && marker.who.heading) || 0
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "#000000"
            fillColor: marker.fill
            strokeWidth: Math.max(2, marker.s * 0.1)
            joinStyle: ShapePath.RoundJoin
            startX: marker.s * 0.5
            startY: marker.s * 0.04
            PathLine { x: marker.s * 0.88; y: marker.s * 0.94 }
            PathLine { x: marker.s * 0.5; y: marker.s * 0.72 }
            PathLine { x: marker.s * 0.12; y: marker.s * 0.94 }
            PathLine { x: marker.s * 0.5; y: marker.s * 0.04 }
        }
    }
    Rectangle {
        anchors.centerIn: parent
        visible: !marker.hasHeading
        width: parent.width * 0.7
        height: width
        radius: width / 2
        color: marker.fill
        border.color: "#000000"
        border.width: 2
    }
    Text {
        visible: marker.who && marker.who.guess === true
        anchors.left: parent.right
        anchors.leftMargin: 2
        anchors.verticalCenter: parent.verticalCenter
        text: "?"
        color: marker.fill
        font.pixelSize: Math.max(12, 13 * marker.mapW / 1002)
        font.bold: true
        style: Text.Outline
        styleColor: "#000000"
    }
}
