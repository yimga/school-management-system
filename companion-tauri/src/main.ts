// RunMyCampus Tauri sibling — 4-step wizard (v3.37.0 Agent 4).
//
// Login → MAA → CSV pick & preview → Upload.
//
// The frontend NEVER stores the bearer token or password on disk;
// both live in module-scope variables for the lifetime of the page.

import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

type LoginResult = { bearer: string };
type MaaText = {
    vendor: string;
    version: string;
    text: string;
    is_draft: boolean;
    active_version: string;
};
type MAAReceipt = { maa_id: number; signed_at: string; agreement_version: string };
type IngestResult = {
    receipt_id: number;
    bundle_id: number | null;
    status: string;
    canonical_sha256: string;
    matched_domain: string;
    row_count: number;
};

// Session-only state. Never persisted.
let bearer: string | null = null;
let tenantSlug: string = "";
let serverUrl: string = "";
let maaId: number | null = null;
let serverPubkeyB64: string | null = null;

function $(id: string): HTMLElement {
    const el = document.getElementById(id);
    if (!el) throw new Error(`missing element ${id}`);
    return el;
}

function showStep(step: 1 | 2 | 3 | 4): void {
    [1, 2, 3, 4].forEach(n => {
        const el = document.getElementById(`step-${n}`);
        if (el) el.style.display = n === step ? "block" : "none";
    });
}

async function doLogin(): Promise<void> {
    const email = (document.getElementById("email") as HTMLInputElement).value;
    const password = (document.getElementById("password") as HTMLInputElement).value;
    serverUrl = (document.getElementById("server_url") as HTMLInputElement).value;
    tenantSlug = (document.getElementById("tenant_slug") as HTMLInputElement).value;
    const status = $("login-status");
    status.textContent = "Logging in…";
    try {
        const result: LoginResult = await invoke("rmc_login", {
            serverUrl,
            email,
            password,
        });
        bearer = result.bearer;
        status.textContent = "Logged in.";
        // Best-effort: fetch the server's public key for sealing.
        const pubResp = await fetch(
            `${serverUrl.replace(/\/$/, "")}/api/v1/migration/companion/server-pubkey/?tenant=${encodeURIComponent(
                tenantSlug
            )}`,
            { headers: { Authorization: `Bearer ${bearer}` } }
        );
        if (pubResp.ok) {
            const j = await pubResp.json();
            serverPubkeyB64 = j.public_key_b64;
        }
        showStep(2);
    } catch (e) {
        status.textContent = `Login failed: ${String(e)}`;
    }
}

async function doFetchMaa(): Promise<void> {
    if (!bearer) return;
    const vendor = (document.getElementById("vendor") as HTMLInputElement).value;
    const status = $("maa-status");
    status.textContent = "Fetching MAA…";
    try {
        const text: MaaText = await invoke("rmc_fetch_maa", {
            serverUrl,
            bearer,
            tenantSlug,
            vendor,
            version: null,
        });
        ($("maa-text") as HTMLTextAreaElement).value = text.text;
        ($("maa-version") as HTMLInputElement).value = text.active_version;
        if (text.is_draft) {
            status.textContent = "Cannot sign — this is a DRAFT version.";
        } else {
            status.textContent = `Fetched (version ${text.version}).`;
        }
    } catch (e) {
        status.textContent = `MAA fetch failed: ${String(e)}`;
    }
}

async function doSignMaa(): Promise<void> {
    if (!bearer) return;
    const vendor = (document.getElementById("vendor") as HTMLInputElement).value;
    const holder = (document.getElementById("holder") as HTMLInputElement).value;
    const role = (document.getElementById("role") as HTMLInputElement).value;
    const version = ($("maa-version") as HTMLInputElement).value;
    const body = ($("maa-text") as HTMLTextAreaElement).value;
    const status = $("maa-status");
    status.textContent = "Signing MAA…";
    try {
        const receipt: MAAReceipt = await invoke("rmc_sign_maa", {
            serverUrl,
            bearer,
            tenantSlug,
            vendor,
            holder,
            role,
            agreementVersion: version,
            body,
        });
        maaId = receipt.maa_id;
        status.textContent = `Signed. MAA id = ${receipt.maa_id}`;
        showStep(3);
    } catch (e) {
        status.textContent = `MAA sign rejected: ${String(e)}`;
    }
}

async function doPickCsv(): Promise<void> {
    const selected = await open({
        multiple: false,
        filters: [{ name: "CSV files", extensions: ["csv"] }],
    });
    if (typeof selected === "string") {
        ($("csv-path") as HTMLInputElement).value = selected;
    }
}

async function doIngestCsv(): Promise<void> {
    if (!bearer || maaId === null || serverPubkeyB64 === null) {
        $("ingest-status").textContent =
            "Cannot ingest: complete login + MAA + server pubkey fetch first.";
        return;
    }
    const csvPath = ($("csv-path") as HTMLInputElement).value;
    const vendor = (document.getElementById("vendor") as HTMLInputElement).value;
    const idemKey =
        ($("idem-key") as HTMLInputElement).value ||
        `tauri-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    const status = $("ingest-status");
    status.textContent = "Parsing, sealing and uploading…";
    try {
        const result: IngestResult = await invoke("rmc_ingest_csv", {
            serverUrl,
            bearer,
            csvPath,
            vendorSource: vendor,
            pubkeyB64: serverPubkeyB64,
            maaId,
            idempotencyKey: idemKey,
        });
        status.textContent = `Uploaded: domain=${result.matched_domain} rows=${result.row_count} receipt=${result.receipt_id} sha=${result.canonical_sha256.slice(0, 12)}…`;
        showStep(4);
    } catch (e) {
        status.textContent = `Upload failed: ${String(e)}`;
    }
}

window.addEventListener("DOMContentLoaded", () => {
    $("login-btn").addEventListener("click", () => void doLogin());
    $("maa-fetch-btn").addEventListener("click", () => void doFetchMaa());
    $("maa-sign-btn").addEventListener("click", () => void doSignMaa());
    $("csv-pick-btn").addEventListener("click", () => void doPickCsv());
    $("csv-ingest-btn").addEventListener("click", () => void doIngestCsv());
    showStep(1);
});
