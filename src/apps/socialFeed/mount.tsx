import { createRoot } from "react-dom/client";
import { SocialFeedGrid } from "../../components/social/SocialFeedGrid";
import { SocialModerationQueue } from "../../components/social/SocialModerationQueue";

function readAttr(el: HTMLElement, name: string, fallback = ""): string {
  return (el.getAttribute(name) || fallback).trim();
}

export function mountSocialFeedSurfaces(): void {
  document.querySelectorAll<HTMLElement>("[data-rmc-social-feed]").forEach((el) => {
    const feedUrl = readAttr(el, "data-feed-url", "/api/v1/social/feed/");
    const columns = Number(readAttr(el, "data-columns", "3"));
    const cols = columns === 2 || columns === 4 ? columns : 3;
    createRoot(el).render(<SocialFeedGrid feedUrl={feedUrl} columns={cols} />);
  });

  document.querySelectorAll<HTMLElement>("[data-rmc-social-moderation]").forEach((el) => {
    const listUrl = readAttr(el, "data-list-url", "/api/v1/social/moderation/");
    const actionBase = readAttr(el, "data-action-url-base", "/api/v1/social/moderation/");
    createRoot(el).render(
      <SocialModerationQueue listUrl={listUrl} actionUrlBase={actionBase} />,
    );
  });
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountSocialFeedSurfaces);
  } else {
    mountSocialFeedSurfaces();
  }
}
