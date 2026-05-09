// k6 load-test baseline for RunMyCampus.
//
// Profile: 6 concurrent virtual users for 5 minutes hitting the marketing
// home + version endpoint + health endpoint. Read-only, no writes.
//
// Run locally:
//   BASE_URL=http://127.0.0.1:8000 k6 run tests/load/k6_baseline.js
//
// Run against staging:
//   BASE_URL=https://manager.runmycampus.com k6 run tests/load/k6_baseline.js
//
// Run a heavier soak (10 VUs / 30 min):
//   BASE_URL=... DURATION=30m VUS=10 k6 run tests/load/k6_baseline.js
//
// SLO targets (declared in docs/operations/PERFORMANCE_BASELINE.md):
//   - http_req_duration p95 < 1500 ms
//   - http_req_failed   < 1%
//   - error_count       < 5 over the run
//
// k6 fails (non-zero exit) when any threshold is breached, so this script can
// gate a release in CI once a deployed staging exists to baseline against.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

const BASE_URL = (__ENV.BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const VUS = Number(__ENV.VUS || 6);
const DURATION = __ENV.DURATION || '5m';

export const errorCount = new Counter('errors');

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1500'],
    errors: ['count<5'],
  },
  // Don't follow redirects — we want to measure raw 200/302 distribution.
  noConnectionReuse: false,
  discardResponseBodies: true,
};

const ENDPOINTS = [
  { path: '/', accept_status: [200, 302] },
  { path: '/-/version/', accept_status: [200] },
  { path: '/health/', accept_status: [200, 204] },
];

export default function () {
  for (const ep of ENDPOINTS) {
    const res = http.get(`${BASE_URL}${ep.path}`, {
      headers: { 'Accept': 'application/json,text/html' },
      tags: { endpoint: ep.path },
    });
    const ok = check(res, {
      'status acceptable': (r) => ep.accept_status.includes(r.status),
    });
    if (!ok) {
      errorCount.add(1);
    }
    sleep(0.2 + Math.random() * 0.3);
  }
}
