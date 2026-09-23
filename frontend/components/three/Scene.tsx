"use client";

import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import * as THREE from "three";
import { useRailView } from "@/lib/store";
import { CameraRig } from "./CameraRig";
import { City } from "./City";
import { Environment } from "./Environment";
import { Ground } from "./Ground";
import { OverlayProjector } from "./OverlayProjector";
import { usePalette } from "./palette";
import { RailLines } from "./RailLines";
import { Trains } from "./Trains";

// Stable references: Canvas re-applies these when their identity changes,
// which would fight the camera rig on every re-render.
const CAMERA = { fov: 40, near: 1, far: 250_000, position: [0, 60_000, 60_000] as [number, number, number] };
// Logarithmic depth keeps metre-scale detail (rails, platforms) free of
// z-fighting across a scene that spans tens of kilometres.
const GL = { antialias: true, logarithmicDepthBuffer: true, powerPreference: "high-performance" as const };

const SUN_DISTANCE = 8000;
// Low sun (early morning, late afternoon) is warmer; by this elevation it
// has reached the palette's midday colour.
const WARM_SUN = new THREE.Color("#FFC58A");
const MIDDAY_ELEVATION_DEG = 35;

/** Sky, sun and fill light for the current day/night mode. By day the
 * sun sits where the real sun is over Mumbai. */
function Lighting() {
  const palette = usePalette();
  const lighting = useRailView((s) => s.lighting);
  const [dx, dy, dz] = lighting.sunDirection;
  const sunColor = useMemo(() => {
    const midday = new THREE.Color(palette.sun);
    if (lighting.mode === "night") return midday;
    const t = THREE.MathUtils.clamp((lighting.sunElevationDeg - 10) / (MIDDAY_ELEVATION_DEG - 10), 0, 1);
    return WARM_SUN.clone().lerp(midday, t);
  }, [palette, lighting.mode, lighting.sunElevationDeg]);

  return (
    <>
      <color attach="background" args={[palette.background]} />
      <hemisphereLight args={[palette.skyLight, palette.groundLight, palette.hemisphereIntensity]} />
      <directionalLight
        position={[dx * SUN_DISTANCE, dy * SUN_DISTANCE, dz * SUN_DISTANCE]}
        intensity={palette.sunIntensity}
        color={sunColor}
      />
      <ambientLight intensity={palette.ambientIntensity} />
    </>
  );
}

export function Scene() {
  return (
    <Canvas camera={CAMERA} gl={GL} dpr={[1, 2]}>
      <Lighting />
      <Ground />
      <Environment />
      <City />
      <RailLines />
      <Trains />
      <CameraRig />
      <OverlayProjector />
    </Canvas>
  );
}
