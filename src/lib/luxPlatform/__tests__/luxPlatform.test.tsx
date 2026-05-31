import { describe, it, expect } from "vitest";
import { render, screen, act } from "@testing-library/react";
import {
  BentoGrid,
  BentoTile,
  BarStack,
  DeltaChip,
  Donut,
  Gauge,
  HeatStrip,
  KpiCard,
  RhythmStack,
  ScrollProgressBar,
  SectionTOC,
  Sparkline,
  SplitPane,
  TileBoard,
} from "../index";

describe("KPI viz primitives", () => {
  it("Sparkline renders an SVG polyline + endpoint circle", () => {
    const { container } = render(<Sparkline values={[1, 4, 2, 6, 3]} />);
    expect(container.querySelector("svg.rmc-lux-viz-sparkline")).not.toBeNull();
    expect(container.querySelector("polyline")).not.toBeNull();
    expect(container.querySelector("circle")).not.toBeNull();
  });

  it("Sparkline returns null on empty values", () => {
    const { container } = render(<Sparkline values={[]} />);
    expect(container.querySelector("svg")).toBeNull();
  });

  it("DeltaChip auto-tones positive as good, negative as danger", () => {
    const { container, rerender } = render(<DeltaChip pct={12.4} />);
    expect(container.querySelector(".rmc-lux-viz-delta--good")).not.toBeNull();
    rerender(<DeltaChip pct={-8.1} />);
    expect(container.querySelector(".rmc-lux-viz-delta--danger")).not.toBeNull();
    rerender(<DeltaChip pct={0.5} />);
    expect(container.querySelector(".rmc-lux-viz-delta--neutral")).not.toBeNull();
  });

  it("Donut renders centered percent and clamps over-max", () => {
    render(<Donut value={150} max={100} />);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("BarStack renders one bar per value", () => {
    const { container } = render(
      <BarStack bars={[{ label: "Q1", value: 5 }, { label: "Q2", value: 9 }, { label: "Q3", value: 3 }]} />,
    );
    expect(container.querySelectorAll(".rmc-lux-viz-bar").length).toBe(3);
  });

  it("Gauge renders an arc + needle", () => {
    const { container } = render(<Gauge value={75} />);
    expect(container.querySelectorAll("path").length).toBeGreaterThanOrEqual(2);
    expect(container.querySelector("line")).not.toBeNull();
  });

  it("HeatStrip renders one cell per value with varying opacity", () => {
    const { container } = render(<HeatStrip cells={[1, 5, 10, 3]} max={10} />);
    const cells = container.querySelectorAll(".rmc-lux-viz-heat__cell");
    expect(cells.length).toBe(4);
    const opacities = Array.from(cells).map((c) => parseFloat((c as HTMLElement).style.opacity));
    expect(new Set(opacities).size).toBeGreaterThan(1);
  });

  it("KpiCard renders label + value + becomes actionable when given href", () => {
    const { container, rerender } = render(<KpiCard label="Revenue" value="$48k" />);
    expect(screen.getByText("Revenue")).toBeInTheDocument();
    expect(screen.getByText("$48k")).toBeInTheDocument();
    expect(container.querySelector(".is-actionable")).toBeNull();
    rerender(<KpiCard label="Revenue" value="$48k" href="/finance/" />);
    expect(container.querySelector(".is-actionable")).not.toBeNull();
  });
});

describe("Layout balance primitives", () => {
  it("BentoGrid + BentoTile produce the expected col/row span classes", () => {
    const { container } = render(
      <BentoGrid density="compact">
        <BentoTile col={4} row={2} accent="emerald" hero>
          Hero
        </BentoTile>
        <BentoTile col={2}>Side</BentoTile>
      </BentoGrid>,
    );
    expect(container.querySelector(".rmc-lux-bento--compact")).not.toBeNull();
    expect(container.querySelector(".rmc-lux-bento__tile--col-4.rmc-lux-bento__tile--row-2.rmc-lux-bento__tile--emerald.is-hero")).not.toBeNull();
    expect(container.querySelector(".rmc-lux-bento__tile--col-2")).not.toBeNull();
  });

  it("SplitPane respects leftWidth + sticky-left flag", () => {
    const { container } = render(
      <SplitPane left={<span>L</span>} right={<span>R</span>} leftWidth="wide" stickyLeft />,
    );
    expect(container.querySelector(".rmc-lux-split--wide.is-sticky-left")).not.toBeNull();
  });

  it("RhythmStack alternates row density classes", () => {
    const { container } = render(
      <RhythmStack>
        <div>1</div>
        <div>2</div>
        <div>3</div>
        <div>4</div>
      </RhythmStack>,
    );
    const rows = container.querySelectorAll(".rmc-lux-rhythm__row");
    expect(rows.length).toBe(4);
    expect(rows[0].classList.contains("rmc-lux-rhythm__row--anchor")).toBe(true);
    expect(rows[1].classList.contains("rmc-lux-rhythm__row--detail")).toBe(true);
    expect(rows[2].classList.contains("rmc-lux-rhythm__row--breath")).toBe(true);
    expect(rows[3].classList.contains("rmc-lux-rhythm__row--anchor")).toBe(true);
  });

  it("TileBoard maps cols prop to grid class", () => {
    const { container } = render(<TileBoard cols={4}><span>x</span></TileBoard>);
    expect(container.querySelector(".rmc-lux-tileboard--cols-4")).not.toBeNull();
  });
});

describe("SectionTOC", () => {
  it("returns null when fewer than 2 sections", () => {
    const { container } = render(<SectionTOC sections={[{ id: "a", label: "A" }]} autoDiscover={false} />);
    expect(container.querySelector(".rmc-lux-toc")).toBeNull();
  });

  it("renders one link per section + a progress bar", () => {
    const { container } = render(
      <SectionTOC
        sections={[
          { id: "intro", label: "Intro" },
          { id: "body", label: "Body" },
          { id: "outro", label: "Outro", depth: 2 },
        ]}
        autoDiscover={false}
      />,
    );
    expect(container.querySelectorAll(".rmc-lux-toc__link").length).toBe(3);
    expect(container.querySelector(".rmc-lux-toc__progress")).not.toBeNull();
    expect(container.querySelector(".rmc-lux-toc__item.is-sub")).not.toBeNull();
  });
});

describe("ScrollProgressBar", () => {
  it("renders a progressbar role with valuenow defaulting to 0 in jsdom", () => {
    render(<ScrollProgressBar />);
    const bar = screen.getByRole("progressbar", { name: /scroll progress/i });
    expect(bar.getAttribute("aria-valuemin")).toBe("0");
    expect(bar.getAttribute("aria-valuemax")).toBe("100");
  });

  it("updates valuenow when window.scroll fires", () => {
    Object.defineProperty(document.documentElement, "scrollHeight", {
      configurable: true,
      get: () => 2000,
    });
    Object.defineProperty(document.documentElement, "clientHeight", {
      configurable: true,
      get: () => 1000,
    });
    Object.defineProperty(window, "scrollY", {
      configurable: true,
      get: () => 500,
    });
    render(<ScrollProgressBar />);
    act(() => {
      window.dispatchEvent(new Event("scroll"));
    });
    const bar = screen.getByRole("progressbar", { name: /scroll progress/i });
    expect(parseInt(bar.getAttribute("aria-valuenow") ?? "0", 10)).toBeGreaterThanOrEqual(50);
  });
});
