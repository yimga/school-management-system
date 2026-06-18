/* IndexedDB-backed draft persistence for unsubmitted sheet edits.
 *
 * Why: the mandate calls out preserving uncommitted text inputs when a
 * side-sheet overlay opens.  This wraps a tiny IDB store so an offline
 * tenant won't lose in-flight notes if the page reloads.
 *
 * Falls back to localStorage when IDB is unavailable (older Safari, jsdom).
 */

const DB_NAME = "rmc-lux-drafts";
const STORE = "drafts";
const VERSION = 1;
const LS_PREFIX = "rmc-lux-draft::";

interface SheetDraft {
  id: string;
  body: string;
  savedAt: number;
}

function hasIDB(): boolean {
  return typeof indexedDB !== "undefined";
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("idb open failed"));
  });
}

/* Draft persistence is BEST-EFFORT by contract: it must never reject. A failed
 * autosave (IDB quota, private-browsing, transaction error) is degraded silently
 * — the same way the localStorage fallback already swallows quota errors — so
 * callers (fire-and-forget autosave) can never raise an unhandled rejection.
 * The functions resolve to void / null on any storage failure. */

export async function saveSheetDraft(id: string, body: string): Promise<void> {
  const draft: SheetDraft = { id, body, savedAt: Date.now() };
  if (!hasIDB()) {
    try {
      localStorage.setItem(LS_PREFIX + id, JSON.stringify(draft));
    } catch {
      /* quota / privacy mode — silently no-op */
    }
    return;
  }
  try {
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(draft);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error("idb put failed"));
    });
    db.close();
  } catch {
    /* best-effort autosave — degrade silently on any IDB failure */
  }
}

export async function loadSheetDraft(id: string): Promise<SheetDraft | null> {
  if (!hasIDB()) {
    try {
      const raw = localStorage.getItem(LS_PREFIX + id);
      return raw ? (JSON.parse(raw) as SheetDraft) : null;
    } catch {
      return null;
    }
  }
  try {
    const db = await openDB();
    const draft = await new Promise<SheetDraft | null>((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const req = tx.objectStore(STORE).get(id);
      req.onsuccess = () => resolve((req.result as SheetDraft | undefined) ?? null);
      req.onerror = () => reject(req.error ?? new Error("idb get failed"));
    });
    db.close();
    return draft;
  } catch {
    return null;
  }
}

export async function clearSheetDraft(id: string): Promise<void> {
  if (!hasIDB()) {
    try {
      localStorage.removeItem(LS_PREFIX + id);
    } catch {
      /* ignore */
    }
    return;
  }
  try {
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error("idb delete failed"));
    });
    db.close();
  } catch {
    /* best-effort — degrade silently */
  }
}
