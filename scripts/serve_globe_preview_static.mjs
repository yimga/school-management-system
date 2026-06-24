#!/usr/bin/env node
/** Static server for globe preview Playwright (repo root on :8765). */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PORT = Number(process.env.GLOBE_PREVIEW_PORT || 8765);
const HOST = process.env.GLOBE_PREVIEW_HOST || '127.0.0.1';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.jpg': 'image/jpeg',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
};

function previewGlobePayload() {
  let globe = {};
  let fleet = {};
  try {
    const html = fs.readFileSync(path.join(ROOT, 'artifacts', 'global-footprint-section-preview.html'), 'utf8');
    const globeMatch = html.match(/<script[^>]*id="rmc-world-globe-data"[^>]*>([\s\S]*?)<\/script>/);
    const fleetMatch = html.match(/<script[^>]*id="rmc-operator-fleet-bootstrap"[^>]*>([\s\S]*?)<\/script>/);
    if (globeMatch) globe = JSON.parse(globeMatch[1]);
    if (fleetMatch) fleet = JSON.parse(fleetMatch[1]);
  } catch (_err) {
    globe = {};
    fleet = {};
  }
  const markers = Array.isArray(globe.markers) ? globe.markers : [];
  const regionLabels = Array.isArray(globe.region_labels) ? globe.region_labels : [];
  return {
    ok: true,
    preview: true,
    revision: 'preview-static',
    schools_live: fleet.schools_live || markers.length || 3,
    marker_count: fleet.marker_count || markers.length || 3,
    display_count: fleet.marker_count || markers.length || 3,
    subline: fleet.summary_label || 'Across 2 regions · 1 country today',
    regional_breakdown: [
      { label: 'West Africa', count: 1 },
      { label: 'Other', count: Math.max(1, (markers.length || 3) - 1) },
    ],
    pulse_events: Array.isArray(fleet.pulse_events) && fleet.pulse_events.length ? fleet.pulse_events : [
      { time_label: 'now', text: '+1 school live · West Africa' },
      { time_label: '1h', text: 'Tour completed · West Africa' },
    ],
    markers,
    region_labels: regionLabels,
    country_labels: Array.isArray(globe.country_labels) ? globe.country_labels : [],
    arcs: Array.isArray(globe.arcs) ? globe.arcs : [],
    expansion_targets: Array.isArray(globe.expansion_targets) ? globe.expansion_targets : [],
    aurora: fleet.aurora || 'good',
    regional_deltas: fleet.regional_deltas || { 'West Africa': 1 },
  };
}

http
  .createServer((req, res) => {
    const raw = (req.url || '/').split('?')[0];
    if (raw === '/super/api/globe/live/' || raw === '/super/api/globe/markers/') {
      res.writeHead(200, { 'Content-Type': MIME['.json'] });
      res.end(JSON.stringify(previewGlobePayload()));
      return;
    }
    if (raw === '/super/api/globe/stream/') {
      res.writeHead(200, {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache',
        Connection: 'close',
      });
      res.end(`event: globe.refresh\ndata: ${JSON.stringify(previewGlobePayload())}\n\n`);
      return;
    }
    if (raw === '/super/api/operator/fleet/context/') {
      res.writeHead(200, { 'Content-Type': MIME['.json'] });
      res.end(
        JSON.stringify({
          ok: true,
          preview: true,
          fleet_brief: {
            headline: 'Preview fleet healthy.',
            body: 'Static preview context loaded without live backend calls.',
          },
          pulse_events: [],
          regional_breakdown: [],
        })
      );
      return;
    }
    if (raw === '/super/api/operator/fleet/globe-presence/') {
      res.writeHead(204);
      res.end();
      return;
    }
    let rel = decodeURIComponent(raw.replace(/^\//, ''));
    if (!rel || raw.endsWith('/')) {
      rel = path.join(rel, 'index.html');
    }
    const file = path.normalize(path.join(ROOT, rel));
    if (!file.startsWith(ROOT)) {
      res.writeHead(403);
      res.end('Forbidden');
      return;
    }
    fs.readFile(file, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end('Not found');
        return;
      }
      const ext = path.extname(file).toLowerCase();
      res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
      res.end(data);
    });
  })
  .listen(PORT, HOST, () => {
    process.stdout.write(`GLOBE_PREVIEW_STATIC_READY http://${HOST}:${PORT}\n`);
  });
