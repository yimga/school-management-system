#!/usr/bin/env npx tsx
/**
 * CLI entry for Phase 3 — deterministic analytics seed (stdout JSON or integrity check).
 */
import {
  seedTenantAnalytics,
  validateTenantAnalyticsIntegrity,
} from "./analytics-seeder";

function main(): void {
  const tenantId = process.argv[2] || "platform-overview";
  const bundle = seedTenantAnalytics(tenantId);
  const check = validateTenantAnalyticsIntegrity(bundle);
  if (!check.ok) {
    console.error("SEED INTEGRITY FAIL:", check.errors.join("; "));
    process.exit(1);
  }
  if (process.argv.includes("--json")) {
    process.stdout.write(`${JSON.stringify(bundle, null, 2)}\n`);
  } else {
    console.log(
      `SEED OK tenant=${bundle.tenantId} revenue=${bundle.totals.revenue} budget=${bundle.totals.budget} points=${bundle.timeseries.length}`,
    );
  }
}

main();
