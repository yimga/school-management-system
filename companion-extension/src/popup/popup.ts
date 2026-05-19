/**
 * v3.37.0 — Popup controller wiring the multi-tenant switcher.
 *
 * Responsibilities:
 *   1. Render the dropdown of known tenants (slug + displayName).
 *   2. On change, call ``setActiveTenant`` then re-fetch the server
 *      pubkey using ``?tenant=<active>`` and display the new fingerprint.
 *   3. Render the fingerprint in 4-char-grouped hex prominently with a
 *      "Verify" button that calls ``markVerified``.
 *   4. Refresh button triggers a fresh server fetch (cache bypass).
 *
 * The popup HTML is expected to provide these element IDs:
 *
 *     <select id="tenant-select"></select>
 *     <button id="tenant-add">Add tenant</button>
 *     <button id="tenant-remove">Remove tenant</button>
 *     <button id="pubkey-refresh">Refresh fingerprint</button>
 *     <button id="pubkey-verify">Verify (operator)</button>
 *     <span id="pubkey-fingerprint"></span>
 *     <span id="pubkey-key-version"></span>
 *
 * If any of those IDs are missing in the host HTML, the wire-up is a
 * silent no-op — the popup can ship a subset of these controls and
 * the rest light up when added.
 */

import {
  addTenant,
  fetchAndRecordPubkey,
  formatFingerprintForDisplay,
  getKnownTenants,
  markVerified,
  removeTenant,
  setActiveTenant,
} from "../lib/tenant_switcher";
import type { FetchLike, TenantSwitcherState } from "../lib/tenant_switcher";

export interface PopupConfig {
  baseUrl: string;
  fetchImpl?: FetchLike;
  // Prompt helper for "Add tenant" — tests inject a stub. Default uses
  // the browser's window.prompt(); the popup HTML may swap it for an
  // inline form.
  addPrompt?: () => Promise<{ slug: string; displayName: string } | null>;
}

export async function wireTenantSwitcher(
  doc: Document,
  cfg: PopupConfig
): Promise<void> {
  const fetchImpl: FetchLike =
    cfg.fetchImpl ??
    ((url, init) =>
      (globalThis as unknown as { fetch: FetchLike }).fetch(url, init));

  const $select = doc.getElementById("tenant-select") as HTMLSelectElement | null;
  const $add = doc.getElementById("tenant-add") as HTMLButtonElement | null;
  const $remove = doc.getElementById("tenant-remove") as HTMLButtonElement | null;
  const $refresh = doc.getElementById("pubkey-refresh") as HTMLButtonElement | null;
  const $verify = doc.getElementById("pubkey-verify") as HTMLButtonElement | null;
  const $fp = doc.getElementById("pubkey-fingerprint");
  const $kv = doc.getElementById("pubkey-key-version");

  const renderSelect = (state: TenantSwitcherState) => {
    if (!$select) return;
    $select.innerHTML = "";
    for (const t of state.tenants) {
      const opt = doc.createElement("option");
      opt.value = t.slug;
      opt.textContent = `${t.displayName} (${t.slug})`;
      if (t.slug === state.activeSlug) opt.selected = true;
      $select.appendChild(opt);
    }
  };

  const renderFingerprint = (fpB64: string | null, version: string | null) => {
    if ($fp) {
      $fp.textContent = fpB64
        ? formatFingerprintForDisplay(fpB64)
        : "(no fingerprint cached)";
    }
    if ($kv) {
      $kv.textContent = version ?? "";
    }
  };

  const refreshForActive = async () => {
    const state = await getKnownTenants();
    if (!state.activeSlug) {
      renderFingerprint(null, null);
      return;
    }
    try {
      const body = await fetchAndRecordPubkey(
        cfg.baseUrl,
        state.activeSlug,
        fetchImpl
      );
      renderFingerprint(body.fingerprint_b64, body.key_version);
    } catch (err) {
      // Surface error in the fingerprint slot rather than throwing —
      // the popup is a fragile context (chrome.action) and uncaught
      // rejections silently kill it.
      if ($fp) {
        $fp.textContent = `(fetch failed: ${
          err instanceof Error ? err.message : String(err)
        })`;
      }
    }
  };

  // Initial render.
  const initial = await getKnownTenants();
  renderSelect(initial);
  if (initial.activeSlug) {
    const active = initial.tenants.find((t) => t.slug === initial.activeSlug);
    renderFingerprint(active?.lastFingerprintB64 ?? null, null);
  }

  if ($select) {
    $select.addEventListener("change", async () => {
      const slug = $select.value;
      await setActiveTenant(slug);
      await refreshForActive();
    });
  }

  if ($add) {
    $add.addEventListener("click", async () => {
      const ask =
        cfg.addPrompt ??
        (async () => {
          const slug = (
            (globalThis as unknown as { prompt?: (q: string) => string | null })
              .prompt?.("Tenant slug?") ?? ""
          ).trim();
          if (!slug) return null;
          const displayName = (
            (globalThis as unknown as { prompt?: (q: string) => string | null })
              .prompt?.("Display name?") ?? slug
          ).trim();
          return { slug, displayName };
        });
      const input = await ask();
      if (!input) return;
      try {
        const next = await addTenant(input.slug, input.displayName);
        renderSelect(next);
        await refreshForActive();
      } catch (err) {
        // Duplicate-slug or empty-slug errors land here. Swallow into
        // the fingerprint slot so the operator gets feedback.
        if ($fp) {
          $fp.textContent = `(add failed: ${
            err instanceof Error ? err.message : String(err)
          })`;
        }
      }
    });
  }

  if ($remove) {
    $remove.addEventListener("click", async () => {
      const state = await getKnownTenants();
      if (!state.activeSlug) return;
      const next = await removeTenant(state.activeSlug);
      renderSelect(next);
      await refreshForActive();
    });
  }

  if ($refresh) {
    $refresh.addEventListener("click", async () => {
      await refreshForActive();
    });
  }

  if ($verify) {
    $verify.addEventListener("click", async () => {
      const state = await getKnownTenants();
      if (!state.activeSlug) return;
      await markVerified(state.activeSlug);
    });
  }
}
