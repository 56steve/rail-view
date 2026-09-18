"use client";

import { Canvas } from "@react-three/fiber";
import { useShallow } from "zustand/react/shallow";
import { useRailPulseStore } from "@/lib/store";
import { CameraRig } from "./CameraRig";
import { RailwayTrack } from "./RailwayTrack";
import { StationMarkers } from "./StationMarkers";
import { TrainMesh } from "./TrainMesh";

// A stable reference matters here: Scene re-renders on every WebSocket
// tick (trainIds changes), and passing a fresh object literal to
// Canvas's `camera` prop on every render fights CameraRig's manual
// positioning (R3F re-applies the initial camera config whenever the
// prop reference changes), so the camera never settles anywhere useful.
const INITIAL_CAMERA = { position: [200, 260, 320] as [number, number, number], fov: 42, near: 0.5, far: 8000 };

export function Scene() {
  const route = useRailPulseStore((state) => state.route);
  // `useShallow` is required here: without it, the selector returns a new
  // array identity every render, which React 19's external-store checks
  // treat as a never-settling snapshot and loop forever.
  const trainIds = useRailPulseStore(useShallow((state) => Object.keys(state.trainPairs)));

  return (
    <Canvas
      camera={INITIAL_CAMERA}
      dpr={[1, 2]}
      gl={{ antialias: true }}
      onPointerMissed={() => useRailPulseStore.getState().selectTrain(null)}
    >
      <color attach="background" args={["#0a0c10"]} />
      <fog attach="fog" args={["#0a0c10", 900, 3600]} />
      <ambientLight intensity={0.95} />
      <hemisphereLight args={["#5a7099", "#0d1117", 0.85]} />
      <directionalLight position={[400, 600, 250]} intensity={1.3} color="#e7edff" />
      {/* Fill light from roughly the opposite side, so a train's face
          away from the key light doesn't read as pure black from the
          follow camera (which can end up on any side of a train
          depending on its heading). */}
      <directionalLight position={[-350, 250, -300]} intensity={0.55} color="#8fb4ff" />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]}>
        <planeGeometry args={[20000, 20000]} />
        <meshStandardMaterial color="#0d1015" roughness={1} />
      </mesh>

      {route && <RailwayTrack route={route} />}
      {route && <StationMarkers route={route} />}
      {trainIds.map((id) => (
        <TrainMesh key={id} trainId={id} />
      ))}

      <CameraRig />
    </Canvas>
  );
}
