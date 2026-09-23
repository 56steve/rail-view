"use client";

import { useEffect, useState } from "react";
import type { CityManifest } from "@/lib/city";
import { useRailView } from "@/lib/store";
import { Logo } from "../ui/Logo";
import { PanelScreen } from "../ui/PanelScreen";
import { Card, SectionTitle } from "../ui/primitives";

export function MoreScreen() {
  const showBuildings = useRailView((s) => s.showBuildings);
  const showLabels = useRailView((s) => s.showLabels);
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
          <Toggle label="3D buildings" checked={showBuildings} onChange={(v) => useRailView.getState().setShowBuildings(v)} />
          <Toggle label="Station names" checked={showLabels} onChange={(v) => useRailView.getState().setShowLabels(v)} />
        </Card>
      </section>

      <section className="mt-6 flex flex-col gap-2.5">
        <SectionTitle>How live is this?</SectionTitle>
        <Card className="px-5 py-4 text-[13.5px] leading-relaxed text-fg-muted">
          Train movements are currently <span className="text-fg">simulated</span> on the real Western, Central,
          Harbour and Trans-Harbour tracks, and run through the same pipeline a live feed would: GPS positions are
          snapped onto the track, filtered, and compared against a timetable to work out delays. No authorised
          real-time feed for Mumbai locals is connected yet.
        </Card>
      </section>

      <section className="mt-6 flex flex-col gap-2.5">
        <SectionTitle>Data</SectionTitle>
        <Card className="px-5 py-4 text-[13.5px] leading-relaxed text-fg-muted">
          <p>Stations, track geometry, buildings and coastline: {attribution ?? "© OpenStreetMap contributors (ODbL)"}.</p>
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

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center justify-between px-5 py-3.5">
      <span className="text-[14.5px] text-fg">{label}</span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="peer sr-only" />
      <span className="relative h-6 w-10 rounded-full bg-ink-600 transition peer-checked:bg-primary after:absolute after:left-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:transition peer-checked:after:translate-x-4 peer-focus-visible:ring-2 peer-focus-visible:ring-primary/60" />
    </label>
  );
}
