"use client";

import { useRef, useState } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { interpolateTrainPosition } from "@/lib/interpolate";
import { useRailPulseStore } from "@/lib/store";

const TRAIN_Y = 0.95;

// The beacon is a screen-space-constant marker (scaled by distance to
// camera every frame) so a train stays a legible dot from a full-network
// overview, the way a map pin does - the detailed body model beneath it
// is what reads at follow-cam distance. Without this, an accurately
// positioned ~9-unit train is imperceptible against a ~1000-unit route.
const BEACON_SCREEN_SIZE = 0.014;
const BEACON_MIN_SCALE = 0.5;
const BEACON_MAX_SCALE = 5;

// Visual footprint is deliberately exaggerated relative to
// lib/geo.ts METERS_PER_SCENE_UNIT (a real EMU car would render as a
// barely-visible ~1.1 units) so trains stay legible at both network-view
// and follow-cam zoom levels. Position accuracy is exact; only the model
// scale is stylized, the same way nav apps draw an oversized car icon on
// an accurately-scaled road.
const BODY_LENGTH = 9;
const BODY_WIDTH = 2.1;
const BODY_HEIGHT = 1.9;

const ACCENT_COLOR = "#2bd9c0";
const FAST_ACCENT = "#ff9d4d";

export function TrainMesh({ trainId }: { trainId: string }) {
  const groupRef = useRef<THREE.Group>(null);
  const beaconRef = useRef<THREE.Mesh>(null);
  const bodyMaterialRef = useRef<THREE.MeshStandardMaterial>(null);
  const stripeMaterialRef = useRef<THREE.MeshStandardMaterial>(null);
  const [hovered, setHovered] = useState(false);
  const { camera } = useThree();

  const isSelected = useRailPulseStore((state) => state.selectedTrainId === trainId);
  const selectTrain = useRailPulseStore((state) => state.selectTrain);
  const trainType = useRailPulseStore((state) => state.trainPairs[trainId]?.to.train_type);
  const exists = useRailPulseStore((state) => Boolean(state.trainPairs[trainId]));

  const accent = trainType === "FAST" ? FAST_ACCENT : ACCENT_COLOR;

  useFrame(() => {
    const pair = useRailPulseStore.getState().trainPairs[trainId];
    const group = groupRef.current;
    if (!pair || !group) return;

    const pos = interpolateTrainPosition(pair.from, pair.to, pair.toReceivedAtMs, performance.now());
    group.position.set(pos.x, TRAIN_Y, pos.z);
    group.rotation.y = THREE.MathUtils.degToRad(pos.headingDeg);

    const isStale = pos.status === "stale";
    if (bodyMaterialRef.current) {
      bodyMaterialRef.current.opacity = isStale ? 0.4 : 1;
      bodyMaterialRef.current.transparent = isStale;
    }
    if (stripeMaterialRef.current) {
      stripeMaterialRef.current.emissiveIntensity = isStale ? 0.15 : hovered || isSelected ? 1.1 : 0.6;
    }
    if (beaconRef.current) {
      const distance = camera.position.distanceTo(group.position);
      const scale = THREE.MathUtils.clamp(distance * BEACON_SCREEN_SIZE, BEACON_MIN_SCALE, BEACON_MAX_SCALE);
      beaconRef.current.scale.setScalar(scale);
    }
  });

  if (!exists) return null;

  return (
    <group
      ref={groupRef}
      onClick={(event) => {
        event.stopPropagation();
        selectTrain(trainId);
      }}
      onPointerOver={(event) => {
        event.stopPropagation();
        setHovered(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHovered(false);
        document.body.style.cursor = "auto";
      }}
    >
      {isSelected && (
        <mesh position={[0, -0.85, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[BODY_LENGTH * 0.55, BODY_LENGTH * 0.68, 32]} />
          <meshBasicMaterial color={accent} transparent opacity={0.55} />
        </mesh>
      )}

      <mesh ref={beaconRef} position={[0, BODY_HEIGHT + 2.2, 0]}>
        <sphereGeometry args={[0.5, 16, 16]} />
        <meshBasicMaterial color={accent} transparent opacity={0.9} />
      </mesh>

      {/* main car body */}
      <mesh position={[0, BODY_HEIGHT / 2, 0]} castShadow>
        <boxGeometry args={[BODY_WIDTH, BODY_HEIGHT, BODY_LENGTH]} />
        <meshStandardMaterial
          ref={bodyMaterialRef}
          color="#3c4452"
          metalness={0.5}
          roughness={0.3}
        />
      </mesh>

      {/* accent stripe */}
      <mesh position={[0, BODY_HEIGHT * 0.52, 0]}>
        <boxGeometry args={[BODY_WIDTH + 0.06, 0.28, BODY_LENGTH - 0.4]} />
        <meshStandardMaterial
          ref={stripeMaterialRef}
          color={accent}
          emissive={accent}
          emissiveIntensity={0.6}
        />
      </mesh>

      {/* cab windshield, front = -Z */}
      <mesh position={[0, BODY_HEIGHT * 0.78, -BODY_LENGTH / 2 + 0.55]} rotation={[0.35, 0, 0]}>
        <boxGeometry args={[BODY_WIDTH - 0.3, 0.55, 0.12]} />
        <meshStandardMaterial color="#0d1117" metalness={0.2} roughness={0.1} />
      </mesh>

      {/* headlights */}
      <mesh position={[BODY_WIDTH * 0.28, BODY_HEIGHT * 0.32, -BODY_LENGTH / 2 - 0.05]}>
        <sphereGeometry args={[0.14, 12, 12]} />
        <meshStandardMaterial color="#fff6da" emissive="#fff6da" emissiveIntensity={1.4} />
      </mesh>
      <mesh position={[-BODY_WIDTH * 0.28, BODY_HEIGHT * 0.32, -BODY_LENGTH / 2 - 0.05]}>
        <sphereGeometry args={[0.14, 12, 12]} />
        <meshStandardMaterial color="#fff6da" emissive="#fff6da" emissiveIntensity={1.4} />
      </mesh>

      {/* pantograph */}
      <mesh position={[0, BODY_HEIGHT + 0.3, BODY_LENGTH * 0.12]}>
        <boxGeometry args={[0.08, 0.55, 0.08]} />
        <meshStandardMaterial color="#1b2027" metalness={0.7} roughness={0.4} />
      </mesh>
      <mesh position={[0, BODY_HEIGHT + 0.58, BODY_LENGTH * 0.12]}>
        <boxGeometry args={[1.1, 0.06, 0.4]} />
        <meshStandardMaterial color="#1b2027" metalness={0.7} roughness={0.4} />
      </mesh>

      {/* bogies */}
      {[-BODY_LENGTH * 0.3, BODY_LENGTH * 0.3].map((z) => (
        <mesh key={z} position={[0, 0.05, z]}>
          <boxGeometry args={[BODY_WIDTH - 0.15, 0.3, 1.4]} />
          <meshStandardMaterial color="#14171c" roughness={0.9} />
        </mesh>
      ))}
    </group>
  );
}
