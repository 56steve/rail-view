"use client";

import { useMemo } from "react";
import * as THREE from "three";
import { latLonToScene } from "@/lib/geo";
import type { RouteOut } from "@/lib/types";

const BED_RADIUS = 0.55;
const RAIL_RADIUS = 0.16;
const RAIL_LIFT = 0.22;

/**
 * Draws the track centerline as two tubes along a curve built from the
 * route's polyline: a wide dark ballast bed, and a thinner accent-lit rail
 * on top. This IS the actual route geometry the trains are matched onto
 * server-side (see backend app/services/track_matching.py) - not a
 * decorative line, the same lat/lon polyline the API serves.
 */
export function RailwayTrack({ route }: { route: RouteOut }) {
  const curve = useMemo(() => {
    const points = route.polyline.map(([lat, lon]) => {
      const scene = latLonToScene(lat, lon);
      return new THREE.Vector3(scene.x, 0, scene.z);
    });
    return new THREE.CatmullRomCurve3(points, false, "catmullrom", 0.15);
  }, [route.polyline]);

  const segments = Math.max(route.polyline.length * 12, 64);

  const bedGeometry = useMemo(
    () => new THREE.TubeGeometry(curve, segments, BED_RADIUS, 8, false),
    [curve, segments],
  );
  const railGeometry = useMemo(
    () => new THREE.TubeGeometry(curve, segments, RAIL_RADIUS, 8, false),
    [curve, segments],
  );

  return (
    <group>
      <mesh geometry={bedGeometry} position={[0, 0, 0]}>
        <meshStandardMaterial color="#3a4250" roughness={0.85} metalness={0.15} />
      </mesh>
      <mesh geometry={railGeometry} position={[0, RAIL_LIFT, 0]}>
        <meshStandardMaterial
          color={route.color_hex}
          emissive={route.color_hex}
          emissiveIntensity={0.35}
          roughness={0.4}
          metalness={0.3}
        />
      </mesh>
    </group>
  );
}
