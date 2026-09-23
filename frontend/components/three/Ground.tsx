"use client";

import { useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { latLonToLocal } from "@/lib/geo";
import { GROUND_ORDER } from "./groundOrder";
import { usePalette } from "./palette";

interface GeoPolygon {
  exterior: [number, number][];
  holes: [number, number][][];
}

interface LandFile {
  land: GeoPolygon[];
  water: GeoPolygon[];
}

function toVectors(ring: [number, number][]): THREE.Vector2[] {
  return ring.map(([lat, lon]) => {
    const { east, north } = latLonToLocal(lat, lon);
    return new THREE.Vector2(east, north);
  });
}

function polygonsToGeometry(polygons: GeoPolygon[]): THREE.BufferGeometry {
  const shapes = polygons.map((polygon) => {
    const shape = new THREE.Shape(toVectors(polygon.exterior));
    shape.holes = polygon.holes.map((hole) => new THREE.Path(toVectors(hole)));
    return shape;
  });
  const geometry = new THREE.ShapeGeometry(shapes);
  // Shape space is (east, north); rotating onto the ground maps it to
  // scene (x = east, z = -north).
  geometry.rotateX(-Math.PI / 2);
  return geometry;
}

/**
 * Sea, land (from the OSM coastline) and large inland water. Everything
 * else in the scene sits above y=0, so the ground never needs to occlude
 * anything: it's drawn without writing depth, in GROUND_ORDER, which rules
 * out z-fighting between these nearly coplanar layers at any zoom. Ground
 * layers are unlit map colours.
 */
export function Ground() {
  const palette = usePalette();
  const [data, setData] = useState<LandFile | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/city/land.json", { signal: controller.signal })
      .then((response) => (response.ok ? (response.json() as Promise<LandFile>) : null))
      .then((json) => json && setData(json))
      .catch(() => {
        // Without land polygons the sea plane still renders; the network
        // and trains are unaffected.
      });
    return () => controller.abort();
  }, []);

  const land = useMemo(() => (data ? polygonsToGeometry(data.land) : null), [data]);
  const water = useMemo(() => (data ? polygonsToGeometry(data.water) : null), [data]);

  useEffect(() => () => land?.dispose(), [land]);
  useEffect(() => () => water?.dispose(), [water]);

  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position-y={-1} renderOrder={GROUND_ORDER.sea}>
        <planeGeometry args={[400_000, 400_000]} />
        <meshBasicMaterial color={palette.sea} depthWrite={false} />
      </mesh>
      {land && (
        <mesh geometry={land} renderOrder={GROUND_ORDER.land}>
          <meshBasicMaterial color={palette.land} depthWrite={false} />
        </mesh>
      )}
      {water && (
        // Transparent (at full opacity) so it's drawn in the same pass as
        // land cover, after it: water wins over overlapping mangrove.
        <mesh geometry={water} position-y={0.06} renderOrder={GROUND_ORDER.inlandWater}>
          <meshBasicMaterial color={palette.inlandWater} transparent depthWrite={false} />
        </mesh>
      )}
    </group>
  );
}
