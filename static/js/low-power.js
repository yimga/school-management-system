/**
 * Low-power / Save Data detection for Resilient Edge.
 * When reduceActivityLowPower is enabled and the device is in a low-power state,
 * sets data-low-power="true" on <html> so CSS can reduce animations and non-essential motion.
 */
(function (global) {
  'use strict';

  var ATTR = 'data-low-power';

  function getConfig() {
    return global.SMS_OFFLINE_CONFIG || {};
  }

  function setLowPower(active) {
    var root = global.document && global.document.documentElement;
    if (!root) return;
    if (active) {
      root.setAttribute(ATTR, 'true');
    } else {
      root.removeAttribute(ATTR);
    }
  }

  function update() {
    var cfg = getConfig();
    if (!cfg.reduceActivityLowPower) {
      setLowPower(false);
      return;
    }
    if (global.navigator && global.navigator.connection && global.navigator.connection.saveData === true) {
      setLowPower(true);
      return;
    }
    if (!global.navigator.getBattery) {
      setLowPower(false);
      return;
    }
    global.navigator.getBattery().then(function (bat) {
      if (!bat) { setLowPower(false); return; }
      setLowPower(bat.level < 0.2 && !bat.charging);
    }).catch(function () { setLowPower(false); });
  }

  function init() {
    if (!global.document || !global.document.documentElement) return;
    update();
    if (global.navigator && global.navigator.getBattery) {
      global.navigator.getBattery().then(function (bat) {
        if (bat) {
          bat.addEventListener('levelchange', update);
          bat.addEventListener('chargingchange', update);
        }
      }).catch(function () {});
    }
  }

  if (global.document && global.document.readyState === 'loading') {
    global.document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : this);
