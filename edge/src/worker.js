// RunMyCampus edge Worker (v4.00.0).
//
// Two routes:
//   1. /edge/runtime/*  — SWR cache for slow-changing tenant config payloads
//   2. /edge/llm/*      — Authenticated passthrough to the central LiteLLM proxy
//
// Viewport class is inferred from CF-Device-Type + Save-Data + Downlink so the
// upstream prompt-shaping layer (services/prompt_shaping.py) can pick the
// right token-stripped variant. Header name: X-RMC-Viewport ∈ {A,B,C}.
//
// Surrogate-Key headers are honored for selective edge purge. The Django
// services.edge_cache module fires purge calls when RuntimeDefaults change.

const SWR_HEADER_KEY_PREFIX = "rmc-edge-swr:";

function classifyViewport(request) {
  const cfDevice = (request.headers.get("CF-Device-Type") || "").toLowerCase();
  const saveData = (request.headers.get("Save-Data") || "").toLowerCase() === "on";
  const downlink = parseFloat(request.headers.get("Downlink") || "0");
  if (cfDevice === "mobile" || saveData || (downlink > 0 && downlink < 1.5)) return "C";
  if (cfDevice === "tablet") return "B";
  return "A";
}

function buildSurrogateKey(url, viewport) {
  // Bucket per pathname + tenant prefix so per-tenant purge works.
  const u = new URL(url);
  const tenant = u.searchParams.get("tenant") || u.hostname.split(".")[0] || "_";
  return `${tenant}::${u.pathname}::v=${viewport}`;
}

async function swrGet(env, surrogateKey) {
  const raw = await env.SWR_KV.get(SWR_HEADER_KEY_PREFIX + surrogateKey, { type: "json" });
  if (!raw) return null;
  return raw; // { body, headers, status, storedAt }
}

async function swrPut(env, surrogateKey, response) {
  const cloned = response.clone();
  const body = await cloned.text();
  const headers = {};
  for (const [k, v] of cloned.headers.entries()) headers[k] = v;
  await env.SWR_KV.put(
    SWR_HEADER_KEY_PREFIX + surrogateKey,
    JSON.stringify({ body, headers, status: cloned.status, storedAt: Date.now() }),
    { expirationTtl: parseInt(env.SWR_REVALIDATE_SECONDS, 10) || 300 },
  );
}

function isFresh(entry, staleSeconds) {
  if (!entry || !entry.storedAt) return false;
  return (Date.now() - entry.storedAt) / 1000 < staleSeconds;
}

function buildResponseFromEntry(entry, fromCache) {
  const headers = new Headers(entry.headers || {});
  headers.set("X-RMC-Edge-Cache", fromCache ? "HIT" : "REVALIDATE");
  return new Response(entry.body, { status: entry.status || 200, headers });
}

async function handleRuntime(request, env, ctx) {
  const viewport = classifyViewport(request);
  const surrogateKey = buildSurrogateKey(request.url, viewport);
  const cached = await swrGet(env, surrogateKey);
  const staleSeconds = parseInt(env.SWR_STALE_SECONDS, 10) || 15;
  if (cached && isFresh(cached, staleSeconds)) {
    return buildResponseFromEntry(cached, true);
  }
  // Stale-while-revalidate: serve stale immediately, refresh in background.
  if (cached) {
    ctx.waitUntil(refreshRuntime(request, env, surrogateKey, viewport));
    return buildResponseFromEntry(cached, true);
  }
  return await refreshRuntime(request, env, surrogateKey, viewport, /*returnResponse*/ true);
}

async function refreshRuntime(request, env, surrogateKey, viewport, returnResponse = false) {
  const u = new URL(request.url);
  const upstreamUrl = env.RUNTIME_UPSTREAM + u.pathname.replace(/^\/edge\/runtime/, "") + u.search;
  const upstreamReq = new Request(upstreamUrl, {
    method: "GET",
    headers: {
      "X-RMC-Viewport": viewport,
      "X-RMC-Edge-Origin": "1",
      "Accept": "application/json",
    },
  });
  const upstreamResp = await fetch(upstreamReq);
  if (upstreamResp.ok) {
    await swrPut(env, surrogateKey, upstreamResp);
  }
  if (returnResponse) {
    const headers = new Headers(upstreamResp.headers);
    headers.set("X-RMC-Edge-Cache", "MISS");
    return new Response(upstreamResp.body, { status: upstreamResp.status, headers });
  }
  return upstreamResp;
}

async function handleLLM(request, env) {
  // Edge-located LiteLLM passthrough. The Worker:
  //   - injects X-RMC-Viewport so the upstream picks the right prompt variant
  //   - swaps the operator's session cookie for the LITELLM_API_KEY bearer
  //   - preserves streaming (transfer-encoding: chunked) end-to-end
  const viewport = classifyViewport(request);
  const u = new URL(request.url);
  const upstreamUrl = env.LITELLM_UPSTREAM + u.pathname.replace(/^\/edge\/llm/, "") + u.search;
  const headers = new Headers(request.headers);
  headers.set("X-RMC-Viewport", viewport);
  headers.set("X-RMC-Edge-Origin", "1");
  if (env.LITELLM_API_KEY) {
    headers.set("Authorization", `Bearer ${env.LITELLM_API_KEY}`);
  }
  headers.delete("Cookie"); // never forward operator session cookies to LLM proxy
  const upstreamReq = new Request(upstreamUrl, {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? null : request.body,
  });
  return await fetch(upstreamReq);
}

async function handlePurge(request, env) {
  // Authenticated Surrogate-Key purge endpoint. Django services.edge_cache
  // fires HMAC-signed POST when RuntimeDefaults changes invalidate cache.
  if (request.method !== "POST") return new Response("method not allowed", { status: 405 });
  const sig = request.headers.get("X-RMC-Edge-Purge-Signature") || "";
  const body = await request.text();
  if (!env.EDGE_HMAC_SIGNING_KEY) return new Response("edge purge unconfigured", { status: 503 });
  const expected = await hmacSha256Hex(env.EDGE_HMAC_SIGNING_KEY, body);
  if (!timingSafeEqualHex(sig, expected)) return new Response("bad signature", { status: 401 });
  let payload;
  try { payload = JSON.parse(body); } catch { return new Response("bad json", { status: 400 }); }
  const keys = Array.isArray(payload.surrogate_keys) ? payload.surrogate_keys : [];
  await Promise.all(keys.map((k) => env.SWR_KV.delete(SWR_HEADER_KEY_PREFIX + k)));
  return new Response(JSON.stringify({ purged: keys.length }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

async function hmacSha256Hex(key, message) {
  const enc = new TextEncoder();
  const ck = await crypto.subtle.importKey(
    "raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", ck, enc.encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqualHex(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export default {
  async fetch(request, env, ctx) {
    const u = new URL(request.url);
    if (u.pathname.startsWith("/edge/runtime/")) return handleRuntime(request, env, ctx);
    if (u.pathname.startsWith("/edge/llm/")) return handleLLM(request, env);
    if (u.pathname === "/edge/_purge") return handlePurge(request, env);
    if (u.pathname === "/edge/_health") return new Response("ok", { status: 200 });
    return new Response("not found", { status: 404 });
  },
};
