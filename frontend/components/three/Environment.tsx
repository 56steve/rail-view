"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import {
  decodeLandcover,
  decodeRoads,
  fetchBinary,
  type LandcoverData,
  type RoadData,
} from "@/lib/environment";
import { edgeFadeMaterial } from "./edgeFadeMaterial";
import { GROUND_ORDER, GROUND_TOP_Y } from "./groundOrder";
import { LANDCOVER_CLASSES, ROAD_CLASSES, usePalette, type RoadClass } from "./palette";
import { flatRibbonsGeometry } from "./trackGeometry";

// Land cover and roads fade out over this distance inside the edge of
// their data, blending into plain land.
const EDGE_FADE_M = 7000;
const LANDCOVER_Y = 0.03;
const ROAD_Y = GROUND_TOP_Y;

const ROAD_WIDTH_M: Record<RoadClass, number> = {
  motorway: 24,
  trunk: 20,
  primary: 15,
  secondary: 12,
  tertiary: 9,
  minor: 6,
};
// Streets are noise at city scale; they appear as the camera comes down.
const ROAD_MAX_HEIGHT_M: Record<RoadClass, number> = {
  motorway: Infinity,
  trunk: Infinity,
  primary: Infinity,
  secondary: 30_000,
  tertiary: 12_000,
  minor: 5_000,
};

function useBinaryLayer<T>(path: string, decode: (buffer: ArrayBuffer) => T): T | null {
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetchBinary(path, controller.signal)
      .then((buffer) => setData(decode(buffer)))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) console.error(`RailView: ${path} failed to load`, error);
      });
    return () => controller.abort();
  }, [path, decode]);
  return data;
}

function Landcover({ data }: { data: LandcoverData }) {
  const palette = usePalette();
  const layers = useMemo(
    () =>
      data.classes.map((mesh, i) => {
        const cls = LANDCOVER_CLASSES[i];
        if (!cls || mesh.indices.length === 0) return null;
        const positions = new Float32Array((mesh.positions.length / 2) * 3);
        for (let k = 0, v = 0; k < mesh.positions.length; k += 2, v += 3) {
          positions[v] = mesh.positions[k]!;
          positions[v + 1] = LANDCOVER_Y;
          positions[v + 2] = mesh.positions[k + 1]!;
        }
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        geometry.setIndex(new THREE.BufferAttribute(mesh.indices, 1));
        geometry.computeBoundingSphere();
        return { cls, geometry, material: edgeFadeMaterial("#000000", data.bounds, EDGE_FADE_M), order: i };
      }),
    [data],
  );

  useEffect(() => {
    for (const layer of layers) layer?.material.color.set(palette.landcover[layer.cls]);
  }, [layers, palette]);

  useEffect(
    () => () => {
      for (const layer of layers) {
        layer?.geometry.dispose();
        layer?.material.dispose();
      }
    },
    [layers],
  );

  return (
    <group>
      {layers.map(
        (layer) =>
          layer && (
            <mesh
              key={layer.cls}
              geometry={layer.geometry}
              material={layer.material}
              renderOrder={GROUND_ORDER.landcover + layer.order}
            />
          ),
      )}
    </group>
  );
}

interface RoadLayer {
  cls: RoadClass;
  geometry: THREE.BufferGeometry;
  material: THREE.MeshBasicMaterial;
  order: number;
}

function Roads({ data }: { data: RoadData }) {
  const palette = usePalette();
  const [layers, setLayers] = useState<RoadLayer[]>([]);

  // Built one class at a time with a yield in between, major roads
  // first, so the map is interactive while the street network fills in.
  useEffect(() => {
    let cancelled = false;
    const built: RoadLayer[] = [];
    const build = async () => {
      for (let i = 0; i < data.classes.length; i++) {
        const cls = ROAD_CLASSES[i];
        const lines = data.classes[i];
        if (!cls || !lines || lines.length === 0) continue;
        await new Promise((resolve) => setTimeout(resolve, 0));
        if (cancelled) return;
        built.push({
          cls,
          geometry: flatRibbonsGeometry(lines, ROAD_WIDTH_M[cls], ROAD_Y),
          material: edgeFadeMaterial("#000000", data.bounds, EDGE_FADE_M),
          order: i,
        });
        setLayers([...built]);
      }
    };
    void build();
    return () => {
      cancelled = true;
      for (const layer of built) {
        layer.geometry.dispose();
        layer.material.dispose();
      }
    };
  }, [data]);

  useEffect(() => {
    for (const layer of layers) layer.material.color.set(palette.roads[layer.cls]);
  }, [layers, palette]);

  const meshes = useRef(new Map<RoadClass, THREE.Mesh>());
  useFrame(({ camera }) => {
    for (const layer of layers) {
      const mesh = meshes.current.get(layer.cls);
      if (mesh) mesh.visible = camera.position.y < ROAD_MAX_HEIGHT_M[layer.cls];
    }
  });

  return (
    <group>
      {layers.map((layer) => (
        <mesh
          key={layer.cls}
          ref={(mesh) => {
            if (mesh) meshes.current.set(layer.cls, mesh);
            else meshes.current.delete(layer.cls);
          }}
          geometry={layer.geometry}
          material={layer.material}
          // Minor roads first, so bigger roads draw over them at junctions.
          renderOrder={GROUND_ORDER.roads + (ROAD_CLASSES.length - 1 - layer.order)}
        />
      ))}
    </group>
  );
}

/** OpenStreetMap land cover (parks, forest, mangrove, farmland, beaches,
 * built-up areas) and roads, coloured for the current day/night mode. */
export function Environment() {
  const landcover = useBinaryLayer("/city/landcover.bin", decodeLandcover);
  const roads = useBinaryLayer("/city/roads.bin", decodeRoads);
  return (
    <group>
      {landcover && <Landcover data={landcover} />}
      {roads && <Roads data={roads} />}
    </group>
  );
}
