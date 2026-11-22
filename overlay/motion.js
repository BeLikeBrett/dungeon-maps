.pragma library

// Presentation only: never fed back into localization, calibration or sharing.
// Predict at most one capture interval, 50 ms and six map pixels. New readings
// always win immediately; standing still, stale input and corrections stop it.
function Track() {
    this.reset = function() {
        this.last = null;
        this.vu = this.vv = this.horizon = 0;
    };
    this.reset();
    this.feed = function(who, now, width, height, key) {
        var old = this.last;
        this.vu = this.vv = this.horizon = 0;
        if (old && old.key === key && who.fresh !== false) {
            var dt = now - old.at;
            var du = who.u - old.u, dv = who.v - old.v;
            var pixels = Math.hypot(du * width, dv * height);
            if (dt >= 8 && dt <= 150 && pixels >= 0.15 && pixels <= 12) {
                this.horizon = Math.min(dt, 50);
                var limit = Math.min(1, 6 / Math.max(0.001, pixels * this.horizon / dt));
                this.vu = du / dt * limit;
                this.vv = dv / dt * limit;
            }
        }
        this.last = {u: who.u, v: who.v, at: now, key: key};
    };
    this.at = function(now) {
        var age = Math.max(0, now - this.last.at);
        var t = Math.min(age, this.horizon);
        return {u: this.last.u + this.vu * t, v: this.last.v + this.vv * t,
                active: this.horizon > 0 && age < this.horizon};
    };
}
