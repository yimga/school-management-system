import { useEffect, useState } from "react";

export type NetworkPhase = "online" | "offline" | "reconnecting";

function readInitialPhase(): NetworkPhase {
  if (typeof navigator === "undefined") return "online";
  return navigator.onLine ? "online" : "offline";
}

export interface NetworkStatusChannelProps {
  onChange?: (phase: NetworkPhase) => void;
}

export function NetworkStatusChannel({ onChange }: NetworkStatusChannelProps) {
  const [phase, setPhase] = useState<NetworkPhase>(readInitialPhase);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const onUp = () => {
      setPhase("reconnecting");
      onChange?.("reconnecting");
      const id = window.setTimeout(() => {
        setPhase("online");
        onChange?.("online");
      }, 600);
      return () => window.clearTimeout(id);
    };
    const onDown = () => {
      setPhase("offline");
      onChange?.("offline");
    };
    window.addEventListener("online", onUp);
    window.addEventListener("offline", onDown);
    return () => {
      window.removeEventListener("online", onUp);
      window.removeEventListener("offline", onDown);
    };
  }, [onChange]);

  if (phase === "online") return null;

  return (
    <div
      className={`rmc-lux-netstatus rmc-lux-netstatus--${phase}`}
      role="status"
      aria-live="polite"
    >
      <span className="rmc-lux-netstatus__pip" aria-hidden="true" />
      <span className="rmc-lux-netstatus__label">
        {phase === "offline"
          ? "Offline — changes will sync when network returns."
          : "Reconnecting…"}
      </span>
    </div>
  );
}
