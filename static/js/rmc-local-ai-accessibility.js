(function () {
  "use strict";

  function chromeConfig() {
    var node = document.getElementById("page-data-rmc-ai-chrome");
    try { return node ? JSON.parse(node.textContent || "{}") : {}; } catch (_error) { return {}; }
  }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    var match = document.cookie.match(/(?:^|;\s*)(?:csrftoken|rmc_manager_csrftoken)=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function setStatus(root, text) {
    var node = root.querySelector("[data-rmc-local-ai-status]");
    if (node) node.textContent = text;
  }

  function consented(root) {
    var node = root.querySelector("[data-rmc-local-ai-consent]");
    if (!node || !node.checked) {
      setStatus(root, "Confirm the one-action consent first.");
      return false;
    }
    return true;
  }

  async function deviceEligible(config) {
    var requiredMemory = Number(config.requirements.minimum_device_memory_gb || 4);
    if (navigator.deviceMemory && navigator.deviceMemory < requiredMemory) {
      throw new Error("This device does not meet the local model memory requirement.");
    }
    if (navigator.storage && navigator.storage.estimate) {
      var estimate = await navigator.storage.estimate();
      var free = Number(estimate.quota || 0) - Number(estimate.usage || 0);
      if (free < Number(config.requirements.minimum_free_bytes || 0)) {
        throw new Error("This device does not have enough free storage for the local model.");
      }
    }
  }

  function initializeBrowser(root, cfg, input) {
    var draft = root.querySelector("[data-rmc-browser-draft]");
    var purge = root.querySelector("[data-rmc-browser-purge]");
    if (!draft || !cfg.features.browser_inference) return;
    draft.hidden = false;
    purge.hidden = false;
    var worker = null;
    var ready = false;

    draft.addEventListener("click", async function () {
      if (!consented(root)) return;
      var prompt = String(input.value || "").trim();
      if (!prompt) { setStatus(root, "Enter draft instructions first."); return; }
      try {
        setStatus(root, "Checking this device...");
        var response = await fetch(cfg.urls.browser_inference_config, { credentials: "same-origin" });
        var modelConfig = await response.json();
        if (!response.ok || !modelConfig.available) throw new Error(modelConfig.detail || "Local model is not staged.");
        await deviceEligible(modelConfig);
        if (!worker) {
          worker = new Worker(modelConfig.worker_url);
          worker.onmessage = function (event) {
            var message = event.data || {};
            if (message.type === "ready") {
              ready = true;
              setStatus(root, "Local model ready. Select Draft again.");
            } else if (message.type === "result") {
              input.value = message.text;
              input.dispatchEvent(new Event("input", { bubbles: true }));
              setStatus(root, "Local draft inserted for review.");
            } else if (message.type === "purged") {
              ready = false;
              worker.terminate();
              worker = null;
              setStatus(root, "Local model data removed.");
            } else if (message.type === "error") {
              setStatus(root, message.error || "Local inference failed.");
            }
          };
          worker.postMessage({ type: "init", config: modelConfig });
        } else if (ready) {
          worker.postMessage({ type: "generate", requestId: Date.now(), prompt: prompt });
          setStatus(root, "Drafting locally...");
        }
      } catch (error) {
        setStatus(root, String(error.message || error));
      }
    });
    purge.addEventListener("click", function () {
      if (worker) worker.postMessage({ type: "purge" });
      else setStatus(root, "No local model is loaded.");
    });
  }

  function initializeVoice(root, cfg, input) {
    var record = root.querySelector("[data-rmc-voice-record]");
    var read = root.querySelector("[data-rmc-voice-read]");
    if (!record || !cfg.features.local_voice) return;
    record.hidden = false;
    read.hidden = false;
    var recorder = null;
    var chunks = [];

    record.addEventListener("click", async function () {
      if (!consented(root)) return;
      if (recorder && recorder.state === "recording") {
        recorder.stop();
        record.textContent = "Speak";
        return;
      }
      try {
        var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        chunks = [];
        recorder = new MediaRecorder(stream);
        recorder.ondataavailable = function (event) { if (event.data.size) chunks.push(event.data); };
        recorder.onstop = async function () {
          stream.getTracks().forEach(function (track) { track.stop(); });
          var blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          try {
            var response = await fetch(cfg.urls.local_voice_transcribe, {
              method: "POST",
              credentials: "same-origin",
              headers: {
                "Content-Type": blob.type,
                "X-CSRFToken": csrfToken(),
                "X-RMC-Voice-Consent": "true",
                "X-RMC-Voice-Language": (cfg.local_ai.voice_languages || ["en"])[0]
              },
              body: blob
            });
            var payload = await response.json();
            if (!response.ok) throw new Error(payload.detail || "Transcription failed.");
            input.value = payload.text;
            input.dispatchEvent(new Event("input", { bubbles: true }));
            setStatus(root, "Transcript inserted for editing.");
          } catch (error) { setStatus(root, String(error.message || error)); }
        };
        recorder.start();
        record.textContent = "Stop";
        setStatus(root, "Recording. Select Stop when finished.");
      } catch (_error) { setStatus(root, "Microphone access is unavailable. Use the text field."); }
    });

    read.addEventListener("click", async function () {
      if (!consented(root)) return;
      var text = String(input.value || "").trim();
      if (!text) { setStatus(root, "Enter text to read aloud."); return; }
      try {
        var response = await fetch(cfg.urls.local_voice_synthesize, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
          body: JSON.stringify({ text: text, language: (cfg.local_ai.voice_languages || ["en"])[0], consent: true })
        });
        if (!response.ok) {
          var error = await response.json();
          throw new Error(error.detail || "Speech synthesis failed.");
        }
        var url = URL.createObjectURL(await response.blob());
        var audio = new Audio(url);
        audio.onended = function () { URL.revokeObjectURL(url); };
        await audio.play();
        setStatus(root, "Reading aloud from the local service.");
      } catch (error) { setStatus(root, String(error.message || error)); }
    });
  }

  function boot() {
    var cfg = chromeConfig();
    if (!cfg.features || (!cfg.features.browser_inference && !cfg.features.local_voice)) return;
    document.querySelectorAll("[data-rmc-local-ai]").forEach(function (root) {
      if (root.dataset.rmcLocalAiReady === "1") return;
      var rail = root.closest(".lx-copilot");
      var input = rail && rail.querySelector("[data-rmc-copilot-input]");
      if (!input) return;
      root.dataset.rmcLocalAiReady = "1";
      root.hidden = false;
      initializeBrowser(root, cfg, input);
      initializeVoice(root, cfg, input);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
