"use client";

import { useLayoutEffect, useMemo, useRef } from "react";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import { useShallow } from "zustand/react/shallow";
import { laneSample } from "@/lib/lanes";
import { trainPose } from "@/lib/motion";
import { navigate } from "@/lib/navigation";
import { focusedTrainId, useRailView } from "@/lib/store";
import { COACH_PITCH, coachGeometry, coachMaterial } from "./coachGeometry";

// Closer than this, a train is drawn as its true-scale rake following the
// track's curves; farther, as a compact glyph sized to stay legible at
// city scale (a 250m train is otherwise sub-pixel in the network view).
const RAKE_LOD_DISTANCE_M = 2600;
// Glyph world-scale per metre of camera distance, tuned so the glyph
// stays ~40px long on a typical viewport regardless of zoom. Width and
// height are exaggerated further: at that size a true-proportioned coach
// would be a 2px sliver.
const GLYPH_SCALE_PER_M = 0.0007;
const GLYPH_GIRTH = 2.4;

const TAP_MAX_TRAVEL_PX = 6;

const STALE_TINT = new THREE.Color(0.38, 0.4, 0.44);
const LIVE_TINT = new THREE.Color(1, 1, 1);

export function Trains() {
  const ids = useRailView(useShallow((s) => Object.keys(s.trainPairs)));
  return (
    <group>
      {ids.map((id) => (
        <TrainView key={id} trainId={id} />
      ))}
    </group>
  );
}

function TrainView({ trainId }: { trainId: string }) {
  const lineCode = useRailView((s) => s.trainPairs[trainId]?.to.line_code ?? null);
  const coachCount = useRailView((s) => s.trainPairs[trainId]?.to.coach_count ?? 12);
  const color = useRailView((s) => (lineCode ? s.lines[lineCode]?.color_hex : undefined)) ?? "#8B93A3";
  const focused = useRailView((s) => focusedTrainId(s) === trainId);
  const dimmed = useRailView((s) => s.lineFilter !== null && s.lineFilter !== lineCode);

  const cab = useMemo(() => coachGeometry("cab", color), [color]);
  const trailer = useMemo(() => coachGeometry("trailer", color), [color]);
  const material = coachMaterial();

  const rakeCabs = useRef<THREE.InstancedMesh>(null);
  const rakeTrailers = useRef<THREE.InstancedMesh>(null);
  const glyph = useRef<THREE.Group>(null);
  const glyphCabs = useRef<THREE.InstancedMesh>(null);
  const glow = useRef<THREE.Mesh>(null);
  const scratch = useMemo(() => ({ object: new THREE.Object3D(), point: new THREE.Vector3() }), []);

  // Glyph layout never changes: two cab cars nose-to-tail, scaled as a group.
  useLayoutEffect(() => {
    const mesh = glyphCabs.current;
    if (!mesh) return;
    const o = scratch.object;
    o.position.set(0, 0, -COACH_PITCH / 2);
    o.rotation.set(0, 0, 0);
    o.updateMatrix();
    mesh.setMatrixAt(0, o.matrix);
    o.position.set(0, 0, COACH_PITCH / 2);
    o.rotation.set(0, Math.PI, 0);
    o.updateMatrix();
    mesh.setMatrixAt(1, o.matrix);
    mesh.instanceMatrix.needsUpdate = true;
  }, [scratch]);

  useFrame(({ camera, clock }) => {
    const state = useRailView.getState();
    const pair = state.trainPairs[trainId];
    const track = pair ? state.tracks[pair.to.route_code] : undefined;
    const lanes = pair ? state.lanes[pair.to.route_code] : undefined;
    const cabs = rakeCabs.current;
    const trailers = rakeTrailers.current;
    const group = glyph.current;
    if (!pair || !track || !lanes || !cabs || !trailers || !group || !glyphCabs.current || !glow.current) return;

    const pose = trainPose(pair, performance.now());
    const centre = laneSample(track, lanes, pose.forward, pose.chainage);
    const distance = camera.position.distanceTo(scratch.point.set(centre.x, 0, centre.z));
    const near = distance < RAKE_LOD_DISTANCE_M;
    const tint = pose.status === "stale" ? STALE_TINT : LIVE_TINT;
    const turn = pose.forward ? 0 : Math.PI;

    cabs.visible = near;
    trailers.visible = near;
    group.visible = !near;

    if (near) {
      const dir = pose.forward ? 1 : -1;
      const frontChainage = pose.chainage + dir * ((coachCount - 1) / 2) * COACH_PITCH;
      const o = scratch.object;
      let trailerIndex = 0;
      for (let k = 0; k < coachCount; k++) {
        const s = laneSample(track, lanes, pose.forward, frontChainage - dir * k * COACH_PITCH);
        const isRearCab = k === coachCount - 1;
        o.position.set(s.x, 0, s.z);
        o.rotation.set(0, s.yaw + turn + (isRearCab ? Math.PI : 0), 0);
        o.updateMatrix();
        if (k === 0 || isRearCab) {
          const index = k === 0 ? 0 : 1;
          cabs.setMatrixAt(index, o.matrix);
          cabs.setColorAt(index, tint);
        } else {
          trailers.setMatrixAt(trailerIndex, o.matrix);
          trailers.setColorAt(trailerIndex, tint);
          trailerIndex += 1;
        }
      }
      cabs.instanceMatrix.needsUpdate = true;
      trailers.instanceMatrix.needsUpdate = true;
      if (cabs.instanceColor) cabs.instanceColor.needsUpdate = true;
      if (trailers.instanceColor) trailers.instanceColor.needsUpdate = true;
      cabs.computeBoundingSphere();
      trailers.computeBoundingSphere();
    } else {
      const scale = Math.max(1, distance * GLYPH_SCALE_PER_M);
      group.position.set(centre.x, 0, centre.z);
      group.rotation.set(0, centre.yaw + turn, 0);
      group.scale.set(scale * GLYPH_GIRTH, scale * GLYPH_GIRTH, scale);
      glyphCabs.current.setColorAt(0, tint);
      glyphCabs.current.setColorAt(1, tint);
      if (glyphCabs.current.instanceColor) glyphCabs.current.instanceColor.needsUpdate = true;
      const pulse = focused ? 1 + 0.25 * Math.sin(clock.elapsedTime * 3) : 1;
      // Undo the glyph's girth exaggeration so the halo stays circular.
      glow.current.scale.set(pulse / GLYPH_GIRTH, pulse, 1);
      (glow.current.material as THREE.MeshBasicMaterial).opacity =
        pose.status === "stale" ? 0.1 : focused ? 0.55 : 0.3;
    }
  });

  const onSelect = (event: ThreeEvent<MouseEvent>) => {
    event.stopPropagation();
    // A pan or orbit that ends over a train isn't a tap on it.
    if (event.delta > TAP_MAX_TRAVEL_PX) return;
    navigate({ name: "follow", trainId });
  };
  const onOver = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation();
    document.body.style.cursor = "pointer";
  };
  const onOut = () => {
    document.body.style.cursor = "";
  };

  return (
    <group visible={!dimmed || focused}>
      <instancedMesh
        ref={rakeCabs}
        args={[cab, material, 2]}
        frustumCulled={false}
        onClick={onSelect}
        onPointerOver={onOver}
        onPointerOut={onOut}
      />
      <instancedMesh
        ref={rakeTrailers}
        args={[trailer, material, Math.max(coachCount - 2, 1)]}
        frustumCulled={false}
        onClick={onSelect}
        onPointerOver={onOver}
        onPointerOut={onOut}
      />
      <group ref={glyph}>
        <instancedMesh ref={glyphCabs} args={[cab, material, 2]} frustumCulled={false} />
        <mesh ref={glow} rotation-x={-Math.PI / 2} position-y={0.5}>
          <circleGeometry args={[17, 32]} />
          <meshBasicMaterial
            color={color}
            transparent
            opacity={0.32}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            toneMapped={false}
          />
        </mesh>
        {/* Invisible hit target just larger than the glyph (the glyph
            itself is thin). Counter-scaled so the girth exaggeration
            doesn't inflate it across the track. */}
        <mesh
          position-y={3}
          scale={[1 / GLYPH_GIRTH, 1 / GLYPH_GIRTH, 1]}
          onClick={onSelect}
          onPointerOver={onOver}
          onPointerOut={onOut}
        >
          <sphereGeometry args={[26, 8, 8]} />
          <meshBasicMaterial transparent opacity={0} depthWrite={false} colorWrite={false} />
        </mesh>
      </group>
    </group>
  );
}
