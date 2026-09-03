// @ts-check
/**
 * Derive the Unified Wizard Framework registry from disk — never hand-type it.
 *
 * WHY THIS MODULE EXISTS
 * ----------------------
 * `unified-wizard-framework.spec.js` used to carry a hand-typed
 * `WIZARD_REGISTRY_KEYS` array plus `expect(WIZARD_REGISTRY_KEYS).toHaveLength(23)`
 * over a comment reading "Update this number when adding more wizards."
 *
 * A hand-maintained magic number asserts the WORD, not the BEHAVIOUR. The array
 * had drifted to 24 entries against 38 registered wizards and the literal had
 * never been bumped, so the only thing that assertion proved was that somebody
 * had once typed a number. Pasting the 14 missing keys in would have added zero
 * coverage and created the same trap one commit later.
 *
 * This module reads `apps/setup_studio/wizards/*.json` — the same directory
 * `apps.setup_studio.wizard_engine.load_wizard_registry()` walks — and applies
 * the same admission rules, so a newly registered wizard cannot be missed and
 * there is no second list to keep in sync.
 *
 * Admission rules mirrored from `load_wizard_registry()`:
 *   - a file whose name starts with "_" is skipped
 *   - `"feature_flag_disabled": true` is parsed but NOT registered
 *   - `wizard_key` must be a non-empty string
 *   - a duplicate `wizard_key` is a registry error (the Python loader logs it
 *     and drops the second copy; here it throws, because a spec that silently
 *     lost a wizard is the defect this file exists to prevent)
 *
 * `scripts/verify_wizard_playwright_spec_coverage.py` executes
 * `describeRegistry()` under Node and cross-checks it against its own
 * independent walk of the same directory, so the derivation itself is verified
 * rather than trusted.
 */

const fs = require("fs");
const path = require("path");

// helpers/ -> e2e/ -> tests/ -> <repo root>
const REPO_ROOT = path.join(__dirname, "..", "..", "..");
const WIZARDS_DIR = path.join(REPO_ROOT, "apps", "setup_studio", "wizards");

/**
 * The audience the operator wizard index (`/super/wizards/`) lists.
 * `OperatorWizardIndexView.get` renders `list_wizards_for_audience("operator")`
 * with no further filtering, so this is the exact SOT for that page.
 */
const OPERATOR_AUDIENCE = "operator";

/**
 * Registered operator-audience wizards that are deliberately NOT expected as a
 * card on the operator index, keyed by wizard_key with the reason as the value.
 *
 * THIS MAP IS EMPTY ON PURPOSE, AND THAT IS A FINDING, NOT AN OVERSIGHT.
 * The operator index path is:
 *     OperatorWizardIndexView.get
 *       -> wizard_engine.list_wizards_for_audience("operator")   (audience filter only)
 *       -> wizard_views._wizard_index_context
 *       -> wizard_categories.group_wizards_by_category           (unmapped -> DEFAULT_CATEGORY,
 *                                                                 so grouping never drops a wizard)
 *       -> wizard_views._decorate_stages                         (one card per wizard, no filter)
 *       -> operator_wizard_index.html                            (renders every stage card)
 * Nothing on that path can hide a wizard, and `wizard_gates.assert_wizard_gates`
 * is applied on the wizard DETAIL view, never on the index. So every wizard whose
 * `audience` array contains "operator" IS an operator-index wizard.
 *
 * Two candidates were considered explicitly because they look like exceptions:
 *   - `mfa_setup` — audience includes "operator" and it is mapped to the
 *     "get_started" stage in `wizard_categories.WIZARD_CATEGORY_BY_KEY`.
 *     `OperatorWizardView.get` even carries a comment about rendering
 *     mfa_setup's completion banner ON the operator index. It renders. Not excluded.
 *   - `super_create_school` — audience is exactly ["operator"] and it is mapped
 *     to "get_started" too. Its card renders; what it does AFTER the click
 *     (`_resolve_school` returns None for a school-less operator and the detail
 *     view redirects back) is a separate concern from index presence. Not excluded.
 *
 * Adding an entry here requires a reason string. The spec's registry-coverage
 * test and `verify_wizard_playwright_spec_coverage.py` both reject an entry that
 * is not a registered operator-audience wizard, or whose reason is blank — so an
 * unexplained absence, which is what let the old list rot, cannot be spelled.
 *
 * @type {Readonly<Record<string, string>>}
 */
const OPERATOR_INDEX_EXCLUSIONS = Object.freeze({});

/** @param {Record<string, unknown>} obj @param {string} key */
function hasOwn(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

/**
 * Walk the wizard JSON directory and return the live registry.
 * @param {string} [dir]
 * @returns {Map<string, {key: string, audience: string[], file: string}>}
 */
function loadWizardRegistry(dir) {
  const target = dir || WIZARDS_DIR;
  if (!fs.existsSync(target)) {
    throw new Error(`wizard registry: directory not found: ${target}`);
  }
  const files = fs
    .readdirSync(target)
    .filter((name) => name.endsWith(".json") && !name.startsWith("_"))
    .sort();

  /** @type {Map<string, {key: string, audience: string[], file: string}>} */
  const registry = new Map();
  for (const file of files) {
    const raw = JSON.parse(fs.readFileSync(path.join(target, file), "utf8"));
    if (raw.feature_flag_disabled === true) continue;
    const key = raw.wizard_key;
    if (typeof key !== "string" || key.length === 0) {
      throw new Error(`wizard registry: ${file} has no usable "wizard_key"`);
    }
    const existing = registry.get(key);
    if (existing) {
      throw new Error(
        `wizard registry: duplicate wizard_key "${key}" in ${file} and ${existing.file}`,
      );
    }
    registry.set(key, {
      key,
      audience: Array.isArray(raw.audience) ? raw.audience.map(String) : [],
      file,
    });
  }
  return registry;
}

/**
 * Every registered wizard key, sorted.
 * @param {string} [dir]
 * @returns {string[]}
 */
function wizardKeys(dir) {
  return [...loadWizardRegistry(dir).keys()].sort();
}

/**
 * Registered wizard keys whose `audience` array contains `audience`, sorted.
 * @param {string} audience
 * @param {string} [dir]
 * @returns {string[]}
 */
function keysForAudience(audience, dir) {
  return [...loadWizardRegistry(dir).values()]
    .filter((w) => w.audience.includes(audience))
    .map((w) => w.key)
    .sort();
}

/**
 * The exact set of wizard cards the operator index must render.
 * @param {string} [dir]
 * @returns {string[]}
 */
function operatorIndexKeys(dir) {
  return keysForAudience(OPERATOR_AUDIENCE, dir).filter(
    (key) => !hasOwn(OPERATOR_INDEX_EXCLUSIONS, key),
  );
}

/**
 * A JSON-serialisable snapshot of everything the spec derives, so the Python
 * verifier can execute this module and diff it against its own walk of the same
 * directory instead of taking the derivation on trust.
 * @param {string} [dir]
 */
function describeRegistry(dir) {
  const registry = loadWizardRegistry(dir);
  return {
    wizards_dir: dir || WIZARDS_DIR,
    wizard_keys: [...registry.keys()].sort(),
    audience_by_key: Object.fromEntries(
      [...registry.values()].map((w) => [w.key, [...w.audience].sort()]),
    ),
    operator_audience_keys: keysForAudience(OPERATOR_AUDIENCE, dir),
    operator_index_exclusions: { ...OPERATOR_INDEX_EXCLUSIONS },
    operator_index_keys: operatorIndexKeys(dir),
  };
}

module.exports = {
  OPERATOR_AUDIENCE,
  OPERATOR_INDEX_EXCLUSIONS,
  REPO_ROOT,
  WIZARDS_DIR,
  describeRegistry,
  keysForAudience,
  loadWizardRegistry,
  operatorIndexKeys,
  wizardKeys,
};
