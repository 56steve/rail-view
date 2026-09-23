"use client";

import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { buildTileGeometry, type CityManifest } from "@/lib/city";
import { useRailView } from "@/lib/store";
import { SCENE } from "./palette";

/**
 * OpenStreetMap buildings along the rail corridors, one merged mesh per
 * 1.5km tile. Tiles are decoded one at a time with a yield between each,
 * so ~50k buildings stream in without blocking interaction. Meshes are
 * added imperatively to avoid a React re-render per tile.
 */
export function City() {
  const groupRef = useRef<THREE.Group>(null);
  const visible = useRailView((s) => s.showBuildings);
  const material = useMemo(
    () => new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92, metalness: 0.04 }),
    [],
  );

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;
    const controller = new AbortController();
    const meshes: THREE.Mesh[] = [];
    const colors = {
      base: new THREE.Color(SCENE.buildingBase),
      top: new THREE.Color(SCENE.buildingTop),
      roof: new THREE.Color(SCENE.roof),
    };

    const load = async () => {
      const response = await fetch("/city/manifest.json", { signal: controller.signal });
      if (!response.ok) return;
      const manifest = (await response.json()) as CityManifest;
      for (const tile of manifest.tiles) {
        if (controller.signal.aborted) return;
        const tileResponse = await fetch(`/city/${tile.file}`, { signal: controller.signal });
        if (!tileResponse.ok) continue;
        const geometry = buildTileGeometry(
          await tileResponse.arrayBuffer(),
          tile,
          manifest.format.coord_quantum_m,
          colors,
        );
        const mesh = new THREE.Mesh(geometry, material);
        meshes.push(mesh);
        group.add(mesh);
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    };

    load().catch((error: unknown) => {
      if (!controller.signal.aborted) console.error("RailView: city tiles failed to load", error);
    });

    return () => {
      controller.abort();
      for (const mesh of meshes) {
        group.remove(mesh);
        mesh.geometry.dispose();
      }
    };
  }, [material]);

  useEffect(() => () => material.dispose(), [material]);

  return <group ref={groupRef} visible={visible} />;
}
