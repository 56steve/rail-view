"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import * as THREE from "three";
import type { Line2 } from "three-stdlib";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { ScenePoint } from "@/lib/geo";
import { routeSpans } from "@/lib/network";
import { loadRailLayout, type RailLayout } from "@/lib/railLayout";
import { useRailView } from "@/lib/store";
import { usePalette } from "./palette";
import {
  SINGLE_TRACK_BED_WIDTH_M,
  extrudedFootprintsGeometry,
  ribbonGeometry,
  trackBedTexture,
} from "./trackGeometry";

const GLOW_Y = 7;
const TRACK_BED_Y = 0.4;
// Beds of converging tracks overlap at turnouts; staggering their heights
// by a few centimetres stops the overlaps from z-fighting.
const TRACK_BED_Y_STEP = 0.025;
const TRACK_BED_Y_LEVELS = 4;
const PLATFORM_HEIGHT_M = 0.9;
// Below this camera height the physical track reads on its own and the
// route glow fades so it doesn't paint over the rails.
const GLOW_FADE_START_M = 2500;
const GLOW_FADE_END_M = 400;
const DETAIL_MAX_HEIGHT_M = 6000;

function RouteGlow({ points, color, dimmed }: { points: ScenePoint[]; color: string; dimmed: boolean }) {
  const linePoints = useMemo(() => points.map((p) => [p.x, GLOW_Y, p.z] as [number, number, number]), [points]);
  const coreRef = useRef<Line2>(null);
  const glowRef = useRef<Line2>(null);
  const base = dimmed ? 0.16 : 1;

  useFrame(({ camera }) => {
    const height = camera.position.y;
    const t = THREE.MathUtils.clamp((height - GLOW_FADE_END_M) / (GLOW_FADE_START_M - GLOW_FADE_END_M), 0.18, 1);
    if (coreRef.current) coreRef.current.material.opacity = base * t;
    if (glowRef.current) glowRef.current.material.opacity = base * t * 0.28;
  });

  return (
    <group>
      <Line ref={glowRef} points={linePoints} color={color} lineWidth={9} transparent depthWrite={false} toneMapped={false} />
      <Line ref={coreRef} points={linePoints} color={color} lineWidth={2.6} transparent depthWrite={false} toneMapped={false} />
    </group>
  );
}

/** Every individual OSM track and platform along the routes - so a
 * two-track branch, a four-track main line and a nine-track junction
 * each look like what's actually on the ground. */
function PhysicalRailway() {
  const palette = usePalette();
  const [layout, setLayout] = useState<RailLayout | null>(null);
  const texture = useMemo(() => trackBedTexture(), []);

  useEffect(() => {
    const controller = new AbortController();
    loadRailLayout(controller.signal)
      .then(setLayout)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) console.error("RailView: track layout failed to load", error);
      });
    return () => controller.abort();
  }, []);

  const beds = useMemo(() => {
    if (!layout || layout.tracks.length === 0) return null;
    const parts = layout.tracks.map((track, i) =>
      ribbonGeometry(track, SINGLE_TRACK_BED_WIDTH_M, TRACK_BED_Y + (i % TRACK_BED_Y_LEVELS) * TRACK_BED_Y_STEP),
    );
    const merged = mergeGeometries(parts);
    for (const part of parts) part.dispose();
    return merged;
  }, [layout]);

  const platforms = useMemo(
    () => (layout && layout.platforms.length > 0 ? extrudedFootprintsGeometry(layout.platforms, PLATFORM_HEIGHT_M) : null),
    [layout],
  );

  useEffect(() => () => texture.dispose(), [texture]);
  useEffect(() => () => beds?.dispose(), [beds]);
  useEffect(() => () => platforms?.dispose(), [platforms]);

  // Rails and platforms are metre-scale detail; from city height they
  // only alias into shimmering noise, so they're drawn close up only.
  const group = useRef<THREE.Group>(null);
  useFrame(({ camera }) => {
    if (group.current) group.current.visible = camera.position.y < DETAIL_MAX_HEIGHT_M;
  });

  return (
    <group ref={group}>
      {beds && (
        <mesh geometry={beds}>
          <meshStandardMaterial map={texture} roughness={0.95} />
        </mesh>
      )}
      {platforms && (
        <mesh geometry={platforms}>
          <meshStandardMaterial color={palette.platform} roughness={0.85} />
        </mesh>
      )}
    </group>
  );
}

export function RailLines() {
  const routes = useRailView((s) => s.routes);
  const tracks = useRailView((s) => s.tracks);
  const lineFilter = useRailView((s) => s.lineFilter);
  const spans = useMemo(() => routeSpans(routes, tracks), [routes, tracks]);

  return (
    <group>
      <PhysicalRailway />
      {spans.map((span) => (
        <RouteGlow
          key={span.key}
          points={span.points}
          color={span.color}
          dimmed={lineFilter !== null && lineFilter !== span.lineCode}
        />
      ))}
    </group>
  );
}
