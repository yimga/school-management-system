export function MetricKpiCardSkeleton() {
  return (
    <article className="rmc-viz-card" aria-busy="true" aria-label="Loading metric">
      <header className="rmc-viz-card__header">
        <div className="rmc-viz-skeleton" style={{ width: "40%", height: "0.75rem" }} />
        <div className="rmc-viz-skeleton" style={{ width: "1.75rem", height: "1.75rem" }} />
      </header>
      <div className="rmc-viz-skeleton rmc-viz-skeleton--kpi-value" />
      <footer style={{ display: "flex", gap: "0.75rem", marginTop: "0.75rem" }}>
        <div className="rmc-viz-skeleton rmc-viz-skeleton--sparkline" />
        <div className="rmc-viz-skeleton" style={{ width: "3rem", height: "1.25rem" }} />
      </footer>
    </article>
  );
}

export function PlatformPulseLineChartSkeleton() {
  return (
    <section className="rmc-viz-card" aria-busy="true" aria-label="Loading campus pulse chart">
      <header className="rmc-viz-card__header">
        <div className="rmc-viz-skeleton" style={{ width: "35%", height: "0.75rem" }} />
      </header>
      <div className="rmc-viz-skeleton rmc-viz-skeleton--chart" />
    </section>
  );
}

export function ResourceAllocationDonutSkeleton() {
  return (
    <section className="rmc-viz-card" aria-busy="true" aria-label="Loading allocation chart">
      <header className="rmc-viz-card__header">
        <div className="rmc-viz-skeleton" style={{ width: "45%", height: "0.75rem" }} />
      </header>
      <div className="rmc-viz-skeleton rmc-viz-skeleton--donut" />
    </section>
  );
}
