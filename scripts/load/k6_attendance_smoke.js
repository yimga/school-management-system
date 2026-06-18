// k6 OSS smoke — attendance list (staging only).
// Install: https://k6.io/docs/get-started/installation/
//
//   k6 run scripts/load/k6_attendance_smoke.js \
//     -e BASE_URL=http://127.0.0.1:8000 \
//     -e SCHOOL_PATH=/t/demo-school

import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 50,
  duration: "30s",
};

export default function () {
  const base = __ENV.BASE_URL || "http://127.0.0.1:8000";
  const prefix = __ENV.SCHOOL_PATH || "/t/demo-school";
  const token = __ENV.RMC_LOAD_AUTH_TOKEN || "";
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = http.get(`${base}${prefix}/api/v1/attendance/`, { headers });
  check(res, { "status is 200 or 401/403": (r) => [200, 401, 403].includes(r.status) });
  sleep(0.1);
}
