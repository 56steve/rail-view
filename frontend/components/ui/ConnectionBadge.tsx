"use client";

import { useRailPulseStore } from "@/lib/store";

const CONFIG = {
  live: { label: "Live", dot: "bg-emerald-400", pulse: false },
  connecting: { label: "Connecting", dot: "bg-white/40", pulse: true },
  reconnecting: { label: "Reconnecting", dot: "bg-amber-400", pulse: true },
} as const;

export function ConnectionBadge() {
  const status = useRailPulseStore((state) => state.connectionStatus);
  const config = CONFIG[status];

  return (
    <div className="pointer-events-auto flex items-center gap-1.5 rounded-full border border-white/10 bg-[#12151bcc] px-3 py-1.5 text-xs font-medium text-white/70 backdrop-blur-xl">
      <span className={`h-1.5 w-1.5 rounded-full ${config.dot} ${config.pulse ? "animate-pulse" : ""}`} />
      {config.label}
    </div>
  );
}
