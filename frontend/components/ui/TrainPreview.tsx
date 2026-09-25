"use client";

import { Suspense, useEffect, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import { COACH } from "../three/coachGeometry";
import { EMU_MODEL_URL, rakeLivery, readEmuModel, useStudioReflections, type CoachPart } from "../three/emuModel";

const CAMERA = { position: [7.5, 3.4, -21] as [number, number, number], fov: 30 };
const GL = { antialias: true, alpha: true };

/** Hero render of a train's leading cab and the coach behind it,
 * three-quarter front view, in its livery (AC or not). */
export function TrainPreview({ ac }: { ac: boolean }) {
  return (
    <div className="relative h-52 w-full overflow-hidden bg-[radial-gradient(120%_90%_at_70%_0%,#1f2a44_0%,#0b0e14_60%)]">
      <Canvas camera={CAMERA} gl={GL} dpr={[1, 2]} frameloop="demand" onCreated={({ camera }) => camera.lookAt(0, 2.2, -4)}>
        <hemisphereLight args={["#bcd0ff", "#1a1f28", 0.9]} />
        <directionalLight position={[8, 12, -14]} intensity={1.6} />
        <Suspense fallback={null}>
          <PreviewCoaches ac={ac} />
        </Suspense>
        <mesh rotation-x={-Math.PI / 2} position-y={-0.02}>
          <planeGeometry args={[60, 120]} />
          <meshStandardMaterial color="#141820" roughness={1} />
        </mesh>
      </Canvas>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-ink-950 to-transparent" />
    </div>
  );
}

/** The model's cab and a trailer in full detail, with materials of their
 * own: this canvas has its own renderer and reflection map. */
function PreviewCoaches({ ac }: { ac: boolean }) {
  const gltf = useGLTF(EMU_MODEL_URL, false, true);
  const coaches = useMemo(() => {
    const parts = readEmuModel(gltf.scene).parts[rakeLivery(ac)];
    const own = (list: CoachPart[]): CoachPart[] => list.map((p) => ({ geometry: p.geometry, material: p.material.clone() }));
    return { cab: own(parts.cab[0]!), trailer: own(parts.trailer[0]!) };
  }, [gltf, ac]);
  const materials = useMemo(() => [...coaches.cab, ...coaches.trailer].map((p) => p.material), [coaches]);
  useStudioReflections(materials);
  useEffect(
    () => () => {
      for (const part of [...coaches.cab, ...coaches.trailer]) {
        part.geometry.dispose();
        part.material.dispose();
      }
    },
    [coaches],
  );

  return (
    <group>
      {coaches.cab.map((part, i) => (
        <mesh key={`cab-${i}`} geometry={part.geometry} material={part.material} />
      ))}
      <group position-z={COACH.length + COACH.gap}>
        {coaches.trailer.map((part, i) => (
          <mesh key={`trailer-${i}`} geometry={part.geometry} material={part.material} />
        ))}
      </group>
    </group>
  );
}
