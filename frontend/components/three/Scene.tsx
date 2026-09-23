"use client";

import { Canvas } from "@react-three/fiber";
import { CameraRig } from "./CameraRig";
import { City } from "./City";
import { Ground } from "./Ground";
import { OverlayProjector } from "./OverlayProjector";
import { SCENE } from "./palette";
import { RailLines } from "./RailLines";
import { Trains } from "./Trains";

// Stable references: Canvas re-applies these when their identity changes,
// which would fight the camera rig on every re-render.
const CAMERA = { fov: 40, near: 1, far: 250_000, position: [0, 60_000, 60_000] as [number, number, number] };
// Logarithmic depth keeps metre-scale detail (rails, platforms) free of
// z-fighting across a scene that spans tens of kilometres.
const GL = { antialias: true, logarithmicDepthBuffer: true, powerPreference: "high-performance" as const };

export function Scene() {
  return (
    <Canvas camera={CAMERA} gl={GL} dpr={[1, 2]}>
      <color attach="background" args={[SCENE.background]} />
      <hemisphereLight args={[SCENE.skyLight, SCENE.groundLight, 0.75]} />
      <directionalLight position={[-3000, 6000, 2500]} intensity={1.35} color={SCENE.sun} />
      <ambientLight intensity={0.18} />
      <Ground />
      <City />
      <RailLines />
      <Trains />
      <CameraRig />
      <OverlayProjector />
    </Canvas>
  );
}
