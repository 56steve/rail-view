"use client";

import { useMemo } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { allAnchors } from "@/lib/overlay";

/** Projects every registered overlay anchor to screen space each frame. */
export function OverlayProjector() {
  const camera = useThree((state) => state.camera);
  const size = useThree((state) => state.size);
  const point = useMemo(() => new THREE.Vector3(), []);

  useFrame(() => {
    for (const anchor of allAnchors()) {
      point.set(anchor.x, anchor.y, anchor.z);
      const distance = camera.position.distanceTo(point);
      point.project(camera);
      const onScreen = point.z > -1 && point.z < 1 && Math.abs(point.x) < 1.15 && Math.abs(point.y) < 1.15;
      if (!onScreen || distance > anchor.maxDistance) {
        anchor.element.style.visibility = "hidden";
        continue;
      }
      const sx = ((point.x + 1) / 2) * size.width;
      const sy = ((1 - point.y) / 2) * size.height;
      anchor.element.style.visibility = "visible";
      anchor.element.style.transform = `translate3d(${sx.toFixed(1)}px, ${sy.toFixed(1)}px, 0)`;
    }
  });

  return null;
}
