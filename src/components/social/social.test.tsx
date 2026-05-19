import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { SocialFeedGrid } from "./SocialFeedGrid";
import { SocialModerationQueue } from "./SocialModerationQueue";

describe("SocialFeedGrid", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          scope: "tenant",
          school_id: "00000000-0000-0000-0000-000000000001",
          items: [{ id: "1", text: "Welcome back", provider: "x" }],
        }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders skeleton then feed items", async () => {
    render(<SocialFeedGrid feedUrl="/api/v1/social/feed/" />);
    expect(screen.getByLabelText(/loading social feed/i)).toBeInTheDocument();
    expect(await screen.findByText("Welcome back")).toBeInTheDocument();
  });
});

describe("SocialModerationQueue", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "a",
              caption: "Spirit day",
              image_url: "https://example.com/a.jpg",
              hashtag: "#spirit",
              created_at: "2026-05-19T00:00:00Z",
            },
          ],
        }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists pending moderation tiles", async () => {
    render(
      <SocialModerationQueue
        listUrl="/api/v1/social/moderation/"
        actionUrlBase="/api/v1/social/moderation/"
      />,
    );
    expect(await screen.findByText("Spirit day")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
  });
});
