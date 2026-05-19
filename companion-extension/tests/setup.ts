/**
 * vitest setup — installs a minimal in-memory `chrome.storage.{local,sync}`
 * mock onto globalThis BEFORE any test module loads.
 *
 * The tenant_switcher tests inject their own `LocalStorageAreaLike` fake
 * via `setStorageBackend(...)`, so this global mock exists to (a) keep
 * any module that touches `chrome.storage.*` at parse time from crashing
 * the test runner, and (b) give future popup-DOM tests a believable
 * `chrome` global without each test rebuilding it.
 *
 * The mock is intentionally minimal — it implements only the surface
 * the companion code touches. Promise-based API matches MV3 contract
 * (Chrome ≥114); callback overloads are NOT supported.
 */

interface StorageAreaLike {
  get(
    keys: string | string[] | Record<string, unknown> | null
  ): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
  remove(keys: string | string[]): Promise<void>;
  clear(): Promise<void>;
}

function makeInMemoryArea(): StorageAreaLike {
  const data: Record<string, unknown> = {};
  return {
    async get(keys) {
      if (keys === null || keys === undefined) {
        return { ...data };
      }
      if (typeof keys === "string") {
        return keys in data ? { [keys]: data[keys] } : {};
      }
      if (Array.isArray(keys)) {
        const out: Record<string, unknown> = {};
        for (const k of keys) {
          if (k in data) out[k] = data[k];
        }
        return out;
      }
      // object form: keys is default-values map.
      const out: Record<string, unknown> = {};
      for (const k of Object.keys(keys)) {
        out[k] = k in data ? data[k] : keys[k];
      }
      return out;
    },
    async set(items) {
      for (const k of Object.keys(items)) {
        data[k] = items[k];
      }
    },
    async remove(keys) {
      const arr = Array.isArray(keys) ? keys : [keys];
      for (const k of arr) {
        delete data[k];
      }
    },
    async clear() {
      for (const k of Object.keys(data)) {
        delete data[k];
      }
    },
  };
}

const chromeGlobal = {
  storage: {
    local: makeInMemoryArea(),
    sync: makeInMemoryArea(),
    session: makeInMemoryArea(),
  },
  runtime: {
    // Minimal stubs so popup code that references chrome.runtime doesn't
    // crash at import time. Tests that actually exercise message-passing
    // should inject their own fakes.
    id: "rmc-companion-test",
    getURL: (p: string) => `chrome-extension://rmc-companion-test/${p}`,
    sendMessage: async (_msg: unknown) => undefined,
    onMessage: {
      addListener: () => undefined,
      removeListener: () => undefined,
    },
  },
};

(globalThis as unknown as { chrome: typeof chromeGlobal }).chrome = chromeGlobal;
