"use client";

import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { COACH, coachGeometry, coachMaterial, type Livery } from "../three/coachGeometry";

const CAMERA = { position: [7.5, 3.4, -21] as [number, number, number], fov: 30 };
const GL = { antialias: true, alpha: true };

/** Hero render of a train's leading coach, three-quarter front view. */
export function TrainPreview({ lineColor, ac }: { lineColor: string; ac: boolean }) {
  const livery = useMemo<Livery>(() => ({ band: lineColor, ac }), [lineColor, ac]);
  const lead = useMemo(() => coachGeometry("cab", livery), [livery]);
  const trailer = useMemo(() => coachGeometry("trailer", livery), [livery]);

  return (
    <div className="relative h-52 w-full overflow-hidden bg-[radial-gradient(120%_90%_at_70%_0%,#1f2a44_0%,#0b0e14_60%)]">
      <Canvas camera={CAMERA} gl={GL} dpr={[1, 2]} frameloop="demand" onCreated={({ camera }) => camera.lookAt(0, 2.2, -4)}>
        <hemisphereLight args={["#bcd0ff", "#1a1f28", 0.9]} />
        <directionalLight position={[8, 12, -14]} intensity={1.6} />
        <mesh geometry={lead} material={coachMaterial()} />
        <mesh geometry={trailer} material={coachMaterial()} position-z={COACH.length + COACH.gap} />
        <mesh rotation-x={-Math.PI / 2} position-y={-0.02}>
          <planeGeometry args={[60, 120]} />
          <meshStandardMaterial color="#141820" roughness={1} />
        </mesh>
      </Canvas>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-ink-950 to-transparent" />
    </div>
  );
}
