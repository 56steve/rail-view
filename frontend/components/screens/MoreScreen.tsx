"use client";

import { useEffect, useState } from "react";
import type { CityManifest } from "@/lib/city";
import { useRailView, type Appearance } from "@/lib/store";
import { Logo } from "../ui/Logo";
import { PanelScreen } from "../ui/PanelScreen";
import { Card, SectionTitle } from "../ui/primitives";

export function MoreScreen() {
  const showBuildings = useRailView((s) => s.showBuildings);
  const showLabels = useRailView((s) => s.showLabels);
  const appearance = useRailView((s) => s.appearance);
  const attribution = useRailView((s) => s.network?.attribution);
  const [buildingStats, setBuildingStats] = useState<CityManifest["stats"] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/city/manifest.json", { signal: controller.signal })
      .then((r) => (r.ok ? (r.json() as Promise<CityManifest>) : null))
      .then((m) => m && setBuildingStats(m.stats))
      .catch(() => {
        // Stats are informational only.
      });
    return () => controller.abort();
  }, []);

  return (
    <PanelScreen title="More">
      <Card className="flex flex-col gap-2 px-5 py-5">
        <Logo />
        <p className="text-[14px] leading-relaxed text-fg-muted">Mumbai in motion. See your train, before it arrives.</p>
      </Card>

      <section className="mt-6 flex flex-col gap-2.5">
        <SectionTitle>Map</SectionTitle>
        <Card className="divide-y divide-white/7">
          <AppearancePicker value={appearance} onChange={(v) => useRailView.getState().setAppearance(v)} />
          <Toggle label="3D buildings" checked={showBuildings} onChange={(v) => useRailView.getState().setShowBuildings(v)} />
          <Toggle label="Station names" checked={showLabels} onChange={(v) => useRailView.getState().setShowLabels(v)} />
        </Card>
      </section>

      <section className="mt-6 flex flex-col gap-2.5">
        <SectionTitle>How live is this?</SectionTitle>
        <Card className="px-5 py-4 text-[13.5px] leading-relaxed text-fg-muted">
          The trains on the map are the ones Central and Western Railway&apos;s{" "}
          <span className="text-fg">official timetable</span> has running right now, with their real numbers and
          rakes. Their exact positions and delays are <span className="text-fg">simulated</span> along the real
          tracks, through the same pipeline a live feed would use. No authorised real-time feed for Mumbai locals is
          connected yet.
        </Card>
      </section>

      <section className="mt-6 flex flex-col gap-2.5">
        <SectionTitle>Data</SectionTitle>
        <Card className="px-5 py-4 text-[13.5px] leading-relaxed text-fg-muted">
          <p>
            Stations, tracks, platforms, buildings, roads, land cover and coastline:{" "}
            {attribution ?? "© OpenStreetMap contributors (ODbL)"}.
          </p>
          {buildingStats && (
            <p className="mt-2">
              Building heights come from OpenStreetMap where tagged ({buildingStats.height_tagged.toLocaleString()} of{" "}
              {buildingStats.buildings.toLocaleString()}); the rest are estimated for display.
            </p>
          )}
        </Card>
      </section>
    </PanelScreen>
  );
}

const APPEARANCE_OPTIONS: { value: Appearance; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "day", label: "Day" },
  { value: "night", label: "Night" },
];

function AppearancePicker({ value, onChange }: { value: Appearance; onChange: (value: Appearance) => void }) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-3">
      <span className="flex flex-col">
        <span className="text-[14.5px] text-fg">Appearance</span>
        {value === "auto" && <span className="text-[12px] text-fg-subtle">Follows sunrise and sunset in Mumbai</span>}
      </span>
      <div role="radiogroup" aria-label="Map appearance" className="flex shrink-0 rounded-full bg-ink-700 p-0.5">
        {APPEARANCE_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={value === option.value}
            onClick={() => onChange(option.value)}
            className={`rounded-full px-3 py-1.5 text-[12.5px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 ${
              value === option.value ? "bg-primary text-white" : "text-fg-muted hover:text-fg"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center justify-between px-5 py-3.5">
      <span className="text-[14.5px] text-fg">{label}</span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="peer sr-only" />
      <span className="relative h-6 w-10 rounded-full bg-ink-600 transition peer-checked:bg-primary after:absolute after:left-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:transition peer-checked:after:translate-x-4 peer-focus-visible:ring-2 peer-focus-visible:ring-primary/60" />
    </label>
  );
}
