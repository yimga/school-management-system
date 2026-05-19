/**
 * MV3 background service-worker stub.
 *
 * Manifest V3 service-workers are event-driven and must NOT hold state
 * in module-scope globals (Chrome unloads idle workers after 30s). This
 * stub installs minimal lifecycle listeners so the worker registers
 * cleanly when the extension is loaded; per-vendor extraction routing
 * (delegated to src/content/ + src/vendors/) is intentionally NOT
 * wired here.
 *
 * Honest deferral: routed message handling lands in a future wave;
 * see docs/COMPANION_SIBLINGS.md for the architectural boundary.
 */

chrome.runtime.onInstalled.addListener((details) => {
  // The popup is the operator's primary entry point; we just log the
  // install reason so the operator can audit it via `chrome://serviceworker-internals/`.
  // eslint-disable-next-line no-console
  console.warn(
    `[rmc-companion] installed reason=${details.reason} version=${chrome.runtime.getManifest().version}`
  );
});

chrome.runtime.onStartup.addListener(() => {
  // eslint-disable-next-line no-console
  console.warn("[rmc-companion] service worker startup");
});

export {};
