"use client";

import { useRailView } from "@/lib/store";

export function LineChips({ className = "" }: { className?: string }) {
  const lines = useRailView((s) => s.lines);
  const lineFilter = useRailView((s) => s.lineFilter);
  const setLineFilter = useRailView((s) => s.setLineFilter);

  const chip = (selected: boolean) =>
    `flex shrink-0 items-center gap-1.5 rounded-full px-4 py-2 text-[13px] font-medium transition active:scale-95 ${
      selected ? "bg-primary text-white shadow-[0_6px_20px_-8px_rgb(76_125_255/0.8)]" : "glass text-fg-muted hover:text-fg"
    }`;

  return (
    <div className={`pointer-events-auto scrollbar-none flex gap-2 overflow-x-auto ${className}`}>
      <button type="button" className={chip(lineFilter === null)} onClick={() => setLineFilter(null)}>
        All Lines
      </button>
      {Object.values(lines).map((line) => (
        <button
          key={line.code}
          type="button"
          className={chip(lineFilter === line.code)}
          onClick={() => setLineFilter(lineFilter === line.code ? null : line.code)}
        >
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: line.color_hex }} />
          {line.name}
        </button>
      ))}
    </div>
  );
}
