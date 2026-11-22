import QtQuick
import QtTest
import "../../overlay" as Overlay

Item {
    id: scene
    width: 1100
    height: 760
    Rectangle { anchors.fill: parent; color: "#483727" }
    Item {
        id: mapCanvas
        x: 30; y: 35; width: 1002; height: 668
        Overlay.PlayerMarker {
            id: marker
            who: ({u: .5, v: .5, heading: 37, fresh: true, guess: false, size: 2.5})
            mapW: mapCanvas.width
            mapH: mapCanvas.height
            mapKey: "1:1"
        }
    }
    TestCase {
        name: "PlayerMarker"
        when: windowShown
        function init() {
            marker.motion.reset();
            marker.who = {u: .5, v: .5, heading: 37, fresh: true, guess: false, size: 2.5};
            mapCanvas.x = 30;
        }
        function test_drag_and_resize() {
            const before = marker.mapToItem(scene, 0, 0);
            mapCanvas.x += 125;
            compare(marker.mapToItem(scene, 0, 0).x - before.x, 125);
            compare(marker.drawnU, .5);
            compare(marker.x + marker.width / 2, mapCanvas.width * .5);
        }
        function test_correction_and_heading_are_immediate() {
            marker.who = {u: .8, v: .2, heading: 270, fresh: true, guess: false, size: 2.5};
            compare(marker.drawnU, .8);
            compare(marker.drawnV, .2);
            compare(findChild(marker, "arrowGlyph").rotation, 270);
            verify(!marker.predicting);
        }
        function test_stale_remains_readable() {
            marker.who = {u: .5, v: .5, heading: null, fresh: false, guess: true};
            compare(marker.opacity, .55);
            verify(!marker.hasHeading);
            verify(!marker.predicting);
        }
        function test_vector_preview() {
            let saved = false;
            verify(marker.grabToImage(function(result) {
                saved = result.saveToFile("/tmp/dungeonmaps-vector-arrow.png");
            }));
            tryVerify(function() { return saved; }, 2000);
        }
    }
}
