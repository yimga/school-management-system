# Browser Inference

Browser inference is an optional, tenant-only drafting path. It is disabled by
default and cannot activate until an operator stages a same-origin runtime and
model pack in `config/browser_model_pack.json`.

## Safety Contract

- The manifest uses an immutable model revision and SHA-256 plus byte size for
  every asset.
- Runtime and model URLs must be same-origin paths.
- The browser checks device memory and storage quota before loading.
- Every action requires visible one-action consent.
- Output is inserted into an editable draft field. It never writes a final
  grade, payment, attendance record, or other authoritative record.
- The worker has no provider URL and performs no application database write.
- `Remove local model` disposes the runtime and clears browser-AI caches.
- `BROWSER_AI_ENABLED=0` is the immediate kill switch.

The committed manifest is intentionally unstaged. Repository verification means
the governed integration exists; it does not certify a model, browser, device,
language, task quality, or production rollout. Pilot promotion requires signed
external evidence through the intelligence-promotion gate.

## Runtime Adapter

The staged runtime must expose `self.RMCBrowserModel` inside the worker with:

```javascript
load(modelManifest)
generate(prompt, { max_new_tokens })
dispose()
```

This adapter permits Transformers.js or another self-hosted WebAssembly/WebGPU
runtime without allowing a CDN dependency or a parallel server-side AI route.
