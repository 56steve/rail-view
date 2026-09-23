"use client";

import { useEffect, useMemo, useRef } from "react";
import { useFrame, type RootState } from "@react-three/fiber";
import { MapControls } from "@react-three/drei";
import * as THREE from "three";
import type { MapControls as MapControlsImpl } from "three-stdlib";
import { laneSample } from "@/lib/lanes";
import { trainPose } from "@/lib/motion";
import { focusedTrainId, useRailView, type CameraRequest } from "@/lib/store";
import { usePalette } from "./palette";

const OVERVIEW_POLAR = THREE.MathUtils.degToRad(40);
const MAX_POLAR_3D = THREE.MathUtils.degToRad(80);
const FOLLOW_BEHIND_M = 210;
const FOLLOW_ABOVE_M = 105;
const FOLLOW_AHEAD_M = 120;
const FOLLOW_2D_HEIGHT_M = 1500;
const TRANSITION_S = 1.2;
const CHASE_EASE_PER_S = 2.2;
const FOG_DENSITY_FACTOR = 0.22;

interface Pose {
  position: THREE.Vector3;
  target: THREE.Vector3;
}

interface Transition {
  from: Pose;
  to: () => Pose;
  elapsed: number;
}

/** Half-angle tangents of the part of the view not covered by UI. */
interface Viewport {
  tanX: number;
  tanY: number;
}

function ease(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}

function orbitPose(target: THREE.Vector3, distance: number, polar: number, azimuth: number): Pose {
  const offset = new THREE.Vector3(
    Math.sin(polar) * Math.sin(azimuth),
    Math.cos(polar),
    Math.sin(polar) * Math.cos(azimuth),
  ).multiplyScalar(distance);
  return { target: target.clone(), position: target.clone().add(offset) };
}

/** Pose that fits the given ground points in the visible viewport. */
function framePoints(points: { x: number; z: number }[], polar: number, view: Viewport): Pose | null {
  if (points.length === 0) return null;
  let minX = Infinity;
  let maxX = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;
  for (const p of points) {
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minZ = Math.min(minZ, p.z);
    maxZ = Math.max(maxZ, p.z);
  }
  const centre = new THREE.Vector3((minX + maxX) / 2, 0, (minZ + maxZ) / 2);
  const byDepth = (((maxZ - minZ) / 2) * Math.cos(polar) + 400) / view.tanY;
  const byWidth = ((maxX - minX) / 2 + 400) / view.tanX;
  return orbitPose(centre, Math.max(byDepth, byWidth, 1500) * 1.08, polar, 0);
}

function networkPose(lineCode: string | null, polar: number, view: Viewport): Pose | null {
  const { tracks, routes } = useRailView.getState();
  const selected = Object.values(routes)
    .filter((route) => lineCode === null || route.line_code === lineCode)
    .flatMap((route) => (tracks[route.route_id] ? [tracks[route.route_id]!] : []));
  return framePoints(
    selected.flatMap((t) => t.points()),
    polar,
    view,
  );
}

function followPose(trainId: string, view2D: boolean): Pose | null {
  const state = useRailView.getState();
  const pair = state.trainPairs[trainId];
  const track = pair ? state.tracks[pair.to.route_code] : undefined;
  const lanes = pair ? state.lanes[pair.to.route_code] : undefined;
  if (!pair || !track || !lanes) return null;
  const pose = trainPose(pair, performance.now());
  const s = laneSample(track, lanes, pose.forward, pose.chainage);
  const yaw = s.yaw + (pose.forward ? 0 : Math.PI);
  const forward = new THREE.Vector3(-Math.sin(yaw), 0, -Math.cos(yaw));
  const centre = new THREE.Vector3(s.x, 0, s.z);
  if (view2D) {
    return { target: centre, position: centre.clone().add(new THREE.Vector3(0, FOLLOW_2D_HEIGHT_M, 1)) };
  }
  return {
    target: centre.clone().addScaledVector(forward, FOLLOW_AHEAD_M).setY(8),
    position: centre.clone().addScaledVector(forward, -FOLLOW_BEHIND_M).setY(FOLLOW_ABOVE_M),
  };
}

/**
 * Camera behaviour for every screen:
 * - overview: frames the network / a line / a journey, with animated fly-to;
 * - follow: chase camera behind the focused train that swings round
 *   curves; if the user orbits or zooms it keeps following at their chosen
 *   angle until they recenter;
 * - 2D toggle, and projection offset so the scene centres in the part of
 *   the screen not covered by UI.
 */
export function CameraRig() {
  const controls = useRef<MapControlsImpl>(null);
  const palette = usePalette();
  const fog = useRef<THREE.FogExp2>(null);
  const rig = useRef({
    mode: "overview" as "overview" | "follow",
    followedId: null as string | null,
    transition: null as Transition | null,
    autoChase: true,
    lastTrainCentre: null as THREE.Vector3 | null,
    requestSeq: 0,
    view2D: false,
    framedNetwork: false,
    viewKey: "",
    view: { tanX: 1, tanY: 1 } as Viewport,
  });
  const carry = useMemo(() => new THREE.Vector3(), []);
  const initialTarget = useMemo(() => new THREE.Vector3(0, 0, 0), []);

  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    const onStart = () => {
      rig.current.transition = null;
      rig.current.autoChase = false;
    };
    c.addEventListener("start", onStart);
    return () => c.removeEventListener("start", onStart);
  }, []);

  useFrame((frame: RootState, delta: number) => {
    const c = controls.current;
    const camera = frame.camera as THREE.PerspectiveCamera;
    if (!c) return;
    const state = useRailView.getState();
    const r = rig.current;
    const { size } = frame;
    const { left, top, bottom } = state.viewInsets;
    // Shift the projection centre into the clear area: widening the full
    // frustum and rendering only a sub-window of it moves the principal
    // point without distorting the image.
    const fullWidth = size.width + left;
    const fullHeight = size.height + Math.abs(top - bottom);
    const tanFull = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
    const view: Viewport = {
      tanX: tanFull * (fullWidth / Math.max(fullHeight, 1)) * (Math.max(size.width - left, 1) / fullWidth),
      tanY: tanFull * (Math.max(size.height - top - bottom, 1) / fullHeight),
    };
    r.view = view;
    const polar = () => (r.view2D ? 0.0001 : OVERVIEW_POLAR);

    const startTransition = (to: () => Pose | null) => {
      const first = to();
      if (!first) return;
      let last = first;
      r.transition = {
        from: { position: camera.position.clone(), target: c.target.clone() },
        to: () => (last = to() ?? last),
        elapsed: 0,
      };
    };

    const requestToPose = (request: CameraRequest): (() => Pose | null) | null => {
      switch (request.kind) {
        case "frame-network":
          return () => networkPose(request.lineCode, polar(), r.view);
        case "frame-points":
          return () => framePoints(request.points, polar(), r.view);
        case "focus-point":
          return () => orbitPose(new THREE.Vector3(request.x, 0, request.z), request.distance, polar(), 0);
        case "recenter-follow": {
          r.autoChase = true;
          const id = r.followedId;
          return id ? () => followPose(id, r.view2D) : null;
        }
      }
    };

    const key = `${size.width}x${size.height}:${left},${top},${bottom}`;
    if (key !== r.viewKey) {
      r.viewKey = key;
      camera.aspect = fullWidth / Math.max(fullHeight, 1);
      camera.setViewOffset(fullWidth, fullHeight, 0, Math.max(bottom - top, 0), size.width, size.height);
      camera.updateProjectionMatrix();
    }

    if (!r.framedNetwork && Object.keys(state.tracks).length > 0) {
      r.framedNetwork = true;
      startTransition(() => networkPose(state.lineFilter, polar(), r.view));
    }

    const trainId = focusedTrainId(state);
    const mode = trainId && state.trainPairs[trainId] ? "follow" : "overview";
    if (mode !== r.mode || (mode === "follow" && trainId !== r.followedId)) {
      r.mode = mode;
      r.followedId = mode === "follow" ? trainId : null;
      r.autoChase = true;
      r.lastTrainCentre = null;
      startTransition(
        mode === "follow" ? () => followPose(trainId!, r.view2D) : () => networkPose(state.lineFilter, polar(), r.view),
      );
    }

    if (state.view2D !== r.view2D) {
      r.view2D = state.view2D;
      c.maxPolarAngle = r.view2D ? 0.0001 : MAX_POLAR_3D;
      if (r.mode === "follow" && r.followedId) {
        const id = r.followedId;
        r.autoChase = true;
        startTransition(() => followPose(id, r.view2D));
      } else {
        const target = c.target.clone();
        const distance = camera.position.distanceTo(target);
        startTransition(() => orbitPose(target, distance, polar(), 0));
      }
    }

    if (state.cameraRequest && state.cameraRequest.seq !== r.requestSeq) {
      r.requestSeq = state.cameraRequest.seq;
      const to = requestToPose(state.cameraRequest.request);
      if (to) startTransition(to);
    }

    if (r.mode === "follow" && r.followedId) {
      const ideal = followPose(r.followedId, r.view2D);
      if (ideal) {
        const centre = ideal.target;
        if (r.lastTrainCentre && !r.transition) {
          // Carry the camera along with the train, preserving whatever
          // angle and zoom the user has chosen.
          carry.copy(centre).sub(r.lastTrainCentre);
          camera.position.add(carry);
          c.target.add(carry);
          if (r.autoChase) {
            const k = 1 - Math.exp(-CHASE_EASE_PER_S * delta);
            camera.position.lerp(ideal.position, k);
            c.target.lerp(ideal.target, k);
          }
        }
        r.lastTrainCentre = centre.clone();
      }
    }

    if (r.transition) {
      const t = r.transition;
      t.elapsed += delta;
      const k = ease(Math.min(t.elapsed / TRANSITION_S, 1));
      const to = t.to();
      camera.position.lerpVectors(t.from.position, to.position, k);
      c.target.lerpVectors(t.from.target, to.target, k);
      if (t.elapsed >= TRANSITION_S) r.transition = null;
    }

    const distance = camera.position.distanceTo(c.target);
    if (fog.current) fog.current.density = FOG_DENSITY_FACTOR / Math.max(distance, 250);
    c.minDistance = r.mode === "follow" ? 40 : 300;
    c.update();
  });

  return (
    <>
      <fogExp2 ref={fog} attach="fog" args={[palette.fog, 0.00001]} />
      <MapControls
        ref={controls}
        makeDefault
        target={initialTarget}
        enableDamping
        dampingFactor={0.12}
        screenSpacePanning={false}
        maxDistance={90_000}
        maxPolarAngle={MAX_POLAR_3D}
        zoomSpeed={1.1}
      />
    </>
  );
}
