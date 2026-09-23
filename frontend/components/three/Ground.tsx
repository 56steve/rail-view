"use client";

import { useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { latLonToLocal } from "@/lib/geo";
import { SCENE } from "./palette";

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
 * anything: it's drawn first without writing depth, which rules out
 * z-fighting between these nearly coplanar layers at any zoom.
 */
export function Ground() {
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
      <mesh rotation-x={-Math.PI / 2} position-y={-1} renderOrder={-3}>
        <planeGeometry args={[400_000, 400_000]} />
        <meshStandardMaterial color={SCENE.sea} roughness={1} depthWrite={false} />
      </mesh>
      {land && (
        <mesh geometry={land} renderOrder={-2}>
          <meshStandardMaterial color={SCENE.land} roughness={1} depthWrite={false} />
        </mesh>
      )}
      {water && (
        <mesh geometry={water} position-y={0.2} renderOrder={-1}>
          <meshStandardMaterial color={SCENE.inlandWater} roughness={1} depthWrite={false} />
        </mesh>
      )}
    </group>
  );
}
