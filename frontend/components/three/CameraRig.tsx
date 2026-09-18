"use client";

import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { interpolateTrainPosition } from "@/lib/interpolate";
import { latLonToScene } from "@/lib/geo";
import { useRailPulseStore } from "@/lib/store";

const FOLLOW_DISTANCE = 13;
const FOLLOW_HEIGHT = 7;
const FOLLOW_LERP = 0.07;

export function CameraRig() {
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const { camera } = useThree();
  const desiredTarget = useRef(new THREE.Vector3());
  const desiredCameraPos = useRef(new THREE.Vector3());
  const route = useRailPulseStore((state) => state.route);

  // Frame the whole route on first load / whenever a new route arrives,
  // so "Network View" opens with the corridor visible rather than at an
  // arbitrary default camera position.
  useEffect(() => {
    if (!route || route.stations.length === 0) return;
    const points = route.stations.map((s) => latLonToScene(s.lat, s.lon));
    const xs = points.map((p) => p.x);
    const zs = points.map((p) => p.z);
    const centerX = (Math.min(...xs) + Math.max(...xs)) / 2;
    const centerZ = (Math.min(...zs) + Math.max(...zs)) / 2;
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...zs) - Math.min(...zs));
    const radius = Math.max(span * 0.75, 40);

    camera.position.set(centerX + radius * 0.35, radius * 0.85, centerZ + radius * 0.9);
    if (controlsRef.current) {
      controlsRef.current.target.set(centerX, 0, centerZ);
      controlsRef.current.update();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route?.route_id]);

  useFrame(() => {
    const state = useRailPulseStore.getState();
    const { selectedTrainId, followSelected, trainPairs } = state;
    if (!followSelected || !selectedTrainId) return;

    const pair = trainPairs[selectedTrainId];
    if (!pair) return;

    const pos = interpolateTrainPosition(pair.from, pair.to, pair.toReceivedAtMs, performance.now());
    const headingRad = THREE.MathUtils.degToRad(pos.headingDeg);

    // Chase-cam offset directly behind the train relative to its heading.
    const behindX = pos.x - Math.sin(headingRad) * FOLLOW_DISTANCE;
    const behindZ = pos.z + Math.cos(headingRad) * FOLLOW_DISTANCE;

    desiredTarget.current.set(pos.x, 1.2, pos.z);
    desiredCameraPos.current.set(behindX, FOLLOW_HEIGHT, behindZ);

    camera.position.lerp(desiredCameraPos.current, FOLLOW_LERP);
    if (controlsRef.current) {
      controlsRef.current.target.lerp(desiredTarget.current, FOLLOW_LERP);
      controlsRef.current.update();
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      minDistance={5}
      maxDistance={2500}
      maxPolarAngle={Math.PI * 0.49}
    />
  );
}
