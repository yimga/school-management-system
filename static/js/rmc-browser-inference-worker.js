"use strict";

var activeConfig = null;
var modelReady = false;

function sameOriginPath(value) {
  return typeof value === "string" && value.charAt(0) === "/" && value.slice(0, 2) !== "//" && value.indexOf("\\") === -1;
}

function hex(buffer) {
  return Array.from(new Uint8Array(buffer)).map(function (byte) {
    return byte.toString(16).padStart(2, "0");
  }).join("");
}

async function verifyAsset(asset) {
  if (!sameOriginPath(asset.url) || !/^[0-9a-f]{64}$/.test(asset.sha256)) {
    throw new Error("Invalid model asset contract.");
  }
  var response = await fetch(asset.url, { credentials: "same-origin", cache: "force-cache" });
  if (!response.ok) throw new Error("Model asset is unavailable.");
  var bytes = await response.arrayBuffer();
  if (bytes.byteLength !== asset.size_bytes) throw new Error("Model asset size mismatch.");
  var digest = hex(await crypto.subtle.digest("SHA-256", bytes));
  if (digest !== asset.sha256) throw new Error("Model asset checksum mismatch.");
}

async function initialize(config) {
  if (!config || !config.available || !config.runtime || !sameOriginPath(config.runtime.url)) {
    throw new Error("Browser model pack is unavailable.");
  }
  await verifyAsset(config.runtime);
  for (var i = 0; i < config.model.assets.length; i += 1) {
    await verifyAsset(config.model.assets[i]);
  }
  importScripts(config.runtime.url);
  if (!self.RMCBrowserModel || typeof self.RMCBrowserModel.load !== "function" || typeof self.RMCBrowserModel.generate !== "function") {
    throw new Error("Browser runtime does not implement the RMCBrowserModel contract.");
  }
  await self.RMCBrowserModel.load(config.model);
  activeConfig = config;
  modelReady = true;
}

async function purge() {
  modelReady = false;
  activeConfig = null;
  if (self.RMCBrowserModel && typeof self.RMCBrowserModel.dispose === "function") {
    await self.RMCBrowserModel.dispose();
  }
  var keys = await caches.keys();
  await Promise.all(keys.filter(function (key) {
    return key.indexOf("rmc-browser-ai") === 0;
  }).map(function (key) { return caches.delete(key); }));
}

self.onmessage = async function (event) {
  var message = event.data || {};
  try {
    if (message.type === "init") {
      await initialize(message.config);
      self.postMessage({ type: "ready" });
      return;
    }
    if (message.type === "generate") {
      if (!modelReady) throw new Error("Browser model is not initialized.");
      var prompt = String(message.prompt || "").slice(0, activeConfig.limits.max_input_chars);
      var text = await self.RMCBrowserModel.generate(prompt, {
        max_new_tokens: activeConfig.limits.max_new_tokens
      });
      self.postMessage({ type: "result", requestId: message.requestId, text: String(text || "") });
      return;
    }
    if (message.type === "purge") {
      await purge();
      self.postMessage({ type: "purged" });
    }
  } catch (error) {
    self.postMessage({ type: "error", requestId: message.requestId, error: String(error && error.message || error) });
  }
};
