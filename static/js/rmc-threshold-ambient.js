/**
 * Threshold ambient sound — optional per-role atmosphere (Web Audio API).
 * Respects prefers-reduced-motion, requires user gesture to unlock AudioContext.
 */
(function (global) {
  "use strict";

  var STORAGE_KEY = "rmc_threshold_ambient";
  var reduced = global.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function ThresholdAmbient() {
    this.ctx = null;
    this.master = null;
    this.roleGain = null;
    this.loopId = null;
    this.role = "admin";
    this.enabled = false;
    this._nodes = [];
  }

  ThresholdAmbient.prototype._ensureContext = function () {
    if (this.ctx) return true;
    var Ctx = global.AudioContext || global.webkitAudioContext;
    if (!Ctx || reduced) return false;
    this.ctx = new Ctx();
    this.master = this.ctx.createGain();
    this.master.gain.value = 0.22;
    this.master.connect(this.ctx.destination);
    this.roleGain = this.ctx.createGain();
    this.roleGain.gain.value = 0;
    this.roleGain.connect(this.master);
    return true;
  };

  ThresholdAmbient.prototype._stopNodes = function () {
    this._nodes.forEach(function (n) {
      try {
        if (n.stop) n.stop(0);
        n.disconnect();
      } catch (e) { /* noop */ }
    });
    this._nodes = [];
    if (this.loopId) {
      clearInterval(this.loopId);
      this.loopId = null;
    }
  };

  ThresholdAmbient.prototype._osc = function (freq, type, gain, dest) {
    var o = this.ctx.createOscillator();
    var g = this.ctx.createGain();
    o.type = type || "sine";
    o.frequency.value = freq;
    g.gain.value = gain;
    o.connect(g);
    g.connect(dest || this.roleGain);
    o.start();
    this._nodes.push(o, g);
    return { o: o, g: g };
  };

  ThresholdAmbient.prototype._noise = function (gain, dest) {
    var bufferSize = 2 * this.ctx.sampleRate;
    var buffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
    var data = buffer.getChannelData(0);
    for (var i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1;
    var src = this.ctx.createBufferSource();
    src.buffer = buffer;
    src.loop = true;
    var filter = this.ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 400;
    var g = this.ctx.createGain();
    g.gain.value = gain;
    src.connect(filter);
    filter.connect(g);
    g.connect(dest || this.roleGain);
    src.start();
    this._nodes.push(src, filter, g);
    return g;
  };

  ThresholdAmbient.prototype._buildRole = function (role) {
    this._stopNodes();
    if (!this.ctx || !this.enabled) return;

    var t = this.ctx.currentTime;
    this.roleGain.gain.cancelScheduledValues(t);
    this.roleGain.gain.setValueAtTime(0, t);
    this.roleGain.gain.linearRampToValueAtTime(1, t + 1.2);

    if (role === "admin") {
      this._osc(55, "sine", 0.08);
      this._osc(110, "triangle", 0.03);
      this._noise(0.015);
    } else if (role === "teacher") {
      this._osc(196, "sine", 0.04);
      this._noise(0.008);
      var self = this;
      this.loopId = setInterval(function () {
        if (!self.enabled || self.role !== "teacher" || !self.ctx) return;
        var o = self.ctx.createOscillator();
        var g = self.ctx.createGain();
        o.frequency.value = 880;
        g.gain.value = 0.02;
        o.connect(g);
        g.connect(self.roleGain);
        o.start();
        g.gain.exponentialRampToValueAtTime(0.001, self.ctx.currentTime + 0.4);
        o.stop(self.ctx.currentTime + 0.45);
      }, 8000);
    } else if (role === "parent") {
      this._noise(0.012);
      this._osc(73, "sine", 0.05);
    } else if (role === "student") {
      this._osc(329, "sine", 0.025);
      this._osc(392, "triangle", 0.015);
    } else if (role === "staff") {
      this._osc(90, "square", 0.012);
      this._noise(0.006);
    } else if (role === "board") {
      this._osc(65, "sine", 0.06);
    }
  };

  ThresholdAmbient.prototype.setRole = function (role) {
    this.role = role || "admin";
    if (this.enabled) this._buildRole(this.role);
  };

  ThresholdAmbient.prototype.toggle = function () {
    if (reduced) return false;
    if (!this._ensureContext()) return false;
    if (this.ctx.state === "suspended") {
      this.ctx.resume();
    }
    this.enabled = !this.enabled;
    try {
      global.localStorage.setItem(STORAGE_KEY, this.enabled ? "1" : "0");
    } catch (e) { /* noop */ }
    if (this.enabled) {
      this._buildRole(this.role);
    } else {
      this._stopNodes();
      var t = this.ctx.currentTime;
      this.roleGain.gain.cancelScheduledValues(t);
      this.roleGain.gain.linearRampToValueAtTime(0, t + 0.4);
    }
    return this.enabled;
  };

  ThresholdAmbient.prototype.initFromStorage = function () {
    try {
      if (global.localStorage.getItem(STORAGE_KEY) === "1") {
        this.enabled = true;
      }
    } catch (e) { /* noop */ }
  };

  ThresholdAmbient.prototype.unlock = function () {
    if (!this._ensureContext()) return;
    if (this.ctx.state === "suspended") {
      this.ctx.resume();
    }
    if (this.enabled) this._buildRole(this.role);
  };

  global.RmcThresholdAmbient = ThresholdAmbient;
})(typeof window !== "undefined" ? window : globalThis);
