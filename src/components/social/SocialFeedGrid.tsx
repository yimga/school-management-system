import { useEffect, useState } from "react";
import type { SocialFeedItem, SocialFeedResponse } from "./types";

export interface SocialFeedGridProps {
  feedUrl: string;
  loading?: boolean;
  columns?: 2 | 3 | 4;
  emptyLabel?: string;
}

function FeedSkeleton({ columns }: { columns: number }) {
  return (
    <div
      className={`rmc-social-feed-grid rmc-social-feed-grid--cols-${columns}`}
      aria-busy="true"
      aria-label="Loading social feed"
    >
      {Array.from({ length: columns * 2 }).map((_, i) => (
        <div key={i} className="rmc-social-feed-card rmc-skeleton" />
      ))}
    </div>
  );
}

export function SocialFeedGrid({
  feedUrl,
  loading: loadingProp,
  columns = 3,
  emptyLabel = "No social posts yet.",
}: SocialFeedGridProps) {
  const [data, setData] = useState<SocialFeedResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(loadingProp ?? true);

  useEffect(() => {
    if (loadingProp) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(feedUrl, { credentials: "same-origin" });
        if (!res.ok) {
          throw new Error(`feed_${res.status}`);
        }
        const json = (await res.json()) as SocialFeedResponse;
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setError("unavailable");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [feedUrl, loadingProp]);

  if (loading || loadingProp) {
    return <FeedSkeleton columns={columns} />;
  }

  if (error) {
    return (
      <div className="rmc-social-feed-grid rmc-card p-3" role="status">
        <p className="mb-0 text-secondary">{emptyLabel}</p>
      </div>
    );
  }

  const items = data?.items ?? [];
  if (!items.length) {
    return (
      <div className="rmc-social-feed-grid rmc-card p-3" role="status">
        <p className="mb-0 text-secondary">{emptyLabel}</p>
      </div>
    );
  }

  return (
    <div
      className={`rmc-social-feed-grid rmc-social-feed-grid--cols-${columns}`}
      aria-label="Social feed"
    >
      {items.map((item: SocialFeedItem) => (
        <article
          key={item.id || item.url || item.text}
          className="rmc-social-feed-card rmc-card"
        >
          {item.image_url ? (
            <img
              src={item.image_url}
              alt=""
              loading="lazy"
              decoding="async"
              className="rmc-social-feed-card__image"
            />
          ) : null}
          <div className="rmc-social-feed-card__body">
            {item.provider ? (
              <span className="rmc-social-feed-card__provider">{item.provider}</span>
            ) : null}
            <p className="rmc-social-feed-card__text">{item.text}</p>
          </div>
        </article>
      ))}
    </div>
  );
}
