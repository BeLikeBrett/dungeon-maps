// Run the exact QML presentation helper without a game or live caches.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const context = {};
vm.runInNewContext(fs.readFileSync(__dirname + '/../overlay/motion.js', 'utf8')
    .replace('.pragma library', ''), context);
const track = new context.Track();
const feed = (u, t, key = 'floor1', fresh = true) =>
    track.feed({u, v: .5, fresh}, t, 1000, 668, key);
feed(.5, 0);
assert.equal(track.at(0).u, .5);
feed(.502, 20);
assert.equal(track.at(30).u, .503);
assert.equal(track.at(200).u, .504); // only one interval, never endless walking
assert(!track.at(200).active);
feed(.502, 220); // stopped: the newest position wins, no easing trail
assert.equal(track.at(230).u, .502);
assert(!track.at(230).active);
feed(.8, 240); // correction: never glide across the map
assert.equal(track.at(250).u, .8);
feed(.801, 260, 'floor2');
assert.equal(track.at(270).u, .801);
feed(.802, 280, 'floor2', false);
assert.equal(track.at(290).u, .802);
feed(.803, 260, 'floor2'); // backwards wall clock
assert.equal(track.at(270).u, .803);
feed(.813, 270, 'floor2'); // fast reading, capped at six map pixels
assert(Math.abs(track.at(1000).u - .813) <= .006000001);
feed(.9, 1000, 'floor2'); // long capture gap resets velocity
assert.equal(track.at(1010).u, .9);
console.log('PASS bounded display prediction, stops, corrections, floors, stale input and clock jumps');
