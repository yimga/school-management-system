/**
 * Interactive 3D global footprint globe (control-plane cockpit).
 * Phases A–E (batch 1653): fly-to, filters, arcs, tour, clustering API bridge.
 */
import Globe from "globe.gl";

type GlobeInstance = ReturnType<ReturnType<typeof Globe>>;

type GlobeMarker = {
  lat: number;
  lng: number;
  country_code?: string;
  country_name?: string;
  status: string;
  color: string;
  ring_color: string;
  label: string;
  region: string;
  city?: string;
  name?: string;
  slug?: string;
  school_id?: string;
  delay_s?: number;
  is_cluster?: boolean;
  cluster_count?: number;
  cluster_members?: Array<{ school_id?: string; name?: string; slug?: string; status?: string }>;
  point_radius?: number;
  plan_tier?: string;
  last_sync_label?: string;
};

type GlobeTheme = {
  atmosphere: string;
  globeColor: string;
  globeEmissive: string;
  polygonCap: string;
  polygonSide: string;
  polygonStroke: string;
  polygonCapDim?: string;
  polygonCapHighlight?: string;
};

type GlobeCamera = {
  lat?: number;
  lng?: number;
  altitude?: number;
};

type GlobeArc = {
  start_lat: number;
  start_lng: number;
  end_lat: number;
  end_lng: number;
  color?: string;
  region?: string;
};

type TourWaypoint = {
  lat: number;
  lng: number;
  altitude?: number;
  label?: string;
  caption?: string;
  dwell_ms?: number;
};

type RegionLabel = {
  lat: number;
  lng: number;
  text: string;
  region: string;
  count?: number;
  kind?: "region" | "country";
  size?: number;
  color?: string;
  country_code?: string;
};

type RegionPaletteEntry = {
  cap: string;
  cap_highlight: string;
  cap_dim: string;
  label: string;
  label_country: string;
  arc: string;
  side: string;
};

type GlobePayload = {
  markers: GlobeMarker[];
  theme: GlobeTheme;
  geo_url?: string;
  globe_texture_url?: string;
  label_zoom?: { country_fade_start?: number; country_fade_end?: number };
  auto_rotate?: boolean;
  auto_rotate_speed?: number;
  camera?: GlobeCamera;
  layout?: string;
  tour_enabled?: boolean;
  region_centroids?: Record<string, GlobeCamera>;
  region_labels?: RegionLabel[];
  country_labels?: RegionLabel[];
  region_palette?: Record<string, RegionPaletteEntry>;
  iso3_region_map?: Record<string, string>;
  hq?: { lat: number; lng: number; label?: string };
  arcs?: GlobeArc[];
  tour_waypoints?: TourWaypoint[];
  expansion_targets?: GlobeMarker[];
  api?: { markers?: string; stream?: string; live?: string };
  live_refresh?: {
    sse_interval_seconds?: number;
    poll_interval_ms?: number;
    sse_reconnect_ms?: number;
  };
  features?: Record<string, boolean | number>;
};

type GlobeLiveBundle = {
  revision?: string;
  markers?: GlobeMarker[];
  country_labels?: RegionLabel[];
  region_labels?: RegionLabel[];
  arcs?: GlobeArc[];
  marker_count?: number;
  display_count?: number;
  schools_live?: number;
  suspended?: number;
  frozen?: number;
  subline?: string;
  regional_breakdown?: Array<{ label: string; count: string; label_color?: string }>;
  tour_waypoints?: TourWaypoint[];
  updated_at?: string;
};

type RMCWorldGlobeApi = {
  flyTo: (opts: { lat: number; lng: number; altitude?: number; ms?: number }) => void;
  flyToRegion: (region: string | null, ms?: number) => void;
  highlightRegion: (region: string | null) => void;
  setStatusFilter: (status: string | null) => void;
  setRegionFilter: (region: string | null) => void;
  getMarkers: () => GlobeMarker[];
  getVisibleMarkers: () => GlobeMarker[];
  refreshMarkers: (params?: Record<string, string>) => Promise<void>;
  refreshLive: (params?: Record<string, string> & { force?: boolean }) => Promise<GlobeLiveBundle | null>;
  startTour: () => void;
  stopTour: () => void;
  resetView: () => void;
  isReady: () => boolean;
  getAltitude: () => number;
  getPointOfView: () => { lat: number; lng: number; altitude: number };
  setWowMode: (enabled: boolean) => void;
  setConstellationMode: (enabled: boolean) => void;
};

declare global {
  interface Window {
    RMCWorldGlobe?: RMCWorldGlobeApi;
  }
}

let globeInstance: GlobeInstance | null = null;
let allMarkers: GlobeMarker[] = [];
let visibleMarkers: GlobeMarker[] = [];
let regionHighlight: string | null = null;
let statusFilter: string | null = null;
let regionFilter: string | null = null;
let polygonFeatures: object[] = [];
let tourTimer: ReturnType<typeof setTimeout> | null = null;
let tourIndex = 0;
let tourWaypoints: TourWaypoint[] = [];
let payloadRef: GlobePayload | null = null;
let resizeHandler: (() => void) | null = null;
let allRegionLabels: RegionLabel[] = [];
let allCountryLabels: RegionLabel[] = [];
let controlsChangeHandler: (() => void) | null = null;
let liveRevision: string | null = null;
let liveRefreshInFlight = false;
let zoomRefreshTimer: ReturnType<typeof setTimeout> | null = null;
let wowModeEnabled = false;
let constellationModeEnabled = false;
let expansionTargets: GlobeMarker[] = [];
let baseArcs: GlobeArc[] = [];
let hashViewApplied = false;
let firstVisitHandled = false;

const FIRST_VISIT_KEY = "rmc-globe-first-visit-done";
const DEFAULT_CAMERA = { lat: 8, lng: -5, altitude: 1.02 };
const FILL_ALTITUDE = 1.02;

function readPayload(): GlobePayload | null {
  const el = document.getElementById("rmc-world-globe-data");
  if (!el?.textContent?.trim()) return null;
  try {
    return JSON.parse(el.textContent) as GlobePayload;
  } catch {
    return null;
  }
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function getGlobeStage(mount: HTMLElement): HTMLElement {
  return (
    (document.getElementById("rmc-world-globe-stage") as HTMLElement | null) ||
    (mount.closest(".lx-world__globe-stage") as HTMLElement | null) ||
    mount.parentElement ||
    mount
  );
}

function showFallback(container: HTMLElement): void {
  if (globeInstance && resizeHandler) {
    window.removeEventListener("resize", resizeHandler);
    resizeHandler = null;
  }
  globeInstance = null;
  const stage = getGlobeStage(container);
  container.dataset.rmcWorldGlobeInited = "";
  container.classList.remove("lx-world__globe--webgl-ready");
  stage.classList.remove("lx-world__globe--webgl-ready");
  stage.classList.add("lx-world__globe--fallback", "lx-world__globe--offline", "lx-world__globe--revealed");
  stage.setAttribute("data-rmc-globe-mode", "svg-offline");
  const canvas = container.querySelector("canvas");
  if (canvas) canvas.remove();
  const svg = stage.querySelector(".lx-world__svg-fallback");
  if (svg) {
    (svg as HTMLElement).hidden = false;
    svg.removeAttribute("hidden");
  }
  hideSkeleton(container);
  document.dispatchEvent(new CustomEvent("rmc:globe-offline-fallback"));
}

function hideSkeleton(container: HTMLElement): void {
  const stage = getGlobeStage(container);
  const sk = container.closest(".lx-world__map")?.querySelector(".lx-world__globe-skeleton");
  if (sk) sk.remove();
  stage.classList.add("lx-world__globe--revealed");
}

function applyMarkerFilters(): GlobeMarker[] {
  let list = allMarkers.slice();
  if (regionFilter) list = list.filter((m) => m.region === regionFilter);
  if (statusFilter) list = list.filter((m) => m.status === statusFilter);
  visibleMarkers = list;
  return list;
}

function paletteFor(region?: string): RegionPaletteEntry | null {
  if (!region || !payloadRef?.region_palette) return null;
  return payloadRef.region_palette[region] || payloadRef.region_palette.Other || null;
}

function polygonCapColor(d: object): string {
  const theme = payloadRef?.theme || ({} as GlobeTheme);
  const props = d as { properties?: { region?: string } };
  const region = props.properties?.region;
  const pal = paletteFor(region);
  if (regionHighlight && region && region !== regionHighlight) {
    return pal?.cap_dim || theme.polygonCapDim || "rgba(71,85,105,0.06)";
  }
  if (regionHighlight && region === regionHighlight) {
    return pal?.cap_highlight || theme.polygonCapHighlight || "rgba(129,140,248,0.22)";
  }
  if (pal?.cap) return pal.cap;
  return theme.polygonCap || "rgba(148,163,184,0.10)";
}

function syncGlobePoints(): void {
  if (!globeInstance) return;
  syncWowMarkers();
  document.dispatchEvent(
    new CustomEvent("rmc:globe-markers-updated", { detail: { count: visibleMarkers.length } })
  );
}

function syncPolygonHighlight(): void {
  if (!globeInstance || !polygonFeatures.length) return;
  const theme = payloadRef?.theme || ({} as GlobeTheme);
  const sidePal = regionHighlight ? paletteFor(regionHighlight) : null;
  globeInstance
    .polygonCapColor(polygonCapColor)
    .polygonSideColor(() => sidePal?.side || theme.polygonSide || "rgba(99,102,241,0.14)")
    .polygonStrokeColor(() => theme.polygonStroke || "rgba(148,163,184,0.22)");
}

function syncPulseRings(): void {
  if (!globeInstance) return;
  if (prefersReducedMotion()) {
    globeInstance.ringsData([]);
    return;
  }
  const points = visibleMarkers.filter((m) => !m.is_cluster && (!regionHighlight || m.region === regionHighlight));
  globeInstance
    .ringsData(points)
    .ringLat("lat")
    .ringLng("lng")
    .ringColor((d: object) => {
      const m = d as GlobeMarker;
      if (m.status === "suspended") return "rgba(252,211,77,0.85)";
      if (m.status === "frozen") return "rgba(147,197,253,0.85)";
      return m.ring_color || m.color;
    })
    .ringMaxRadius((d: object) => {
      const m = d as GlobeMarker;
      if (m.status === "suspended" || m.status === "frozen") return 3.4;
      return 2.6;
    })
    .ringPropagationSpeed((d: object) => {
      const m = d as GlobeMarker;
      if (m.status === "suspended" || m.status === "frozen") return 1.4;
      return 2.2;
    })
    .ringRepeatPeriod((d: object) => {
      const m = d as GlobeMarker;
      if (m.status === "suspended" || m.status === "frozen") return 2200;
      return 1600;
    });
}

function markerPlaceLabel(m: GlobeMarker): string {
  const parts: string[] = [];
  if (m.city) parts.push(m.city);
  const country = m.country_name || m.country_code;
  if (country) parts.push(country);
  if (m.region) parts.push(m.region);
  return parts.join(" · ");
}

function markerTooltipMeta(m: GlobeMarker): string {
  const parts: string[] = [];
  if (m.plan_tier) parts.push(m.plan_tier);
  if (m.last_sync_label) parts.push(`Sync ${m.last_sync_label}`);
  return parts.join(" · ");
}

function parseGlobeHash(): GlobeCamera | null {
  if (typeof window === "undefined") return null;
  const match = window.location.hash.match(/#globe=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),(\d+(?:\.\d+)?)/);
  if (!match) return null;
  return {
    lat: parseFloat(match[1]),
    lng: parseFloat(match[2]),
    altitude: parseFloat(match[3]),
  };
}

function applyGlobeHashIfPresent(globe: GlobeInstance): boolean {
  const hashCam = parseGlobeHash();
  if (!hashCam) return false;
  globe.pointOfView(
    {
      lat: hashCam.lat ?? DEFAULT_CAMERA.lat,
      lng: hashCam.lng ?? DEFAULT_CAMERA.lng,
      altitude: hashCam.altitude ?? FILL_ALTITUDE,
    },
    0
  );
  return true;
}

function parseColorAlpha(color: string): { rgb: string; a: number } {
  const rgba = color.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/);
  if (rgba) {
    return {
      rgb: `rgb(${rgba[1]}, ${rgba[2]}, ${rgba[3]})`,
      a: rgba[4] !== undefined ? parseFloat(rgba[4]) : 1,
    };
  }
  return { rgb: color, a: 1 };
}

function withAlpha(color: string, alpha: number): string {
  const { rgb, a } = parseColorAlpha(color);
  const m = rgb.match(/rgb\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)/);
  if (m) {
    return `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${Math.max(0, Math.min(1, alpha * a))})`;
  }
  return color;
}

function countryLabelOpacity(altitude: number): number {
  const zoom = payloadRef?.label_zoom || {};
  const fadeEnd = zoom.country_fade_end ?? 1.55;
  const fadeStart = zoom.country_fade_start ?? 1.15;
  if (altitude >= fadeEnd) return 0;
  if (altitude <= fadeStart) return 1;
  return 1 - (altitude - fadeStart) / (fadeEnd - fadeStart);
}

function labelsForAltitude(altitude: number): Array<RegionLabel & { _fade?: number }> {
  const countryFade = countryLabelOpacity(altitude);
  const countries =
    countryFade <= 0.01
      ? []
      : allCountryLabels.map((row) => ({
          ...row,
          _fade: countryFade,
          size: (row.size ?? 0.36) * (0.85 + countryFade * 0.15),
        }));
  return [...allRegionLabels, ...countries];
}

function applyLiveBundle(data: GlobeLiveBundle, opts?: { force?: boolean }): boolean {
  if (!data.markers) return false;
  const priorRevision = liveRevision;
  if (!opts?.force && data.revision && liveRevision === data.revision) {
    return false;
  }
  if (data.revision && data.revision !== priorRevision) {
    const mount = document.getElementById("rmc-world-globe");
    if (mount && !prefersReducedMotion()) {
      mount.classList.add("lx-world__globe--pulse");
      window.setTimeout(() => mount.classList.remove("lx-world__globe--pulse"), 700);
    }
  }
  if (data.revision) liveRevision = data.revision;
  allMarkers = data.markers;
  if (Array.isArray(data.country_labels)) allCountryLabels = data.country_labels;
  if (Array.isArray(data.region_labels)) allRegionLabels = data.region_labels;
  if (Array.isArray(data.tour_waypoints) && data.tour_waypoints.length) {
    tourWaypoints = data.tour_waypoints;
  }
  syncGlobePoints();
  syncMapLabels();
  if (globeInstance && Array.isArray(data.arcs)) {
    baseArcs = data.arcs;
    bindArcs(globeInstance, wowModeEnabled ? baseArcs : []);
  }
  document.dispatchEvent(
    new CustomEvent("rmc:globe-live-updated", {
      detail: { bundle: data },
    })
  );
  maybeFirstVisitFlyIn();
  return true;
}

async function fetchLiveBundle(params?: Record<string, string>): Promise<GlobeLiveBundle | null> {
  const liveUrl = payloadRef?.api?.live || payloadRef?.api?.markers;
  if (!liveUrl) return null;
  const qs = new URLSearchParams(params || {});
  if (!qs.has("zoom") && globeInstance) {
    qs.set("zoom", String(api.getAltitude()));
  }
  if (regionFilter) qs.set("region", regionFilter);
  if (statusFilter) qs.set("status", statusFilter);
  const resp = await fetch(`${liveUrl}?${qs.toString()}`, { credentials: "same-origin" });
  if (!resp.ok) return null;
  return (await resp.json()) as GlobeLiveBundle;
}

function syncMapLabels(): void {
  if (!globeInstance) return;
  const altitude = api.getAltitude();
  const labels = labelsForAltitude(altitude);
  globeInstance
    .labelsData(labels)
    .labelLat("lat")
    .labelLng("lng")
    .labelText("text")
    .labelSize((d: object) => (d as RegionLabel).size ?? 0.5)
    .labelDotRadius(0)
    .labelColor((d: object) => {
      const row = d as RegionLabel & { _fade?: number };
      let base = row.color;
      if (!base) {
        const pal = paletteFor(row.region);
        base =
          row.kind === "country"
            ? pal?.label_country || "rgba(203,213,225,0.75)"
            : pal?.label || "rgba(148,163,184,0.82)";
      }
      if (row.kind === "country" && row._fade !== undefined) {
        return withAlpha(base, row._fade);
      }
      return base;
    })
    .labelAltitude((d: object) => ((d as RegionLabel).kind === "country" ? 0.014 : 0.008))
    .labelResolution(2);
}

function bindMapLabels(globe: GlobeInstance, payload: GlobePayload): void {
  allRegionLabels = payload.region_labels || [];
  allCountryLabels = payload.country_labels || [];
  syncMapLabels();
  const controls = globe.controls();
  if (controlsChangeHandler) {
    controls.removeEventListener("change", controlsChangeHandler);
  }
  controlsChangeHandler = () => {
    syncMapLabels();
    syncWowMarkers();
    if (zoomRefreshTimer) clearTimeout(zoomRefreshTimer);
    zoomRefreshTimer = window.setTimeout(() => {
      void api.refreshLive({});
    }, 280);
  };
  controls.addEventListener("change", controlsChangeHandler);
}

function enrichPolygonFeatures(features: object[], isoMap: Record<string, string>): object[] {
  return features.map((raw) => {
    const feat = raw as { id?: string; properties?: Record<string, unknown> };
    const iso3 = feat.id || (feat.properties?.iso_a3 as string | undefined) || (feat.properties?.adm0_a3 as string | undefined);
    const region = iso3 ? isoMap[iso3] : undefined;
    if (!region) return raw;
    return {
      ...feat,
      properties: { ...(feat.properties || {}), region },
    };
  });
}

function bindArcs(globe: GlobeInstance, arcs: GlobeArc[], golden = false): void {
  if (!arcs.length) {
    globe.arcsData([]);
    return;
  }
  globe
    .arcsData(arcs)
    .arcColor((d: object) => {
      if (golden) return "rgba(251,191,36,0.62)";
      return (d as GlobeArc).color || "rgba(99,102,241,0.42)";
    })
    .arcAltitude(0.12)
    .arcStroke(0.4)
    .arcDashLength(0.4)
    .arcDashGap(0.2)
    .arcDashAnimateTime(prefersReducedMotion() ? 0 : golden ? 3200 : 2800);
}

function syncArcLayer(): void {
  if (!globeInstance) return;
  if ((wowModeEnabled || constellationModeEnabled) && baseArcs.length) {
    bindArcs(globeInstance, baseArcs);
  } else {
    bindArcs(globeInstance, []);
  }
}

function buildGoldenTourArcs(waypoints: TourWaypoint[]): GlobeArc[] {
  if (waypoints.length < 2) return [];
  const arcs: GlobeArc[] = [];
  for (let i = 0; i < waypoints.length - 1; i += 1) {
    const a = waypoints[i];
    const b = waypoints[i + 1];
    arcs.push({
      start_lat: a.lat,
      start_lng: a.lng,
      end_lat: b.lat,
      end_lng: b.lng,
      color: "rgba(251,191,36,0.62)",
    });
  }
  return arcs;
}

function clusterBloomRadius(m: GlobeMarker, altitude: number): number {
  if (m.status === "ghost") return 0.28;
  let radius = m.point_radius ?? 0.42;
  if (m.is_cluster && altitude >= 1.2) {
    const boost = Math.min(1.5, 0.12 + (m.cluster_count || 0) * 0.035);
    radius = Math.min(1.55, radius + boost * (altitude >= 1.35 ? 1.15 : 0.85));
  }
  return radius;
}

function featureEnabled(key: string): boolean {
  const payload = payloadRef as GlobePayload & { features?: Record<string, boolean> };
  const features = payload?.features;
  if (features && Object.prototype.hasOwnProperty.call(features, key)) {
    return Boolean(features[key]);
  }
  return true;
}

function largestClusterTarget(): GlobeMarker | null {
  const clusters = allMarkers.filter((m) => m.is_cluster && (m.cluster_count || 0) > 0);
  if (clusters.length) {
    return clusters.reduce((best, m) =>
      (m.cluster_count || 0) > (best.cluster_count || 0) ? m : best
    );
  }
  if (!allMarkers.length) return null;
  let latSum = 0;
  let lngSum = 0;
  allMarkers.forEach((m) => {
    latSum += m.lat;
    lngSum += m.lng;
  });
  return {
    lat: latSum / allMarkers.length,
    lng: lngSum / allMarkers.length,
    status: "active",
    color: "#818cf8",
    ring_color: "#6366f1",
    label: "Fleet",
    region: "",
  };
}

function defaultCamera(): GlobeCamera {
  const cam = payloadRef?.camera || {};
  return {
    lat: cam.lat ?? DEFAULT_CAMERA.lat,
    lng: cam.lng ?? DEFAULT_CAMERA.lng,
    altitude: cam.altitude ?? DEFAULT_CAMERA.altitude,
  };
}

function maybeFirstVisitFlyIn(): void {
  if (hashViewApplied || firstVisitHandled || prefersReducedMotion() || !featureEnabled("first_visit_fly_in")) return;
  try {
    if (sessionStorage.getItem(FIRST_VISIT_KEY)) {
      firstVisitHandled = true;
      return;
    }
  } catch {
    return;
  }
  if (!globeInstance) return;
  firstVisitHandled = true;
  try {
    sessionStorage.setItem(FIRST_VISIT_KEY, "1");
  } catch {
    /* ignore */
  }
  const cam = defaultCamera();
  globeInstance.pointOfView(
    { lat: cam.lat ?? DEFAULT_CAMERA.lat, lng: cam.lng ?? DEFAULT_CAMERA.lng, altitude: 2.35 },
    0
  );
  window.setTimeout(() => {
    api.flyTo({
      lat: cam.lat ?? DEFAULT_CAMERA.lat,
      lng: cam.lng ?? DEFAULT_CAMERA.lng,
      altitude: cam.altitude ?? FILL_ALTITUDE,
      ms: prefersReducedMotion() ? 0 : 2200,
    });
  }, prefersReducedMotion() ? 0 : 700);
}

function syncWowMarkers(): void {
  if (!globeInstance) return;
  const base = applyMarkerFilters();
  const alt = api.getAltitude();
  const showGhosts = wowModeEnabled && alt >= 1.35 && expansionTargets.length;
  const merged = showGhosts ? base.concat(expansionTargets) : base;
  globeInstance
    .pointsData(merged)
    .pointColor((d: object) => {
      const m = d as GlobeMarker;
      if (m.status === "ghost") return m.color || "rgba(148,163,184,0.5)";
      if (regionHighlight && m.region !== regionHighlight) {
        return "rgba(148,163,184,0.38)";
      }
      if (m.is_cluster && alt >= 1.25 && featureEnabled("cluster_bloom")) {
        return m.color || "rgba(129,140,248,0.92)";
      }
      return m.color;
    })
    .pointRadius((d: object) => clusterBloomRadius(d as GlobeMarker, alt));
  syncPulseRings();
}

function dispatchMarkerOpen(container: HTMLElement, marker: GlobeMarker): void {
  container.dispatchEvent(
    new CustomEvent("rmc:globe-marker-open", {
      bubbles: true,
      detail: { marker },
    })
  );
}

function initGlobe(container: HTMLElement, payload: GlobePayload): GlobeInstance | null {
  if (!(window as Window & { WebGLRenderingContext?: unknown }).WebGLRenderingContext) {
    showFallback(container);
    return null;
  }

  payloadRef = payload;
  allMarkers = payload.markers || [];
  tourWaypoints = payload.tour_waypoints || [];
  expansionTargets = payload.expansion_targets || [];
  baseArcs = payload.arcs || [];
  const theme = payload.theme || ({} as GlobeTheme);

  const globe = Globe()(container)
    .backgroundColor("rgba(0,0,0,0)")
    .showGlobe(true)
    .showAtmosphere(true)
    .atmosphereColor(theme.atmosphere || "rgba(99,102,241,0.35)")
    .atmosphereAltitude(0.12)
    .pointsData(applyMarkerFilters())
    .pointLat("lat")
    .pointLng("lng")
    .pointColor((d: object) => {
      const m = d as GlobeMarker;
      if (regionHighlight && m.region !== regionHighlight) {
        return "rgba(148,163,184,0.38)";
      }
      return m.color;
    })
    .pointAltitude(0.025)
    .pointRadius((d: object) => (d as GlobeMarker).point_radius ?? 0.42)
    .pointLabel((d: object) => {
      const m = d as GlobeMarker;
      if (m.is_cluster) {
        return `<div class="lx-world__globe-tip"><strong>${m.cluster_count || 0} schools</strong><span>${m.region || ""}</span></div>`;
      }
      const place = markerPlaceLabel(m);
      const meta = markerTooltipMeta(m);
      const title = m.name || m.label;
      const metaLine = meta ? `<span class="lx-world__globe-tip-meta">${meta}</span>` : "";
      return `<div class="lx-world__globe-tip"><strong>${title}</strong><span>${place}</span>${metaLine}</div>`;
    })
    .onPointClick((d: object | null) => {
      if (!d) return;
      const m = d as GlobeMarker;
      if (m.is_cluster) {
        dispatchMarkerOpen(container, m);
        api.flyTo({ lat: m.lat, lng: m.lng, altitude: FILL_ALTITUDE, ms: 900 });
        return;
      }
      container.dispatchEvent(
        new CustomEvent("rmc:globe-marker-click", {
          bubbles: true,
          detail: {
            status: m.status,
            region: m.region,
            country_code: m.country_code || "",
            school_id: m.school_id || "",
            name: m.name || "",
            slug: m.slug || "",
          },
        })
      );
      dispatchMarkerOpen(container, m);
    });

  const material = globe.globeMaterial();
  const textureUrl = payload.globe_texture_url;
  if (textureUrl) {
    const probe = new Image();
    probe.onerror = () => showFallback(container);
    probe.src = textureUrl;
    globe.globeImageUrl(textureUrl);
    material.color.set("#ffffff");
    material.emissive.set("#0a0e22");
    material.emissiveIntensity = 0.12;
    material.shininess = 0.18;
  } else {
    material.color.set(theme.globeColor || "#0f1530");
    material.emissive.set(theme.globeEmissive || "#1e1b4b");
    material.emissiveIntensity = 0.28;
    material.shininess = 0.42;
  }

  const camera = payload.camera || {};
  hashViewApplied = applyGlobeHashIfPresent(globe);
  if (!hashViewApplied) {
    globe.pointOfView({
      lat: camera.lat ?? DEFAULT_CAMERA.lat,
      lng: camera.lng ?? DEFAULT_CAMERA.lng,
      altitude: camera.altitude ?? FILL_ALTITUDE,
    });
  }

  const controls = globe.controls();
  controls.enableZoom = true;
  controls.autoRotate = Boolean(payload.auto_rotate) && !prefersReducedMotion();
  controls.autoRotateSpeed = payload.auto_rotate_speed ?? 0.35;

  bindArcs(globe, baseArcs);
  bindMapLabels(globe, payload);
  syncPulseRings();

  const geoUrl = payload.geo_url;
  if (geoUrl) {
    fetch(geoUrl, { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .then((geo) => {
        if (!geo) return;
        const features = geo.features || geo;
        const enriched = enrichPolygonFeatures(features as object[], payload.iso3_region_map || {});
        polygonFeatures = enriched;
        globe
          .polygonsData(enriched)
          .polygonCapColor(polygonCapColor)
          .polygonSideColor(() => theme.polygonSide || "rgba(99,102,241,0.14)")
          .polygonStrokeColor(() => theme.polygonStroke || "rgba(148,163,184,0.22)")
          .polygonAltitude(0.006);
      })
      .catch(() => {
        /* polygons optional */
      });
  }

  const resize = () => {
    globe.width(container.clientWidth);
    globe.height(container.clientHeight);
  };
  resize();
  window.addEventListener("resize", resize);
  resizeHandler = resize;

  container.dataset.rmcWorldGlobeInited = "1";
  container.classList.add("lx-world__globe--webgl-ready");
  const stage = getGlobeStage(container);
  stage.classList.add("lx-world__globe--webgl-ready");
  stage.classList.remove("lx-world__globe--offline", "lx-world__globe--fallback");
  stage.removeAttribute("data-rmc-globe-mode");
  hideSkeleton(container);
  globeInstance = globe;
  return globe;
}

const api: RMCWorldGlobeApi = {
  flyTo(opts) {
    if (!globeInstance) return;
    const controls = globeInstance.controls();
    controls.autoRotate = false;
    globeInstance.pointOfView(
      { lat: opts.lat, lng: opts.lng, altitude: opts.altitude ?? FILL_ALTITUDE },
      prefersReducedMotion() ? 0 : opts.ms ?? 1200
    );
    window.setTimeout(() => syncMapLabels(), prefersReducedMotion() ? 0 : (opts.ms ?? 1200) + 50);
  },
  flyToRegion(region, ms) {
    if (!region) return;
    const centroids = payloadRef?.region_centroids || {};
    const c = centroids[region];
    if (!c) return;
    api.flyTo({ lat: c.lat ?? 0, lng: c.lng ?? 0, altitude: FILL_ALTITUDE, ms });
    api.highlightRegion(region);
  },
  highlightRegion(region) {
    regionHighlight = region;
    syncGlobePoints();
    syncPolygonHighlight();
    const root = document.querySelector(".lx-world");
    if (root) {
      root.querySelectorAll("[data-rmc-region]").forEach((el) => {
        el.classList.toggle("lx-world__legend-row--active", region !== null && el.getAttribute("data-rmc-region") === region);
      });
    }
  },
  setStatusFilter(status) {
    statusFilter = status;
    syncGlobePoints();
    document.querySelectorAll("[data-rmc-status-filter]").forEach((el) => {
      const val = el.getAttribute("data-rmc-status-filter");
      el.classList.toggle("lx-world__status-chip--active", status !== null && val === status);
      el.setAttribute("aria-pressed", status !== null && val === status ? "true" : "false");
    });
  },
  setRegionFilter(region) {
    regionFilter = region;
    syncGlobePoints();
  },
  getMarkers() {
    return allMarkers.slice();
  },
  getVisibleMarkers() {
    return visibleMarkers.slice();
  },
  async refreshLive(params) {
    if (liveRefreshInFlight) return null;
    liveRefreshInFlight = true;
    try {
      const data = await fetchLiveBundle(params as Record<string, string> | undefined);
      if (!data) return null;
      applyLiveBundle(data, { force: Boolean(params?.force) || params?.force === "1" });
      return data;
    } finally {
      liveRefreshInFlight = false;
    }
  },
  async refreshMarkers(params) {
    await api.refreshLive(params);
  },
  startTour() {
    api.stopTour();
    if (!tourWaypoints.length || prefersReducedMotion()) return;
    if (globeInstance) {
      bindArcs(globeInstance, buildGoldenTourArcs(tourWaypoints), true);
    }
    const step = () => {
      const wp = tourWaypoints[tourIndex % tourWaypoints.length];
      const stepIndex = tourIndex % tourWaypoints.length;
      tourIndex += 1;
      api.flyTo({
        lat: wp.lat,
        lng: wp.lng,
        altitude: wp.altitude ?? FILL_ALTITUDE,
        ms: 1400,
      });
      const caption = document.getElementById("rmc-world-globe-tour-caption");
      const voidCaption = document.getElementById("rmc-world-globe-void-caption-text");
      const text = wp.caption || (wp.label ? `Tour · ${wp.label}` : "");
      if (caption && text) caption.textContent = text;
      if (voidCaption && text) voidCaption.textContent = text;
      document.dispatchEvent(
        new CustomEvent("rmc:globe-tour-step", {
          detail: {
            waypoint: wp,
            step_index: stepIndex,
            label: wp.label || "",
            region: wp.label || "",
            lat: wp.lat,
            lng: wp.lng,
          },
        })
      );
      tourTimer = window.setTimeout(step, wp.dwell_ms ?? 3200);
    };
    step();
  },
  stopTour() {
    if (tourTimer) window.clearTimeout(tourTimer);
    tourTimer = null;
    if (globeInstance) {
      bindArcs(globeInstance, wowModeEnabled ? baseArcs : []);
    }
  },
  resetView() {
    api.stopTour();
    regionHighlight = null;
    regionFilter = null;
    statusFilter = null;
    syncGlobePoints();
    syncPolygonHighlight();
    document.querySelectorAll("[data-rmc-status-filter]").forEach((el) => {
      el.classList.remove("lx-world__status-chip--active");
      el.setAttribute("aria-pressed", "false");
    });
    document.querySelectorAll(".lx-world [data-rmc-region]").forEach((el) => {
      el.classList.remove("lx-world__legend-row--active");
    });
    const caption = document.getElementById("rmc-world-globe-tour-caption");
    if (caption) caption.textContent = "";
    if (!globeInstance || !payloadRef) return;
    const cam = defaultCamera();
    const controls = globeInstance.controls();
    controls.autoRotate = Boolean(payloadRef.auto_rotate) && !prefersReducedMotion();
    api.flyTo({
      lat: cam.lat ?? DEFAULT_CAMERA.lat,
      lng: cam.lng ?? DEFAULT_CAMERA.lng,
      altitude: cam.altitude ?? FILL_ALTITUDE,
      ms: prefersReducedMotion() ? 0 : 1200,
    });
    window.setTimeout(() => syncMapLabels(), prefersReducedMotion() ? 0 : 1250);
  },
  isReady() {
    return globeInstance !== null;
  },
  getAltitude() {
    if (!globeInstance) return FILL_ALTITUDE;
    const pov = globeInstance.pointOfView();
    return typeof pov.altitude === "number" ? pov.altitude : FILL_ALTITUDE;
  },
  getPointOfView() {
    const cam = defaultCamera();
    if (!globeInstance) {
      return { lat: cam.lat ?? DEFAULT_CAMERA.lat, lng: cam.lng ?? DEFAULT_CAMERA.lng, altitude: cam.altitude ?? FILL_ALTITUDE };
    }
    const pov = globeInstance.pointOfView();
    return {
      lat: typeof pov.lat === "number" ? pov.lat : DEFAULT_CAMERA.lat,
      lng: typeof pov.lng === "number" ? pov.lng : DEFAULT_CAMERA.lng,
      altitude: typeof pov.altitude === "number" ? pov.altitude : FILL_ALTITUDE,
    };
  },
  setWowMode(enabled) {
    wowModeEnabled = Boolean(enabled);
    if (!globeInstance) return;
    const controls = globeInstance.controls();
    controls.autoRotate = wowModeEnabled && Boolean(payloadRef?.auto_rotate) && !prefersReducedMotion();
    syncArcLayer();
    syncWowMarkers();
  },
  setConstellationMode(enabled) {
    constellationModeEnabled = Boolean(enabled);
    syncArcLayer();
  },
};

function isSvgOfflineLocked(container: HTMLElement): boolean {
  const stage = getGlobeStage(container);
  return (
    stage.getAttribute("data-rmc-globe-mode") === "svg-offline" ||
    stage.classList.contains("lx-world__globe--offline")
  );
}

function boot(): void {
  const container = document.getElementById("rmc-world-globe");
  if (!container || container.dataset.rmcWorldGlobeInited === "1") return;

  if (isSvgOfflineLocked(container)) {
    showFallback(container);
    return;
  }

  const payload = readPayload();
  if (!payload) {
    showFallback(container);
    return;
  }

  try {
    const instance = initGlobe(container, payload);
    window.RMCWorldGlobe = api;
    if (!instance) {
      return;
    }
    void api.refreshLive({ force: "1" });
    document.dispatchEvent(new CustomEvent("rmc:globe-ready"));
  } catch {
    showFallback(container);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}

export function mountWorldGlobes(): void {
  boot();
}

export type { RMCWorldGlobeApi, GlobeMarker };
