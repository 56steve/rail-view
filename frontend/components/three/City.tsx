"use client";

import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { buildTileGeometry, paintBuildings, type BuildingColors, type CityManifest } from "@/lib/city";
import { useRailView } from "@/lib/store";
import { usePalette } from "./palette";

/**
 * OpenStreetMap buildings along the rail corridors, one merged mesh per
 * 1.5km tile. Tiles are decoded one at a time with a yield between each,
 * so ~60k buildings stream in without blocking interaction. Meshes are
 * added imperatively to avoid a React re-render per tile, and repainted
 * in place when the day/night palette changes.
 */
export function City() {
  const groupRef = useRef<THREE.Group>(null);
  const meshesRef = useRef<THREE.Mesh[]>([]);
  const visible = useRailView((s) => s.showBuildings);
  const palette = usePalette();
  const material = useMemo(
    () => new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92, metalness: 0.04 }),
    [],
  );
  const colors = useMemo<BuildingColors>(
    () => ({
      base: new THREE.Color(palette.buildingBase),
      top: new THREE.Color(palette.buildingTop),
      roof: new THREE.Color(palette.roof),
    }),
    [palette],
  );
  // The loader paints each new tile with whatever palette is current.
  const colorsRef = useRef(colors);

  useEffect(() => {
    colorsRef.current = colors;
    for (const mesh of meshesRef.current) paintBuildings(mesh.geometry, colors);
  }, [colors]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;
    const controller = new AbortController();
    const meshes = meshesRef.current;

    const load = async () => {
      const response = await fetch("/city/manifest.json", { signal: controller.signal });
      if (!response.ok) return;
      const manifest = (await response.json()) as CityManifest;
      for (const tile of manifest.tiles) {
        if (controller.signal.aborted) return;
        const tileResponse = await fetch(`/city/${tile.file}`, { signal: controller.signal });
        if (!tileResponse.ok) continue;
        const geometry = buildTileGeometry(await tileResponse.arrayBuffer(), tile, manifest.format.coord_quantum_m);
        paintBuildings(geometry, colorsRef.current);
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
      meshes.length = 0;
    };
  }, [material]);

  useEffect(() => () => material.dispose(), [material]);

  return <group ref={groupRef} visible={visible} />;
}
