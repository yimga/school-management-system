import { useCallback, useEffect, useState } from "react";
import type { ModerationItem } from "./types";

export interface SocialModerationQueueProps {
  listUrl: string;
  actionUrlBase: string;
}

export function SocialModerationQueue({ listUrl, actionUrlBase }: SocialModerationQueueProps) {
  const [items, setItems] = useState<ModerationItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(listUrl, { credentials: "same-origin" });
      if (res.ok) {
        const json = (await res.json()) as { items: ModerationItem[] };
        setItems(json.items || []);
      }
    } finally {
      setLoading(false);
    }
  }, [listUrl]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (id: string, action: "approve" | "reject") => {
    const res = await fetch(`${actionUrlBase}${id}/`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    if (res.ok) {
      setItems((prev) => prev.filter((row) => row.id !== id));
    }
  };

  if (loading) {
    return (
      <div className="rmc-social-moderation rmc-social-moderation--loading" aria-busy="true">
        <div className="rmc-skeleton rmc-social-moderation__tile" />
        <div className="rmc-skeleton rmc-social-moderation__tile" />
      </div>
    );
  }

  if (!items.length) {
    return (
      <p className="rmc-social-moderation__empty text-secondary" role="status">
        No moments awaiting approval.
      </p>
    );
  }

  return (
    <div className="rmc-social-moderation" aria-label="Proud campus moderation queue">
      {items.map((item) => (
        <figure key={item.id} className="rmc-social-moderation__tile rmc-card">
          <img src={item.image_url} alt="" className="rmc-social-moderation__image" loading="lazy" />
          <figcaption className="rmc-social-moderation__caption">
            {item.caption || item.hashtag}
          </figcaption>
          <div className="rmc-social-moderation__actions">
            <button type="button" className="btn btn-sm btn-primary" onClick={() => act(item.id, "approve")}>
              Approve
            </button>
            <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => act(item.id, "reject")}>
              Reject
            </button>
          </div>
        </figure>
      ))}
    </div>
  );
}
