"use client";

import { Bookmark, Compass, Ellipsis, TrainFront } from "lucide-react";
import { openTab } from "@/lib/navigation";
import { currentScreen, useRailView, type TabName } from "@/lib/store";

const TABS: { tab: TabName; label: string; Icon: typeof Compass }[] = [
  { tab: "explore", label: "Explore", Icon: Compass },
  { tab: "trains", label: "Trains", Icon: TrainFront },
  { tab: "saved", label: "Saved", Icon: Bookmark },
  { tab: "more", label: "More", Icon: Ellipsis },
];

export function TabBar() {
  const active = useRailView((s) => currentScreen(s).name);

  return (
    <nav
      aria-label="Primary"
      className="pointer-events-auto glass pb-safe grid grid-cols-4 border-x-0 border-b-0 pt-2 md:rounded-2xl md:border md:pb-2"
    >
      {TABS.map(({ tab, label, Icon }) => {
        const selected = active === tab;
        return (
          <button
            key={tab}
            type="button"
            onClick={() => openTab(tab)}
            aria-current={selected ? "page" : undefined}
            className={`flex flex-col items-center gap-1 py-1 text-[11px] font-medium transition ${
              selected ? "text-primary" : "text-fg-subtle hover:text-fg-muted"
            }`}
          >
            <Icon className="h-[22px] w-[22px]" strokeWidth={selected ? 2.2 : 1.8} />
            {label}
          </button>
        );
      })}
    </nav>
  );
}
