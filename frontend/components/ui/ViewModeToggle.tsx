"use client";

import { useRailPulseStore } from "@/lib/store";
import type { ViewMode } from "@/lib/types";

const OPTIONS: { mode: ViewMode; label: string }[] = [
  { mode: "network", label: "Network" },
  { mode: "journey", label: "Journey" },
];

export function ViewModeToggle() {
  const viewMode = useRailPulseStore((state) => state.viewMode);
  const setViewMode = useRailPulseStore((state) => state.setViewMode);

  return (
    <div className="pointer-events-auto flex items-center gap-0.5 rounded-full border border-white/10 bg-[#12151bcc] p-1 backdrop-blur-xl">
      {OPTIONS.map((option) => (
        <button
          key={option.mode}
          type="button"
          onClick={() => setViewMode(option.mode)}
          className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
            viewMode === option.mode
              ? "bg-white/12 text-white"
              : "text-white/50 hover:text-white/80"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
