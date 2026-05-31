import React, { useEffect, useMemo, useRef, useState } from "react";

export interface TOCSection {
  id: string;
  label: string;
  depth?: 1 | 2;
}

export interface SectionTOCProps {
  sections?: TOCSection[];
  autoDiscover?: boolean;
  containerSelector?: string;
  className?: string;
  stickyOffsetPx?: number;
  showProgress?: boolean;
}

function discoverSections(container: HTMLElement): TOCSection[] {
  const out: TOCSection[] = [];
  const heads = container.querySelectorAll<HTMLElement>(
    "section[id][data-rmc-toc], h2[id][data-rmc-toc], h3[id][data-rmc-toc]",
  );
  heads.forEach((el) => {
    const id = el.id;
    if (!id) return;
    const label =
      el.getAttribute("data-rmc-toc-label") ??
      (el.tagName === "SECTION"
        ? (el.querySelector("h2, h3")?.textContent ?? id).trim()
        : (el.textContent ?? id).trim());
    const depth = el.tagName === "H3" ? 2 : 1;
    out.push({ id, label, depth });
  });
  return out;
}

export function SectionTOC({
  sections,
  autoDiscover = true,
  containerSelector,
  className = "",
  stickyOffsetPx = 88,
  showProgress = true,
}: SectionTOCProps) {
  const [discovered, setDiscovered] = useState<TOCSection[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [progressPct, setProgressPct] = useState(0);
  const rootRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!autoDiscover) return;
    const target = containerSelector
      ? document.querySelector<HTMLElement>(containerSelector)
      : document.body;
    if (!target) return;
    const observer = new MutationObserver(() => setDiscovered(discoverSections(target)));
    observer.observe(target, { childList: true, subtree: true });
    setDiscovered(discoverSections(target));
    return () => observer.disconnect();
  }, [autoDiscover, containerSelector]);

  const resolved = sections ?? discovered;

  useEffect(() => {
    if (resolved.length === 0) return;
    const els = resolved
      .map((s) => document.getElementById(s.id))
      .filter((el): el is HTMLElement => el !== null);
    if (els.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) setActiveId(visible[0].target.id);
      },
      { rootMargin: `-${stickyOffsetPx}px 0px -60% 0px`, threshold: [0, 1] },
    );
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [resolved, stickyOffsetPx]);

  useEffect(() => {
    if (!showProgress || typeof window === "undefined") return;
    const onScroll = () => {
      const doc = document.documentElement;
      const max = doc.scrollHeight - doc.clientHeight;
      const pct = max > 0 ? Math.min(100, Math.max(0, (window.scrollY / max) * 100)) : 0;
      setProgressPct(Math.round(pct));
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, [showProgress]);

  if (resolved.length < 2) return null;

  return (
    <aside
      ref={rootRef as React.RefObject<HTMLElement>}
      className={`rmc-lux-toc ${className}`.trim()}
      style={{ top: stickyOffsetPx }}
      aria-label="On-this-page navigation"
    >
      {showProgress ? (
        <div
          className="rmc-lux-toc__progress"
          role="progressbar"
          aria-valuenow={progressPct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <span
            className="rmc-lux-toc__progress-bar"
            style={{ height: `${progressPct}%` }}
            aria-hidden="true"
          />
        </div>
      ) : null}
      <h6 className="rmc-lux-toc__title">On this page</h6>
      <ol className="rmc-lux-toc__list">
        {resolved.map((section) => (
          <li
            key={section.id}
            className={
              "rmc-lux-toc__item" +
              (section.depth === 2 ? " is-sub" : "") +
              (section.id === activeId ? " is-active" : "")
            }
          >
            <a href={`#${section.id}`} className="rmc-lux-toc__link">
              {section.label}
            </a>
          </li>
        ))}
      </ol>
    </aside>
  );
}

export interface ScrollProgressBarProps {
  className?: string;
  height?: number;
}

export function ScrollProgressBar({ className = "", height = 2 }: ScrollProgressBarProps) {
  const [pct, setPct] = useState(0);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onScroll = () => {
      const doc = document.documentElement;
      const max = doc.scrollHeight - doc.clientHeight;
      setPct(max > 0 ? Math.min(100, (window.scrollY / max) * 100) : 0);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <div
      className={`rmc-lux-scroll-progress ${className}`.trim()}
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Page scroll progress"
    >
      <span
        className="rmc-lux-scroll-progress__bar"
        style={{ width: `${pct}%` }}
        aria-hidden="true"
      />
    </div>
  );
}
