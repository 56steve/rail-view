"use client";

import { useMemo } from "react";
import { latLonToScene } from "@/lib/geo";
import { routeSpans } from "@/lib/network";
import type { JourneySegment } from "@/lib/journey";
import { useRailView } from "@/lib/store";
import type { StationIndexEntry } from "@/lib/types";

const ASPECT = 2; // width : height of the map card
const APPROX_WIDTH_PX = 380;

/** Flat, north-up overview of the journey: every line faintly, the
 * direct stretch highlighted, and the live position of each offered train. */
export function JourneyMiniMap({
  from,
  to,
  segment,
  trainIds,
}: {
  from: StationIndexEntry;
  to: StationIndexEntry;
  segment: JourneySegment | null;
  trainIds: string[];
}) {
  const lines = useRailView((s) => s.lines);
  const tracks = useRailView((s) => s.tracks);
  const trainPairs = useRailView((s) => s.trainPairs);
  const routes = useRailView((s) => s.routes);
  const spans = useMemo(() => routeSpans(routes, tracks), [routes, tracks]);

  const a = useMemo(() => latLonToScene(from.lat, from.lon), [from]);
  const b = useMemo(() => latLonToScene(to.lat, to.lon), [to]);

  const box = useMemo(() => {
    const pts = segment?.points.length ? segment.points : [a, b];
    let minX = Math.min(...pts.map((p) => p.x));
    let maxX = Math.max(...pts.map((p) => p.x));
    let minZ = Math.min(...pts.map((p) => p.z));
    let maxZ = Math.max(...pts.map((p) => p.z));
    const pad = Math.max(maxX - minX, maxZ - minZ) * 0.22 + 900;
    minX -= pad;
    maxX += pad;
    minZ -= pad;
    maxZ += pad;
    // Grow the short side so the viewBox matches the card's aspect ratio.
    let w = maxX - minX;
    let h = maxZ - minZ;
    if (w / h < ASPECT) {
      const grow = h * ASPECT - w;
      minX -= grow / 2;
      w = h * ASPECT;
    } else {
      const grow = w / ASPECT - h;
      minZ -= grow / 2;
      h = w / ASPECT;
    }
    return { minX, minZ, w, h };
  }, [segment, a, b]);

  const unit = box.w / APPROX_WIDTH_PX; // viewBox units per screen pixel
  const toPoints = (pts: { x: number; z: number }[]) => pts.map((p) => `${p.x.toFixed(0)},${p.z.toFixed(0)}`).join(" ");
  const segmentColor = segment ? (lines[segment.lineCode]?.color_hex ?? "#4C7DFF") : "#4C7DFF";

  return (
    <div className="overflow-hidden rounded-2xl border hairline bg-ink-900">
      <svg viewBox={`${box.minX} ${box.minZ} ${box.w} ${box.h}`} className="block aspect-[2/1] w-full" role="img" aria-label={`Map from ${from.name} to ${to.name}`}>
        {spans.map((span) => (
          <polyline
            key={span.key}
            points={toPoints(span.points)}
            fill="none"
            stroke="#2C3444"
            strokeWidth={3}
            vectorEffect="non-scaling-stroke"
            strokeLinejoin="round"
          />
        ))}
        {segment && (
          <polyline
            points={toPoints(segment.points)}
            fill="none"
            stroke={segmentColor}
            strokeWidth={5}
            vectorEffect="non-scaling-stroke"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}
        {trainIds.map((id) => {
          const pair = trainPairs[id];
          const track = pair ? tracks[pair.to.route_code] : undefined;
          if (!pair || !track) return null;
          const p = track.sample(pair.to.chainage_m);
          return (
            <g key={id}>
              <circle cx={p.x} cy={p.z} r={9 * unit} fill={lines[pair.to.line_code]?.color_hex} opacity={0.3} />
              <rect x={p.x - 7 * unit} y={p.z - 3.5 * unit} width={14 * unit} height={7 * unit} rx={3.5 * unit} fill="#F2C21B" stroke="#06080C" strokeWidth={unit} />
            </g>
          );
        })}
        <Marker x={a.x} z={a.z} unit={unit} color="#4C7DFF" label={from.name} />
        <Marker x={b.x} z={b.z} unit={unit} color="#FF5C5C" label={to.name} />
      </svg>
    </div>
  );
}

function Marker({ x, z, unit, color, label }: { x: number; z: number; unit: number; color: string; label: string }) {
  return (
    <g>
      <circle cx={x} cy={z} r={7 * unit} fill={color} stroke="#fff" strokeWidth={2 * unit} />
      <text x={x + 11 * unit} y={z + 4.5 * unit} fontSize={13 * unit} fontWeight={600} fill="#F3F5F9" stroke="#06080C" strokeWidth={3 * unit} paintOrder="stroke">
        {label}
      </text>
    </g>
  );
}
