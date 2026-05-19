/**
 * Content-script stub.
 *
 * Injected into the 6 SIS vendor tabs (PowerSchool / Blackbaud /
 * Veracross / Alma / FACTS / Skyward) at `document_idle` per
 * manifest.json::content_scripts.
 *
 * This stub does NOTHING by default — DOM reading routes through the
 * popup's "extract" button, which sends a message to the active tab.
 * That handshake plus per-vendor readers (src/vendors/*.ts) land in a
 * future wave; see docs/COMPANION_SIBLINGS.md.
 *
 * Trust boundary: this script reads the DOM of the operator's own
 * authenticated tab ONLY. It never embeds, captures, or replays SIS
 * credentials.
 */

export {};
