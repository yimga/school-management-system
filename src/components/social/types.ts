export type SocialFeedScope = "platform" | "tenant";

export interface SocialFeedItem {
  id: string;
  text?: string;
  url?: string;
  image_url?: string;
  provider?: string;
  handle?: string;
  published_at?: string;
}

export interface SocialFeedResponse {
  scope: SocialFeedScope;
  school_id: string | null;
  items: SocialFeedItem[];
}

export interface ModerationItem {
  id: string;
  caption: string;
  image_url: string;
  hashtag: string;
  created_at: string;
}
