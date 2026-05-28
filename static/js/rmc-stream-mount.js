// RunMyCampus streaming UI mount (v4.00.0).
//
// Incremental JSON parser. Reads chunks streamed from the LiteLLM gateway via
// WS (group ai.session.<id>) or fetch(POST, ReadableStream). On the first
// occurrence of `{"component": "<X>"`, mounts the .rmc-<X> shell skeleton
// in <100ms so the user sees structure before the model finishes generating.
// Trailing data hydrates into the already-mounted shell nodes.
//
// Anti-pattern killed: awaiting a full payload before any DOM is touched.
//
// API surface (window.rmcStreamMount):
//   .attachWS(url, { onComponent, onComplete })       -> close()
//   .attachFetch(response, { onComponent, onComplete }) -> Promise<void>

(function () {
  "use strict";
  if (window.rmcStreamMount) return;

  function shellFor(componentName) {
    if (!componentName) return null;
    const safe = String(componentName).replace(/[^a-z0-9_-]/gi, "");
    const root = document.querySelector(`[data-rmc-stream-target="${safe}"]`)
              || document.querySelector(`.rmc-${safe}`);
    if (!root) return null;
    root.classList.add("rmc-stream-mounting");
    return root;
  }

  // Token-level scanner: looks for `"component"` followed by `"<value>"`.
  function scanForComponentMarker(buffer) {
    const idx = buffer.indexOf('"component"');
    if (idx < 0) return null;
    const tail = buffer.slice(idx);
    const m = tail.match(/"component"\s*:\s*"([a-zA-Z0-9_-]+)"/);
    return m ? m[1] : null;
  }

  function makeChunkProcessor({ onComponent, onComplete, onChunkText }) {
    let buffer = "";
    let mountedComponent = null;
    return {
      push(text) {
        buffer += text;
        if (!mountedComponent) {
          const comp = scanForComponentMarker(buffer);
          if (comp) {
            mountedComponent = comp;
            const root = shellFor(comp);
            if (onComponent) {
              try { onComponent(comp, root); } catch (e) {}
            }
          }
        }
        if (onChunkText) {
          try { onChunkText(text, mountedComponent); } catch (e) {}
        }
      },
      finish() {
        if (mountedComponent) {
          const root = shellFor(mountedComponent);
          if (root) root.classList.remove("rmc-stream-mounting");
        }
        if (onComplete) {
          try { onComplete(buffer, mountedComponent); } catch (e) {}
        }
      },
    };
  }

  function attachWS(url, opts = {}) {
    const ws = new WebSocket(url);
    const proc = makeChunkProcessor(opts);
    ws.onmessage = (ev) => {
      let msg = null;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === "ai.stream.chunk" && typeof msg.chunk === "string") {
        proc.push(msg.chunk);
      } else if (msg.type === "ai.stream.done") {
        proc.finish();
      }
    };
    ws.onerror = () => proc.finish();
    ws.onclose = () => proc.finish();
    return () => { try { ws.close(); } catch {} };
  }

  async function attachFetch(response, opts = {}) {
    const proc = makeChunkProcessor(opts);
    if (!response || !response.body) {
      proc.finish();
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let done = false;
    while (!done) {
      const r = await reader.read();
      done = r.done;
      if (r.value) {
        const text = decoder.decode(r.value, { stream: !done });
        if (text) proc.push(text);
      }
    }
    proc.finish();
  }

  window.rmcStreamMount = { attachWS, attachFetch };
})();
