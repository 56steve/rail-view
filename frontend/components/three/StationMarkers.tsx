"use client";

import { Suspense } from "react";
import { Billboard, Text } from "@react-three/drei";
import { latLonToScene } from "@/lib/geo";
import { useRailPulseStore } from "@/lib/store";
import type { RouteOut, StationOut } from "@/lib/types";

export function StationMarkers({ route }: { route: RouteOut }) {
  return (
    <group>
      {route.stations.map((station) => (
        <StationMarker key={station.code} station={station} lineColor={route.color_hex} />
      ))}
    </group>
  );
}

function StationMarker({ station, lineColor }: { station: StationOut; lineColor: string }) {
  const scene = latLonToScene(station.lat, station.lon);
  const isTerminus = station.sequence === 0;
  const viewMode = useRailPulseStore((state) => state.viewMode);

  return (
    <group position={[scene.x, 0, scene.z]}>
      <mesh position={[0, 0.24, 0]}>
        <cylinderGeometry args={[isTerminus ? 0.9 : 0.6, isTerminus ? 0.9 : 0.6, 0.12, 16]} />
        <meshStandardMaterial
          color={isTerminus ? lineColor : "#c7cdd6"}
          emissive={isTerminus ? lineColor : "#000000"}
          emissiveIntensity={isTerminus ? 0.5 : 0}
        />
      </mesh>
      {viewMode === "network" && (
        // Isolated Suspense boundary: drei's <Text> suspends while it
        // fetches its glyph font. Scoping the boundary to just the label
        // means a slow/blocked font request hides station names only -
        // never the track, markers, or trains, which render synchronously
        // and don't belong inside this boundary.
        <Suspense fallback={null}>
          <Billboard position={[0, 3.2, 0]}>
            <Text
              fontSize={1.6}
              color="#c7cdd6"
              anchorX="center"
              anchorY="bottom"
              outlineWidth={0.04}
              outlineColor="#0a0c10"
            >
              {station.name}
            </Text>
          </Billboard>
        </Suspense>
      )}
    </group>
  );
}
