import { useEffect, useMemo } from "react";
import { useThree } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import type { CoachKind } from "./coachGeometry";

// The Mumbai EMU, built in Blender by models/emu/build_emu.py (--app-out)
// and meshopt-compressed. Each coach kind comes in both liveries (the
// non-AC rakes and the stainless AC ones), each at two levels of detail:
// `<coach>_lod0` in full for coaches near the camera, `<coach>_lod1`
// simplified for the rest of a rake. Their colours live on the vertices,
// so each is only a few materials: Paint and Metal (vertex-coloured),
// Glass, and the lamps and destination boards, which light up at night.
// Empties `lamp_top`, `lamp_left` and `lamp_right` mark the cab's lamps.
// Frame: metres, y up from rail level, front of the coach at -z.

export const EMU_MODEL_URL = "/models/emu.glb";

export type RakeLivery = "nonac" | "ac";

const LIVERIES: readonly RakeLivery[] = ["nonac", "ac"];
const COACH_KINDS: readonly CoachKind[] = ["cab", "motor", "trailer"];

export function rakeLivery(ac: boolean): RakeLivery {
  return ac ? "ac" : "nonac";
}

/** Materials that glow: brighter at night, when the lamps are on. */
const LIT_MATERIALS: Record<string, { day: number; night: number }> = {
  Headlight: { day: 0.6, night: 4 },
  AmberLight: { day: 0.4, night: 2 },
  TailLight: { day: 0.4, night: 2.5 },
  DestinationText: { day: 1, night: 2.2 },
  DestinationBoard: { day: 0, night: 0.25 },
};

export const LOD_COUNT = 2;
export type CoachLod = 0 | 1;

export interface CoachPart {
  geometry: THREE.BufferGeometry;
  material: THREE.Material;
}

export interface LampAnchors {
  top: THREE.Vector3;
  left: THREE.Vector3;
  right: THREE.Vector3;
}

/** Per coach kind, per level of detail, the meshes that make it up. */
export type RakeParts = Record<CoachKind, CoachPart[][]>;

export interface EmuModel {
  parts: Record<RakeLivery, RakeParts>;
  lamps: LampAnchors;
}

export class EmuModelError extends Error {}

/** A float copy of a quantized attribute. The file stores positions and
 * normals as normalized integers, with the node's scale restoring their
 * size, so transforming them in place would clamp every value to ±1. */
function toFloat(attribute: THREE.BufferAttribute | THREE.InterleavedBufferAttribute): THREE.BufferAttribute {
  const { count, itemSize } = attribute;
  const values = new Float32Array(count * itemSize);
  for (let i = 0; i < count; i++) {
    for (let c = 0; c < itemSize; c++) values[i * itemSize + c] = attribute.getComponent(i, c);
  }
  return new THREE.BufferAttribute(values, itemSize);
}

/** The mesh's geometry with its transform applied, in the coach frame. */
function bakedGeometry(mesh: THREE.Mesh): THREE.BufferGeometry {
  const geometry = (mesh.geometry as THREE.BufferGeometry).clone();
  for (const name of ["position", "normal"]) {
    const attribute = geometry.getAttribute(name);
    if (attribute) geometry.setAttribute(name, toFloat(attribute));
  }
  return geometry.applyMatrix4(mesh.matrixWorld);
}

function coachParts(root: THREE.Object3D, nodeName: string): CoachPart[] {
  const node = root.getObjectByName(nodeName);
  if (!node) throw new EmuModelError(`emu.glb has no "${nodeName}"`);
  const parts: CoachPart[] = [];
  node.traverse((object) => {
    if (object instanceof THREE.Mesh) {
      // Baked into the coach frame, so instances only need their own matrix.
      const geometry = bakedGeometry(object);
      parts.push({ geometry, material: object.material as THREE.Material });
    }
  });
  if (parts.length === 0) throw new EmuModelError(`emu.glb: "${nodeName}" has no meshes`);
  return parts;
}

function anchor(root: THREE.Object3D, name: string): THREE.Vector3 {
  const node = root.getObjectByName(name);
  if (!node) throw new EmuModelError(`emu.glb has no "${name}" marker`);
  return node.getWorldPosition(new THREE.Vector3());
}

/** Read the coaches and lamp markers out of the loaded glTF scene. */
export function readEmuModel(root: THREE.Object3D): EmuModel {
  root.updateMatrixWorld(true);
  const rake = (livery: RakeLivery): RakeParts =>
    Object.fromEntries(
      COACH_KINDS.map((kind) => [kind, [0, 1].map((lod) => coachParts(root, `coach_${kind}_${livery}_lod${lod}`))]),
    ) as RakeParts;
  const parts = Object.fromEntries(LIVERIES.map((livery) => [livery, rake(livery)])) as Record<RakeLivery, RakeParts>;
  return { parts, lamps: { top: anchor(root, "lamp_top"), left: anchor(root, "lamp_left"), right: anchor(root, "lamp_right") } };
}

/** Point standard materials at a reflection map. */
function applyReflections(materials: readonly THREE.Material[], environment: THREE.Texture, intensity: number): void {
  for (const material of materials) {
    if (!(material instanceof THREE.MeshStandardMaterial)) continue;
    material.envMap = environment;
    material.envMapIntensity = intensity;
    material.needsUpdate = true;
  }
}

/** Turn the lamps and destination boards up at night, down by day. */
function applyLampBrightness(materials: readonly THREE.Material[], night: boolean): void {
  for (const material of materials) {
    const lit = LIT_MATERIALS[material.name];
    if (lit && material instanceof THREE.MeshStandardMaterial) material.emissiveIntensity = night ? lit.night : lit.day;
  }
}

function modelMaterials(model: EmuModel): THREE.Material[] {
  return [
    ...new Set(
      Object.values(model.parts).flatMap((rake) =>
        Object.values(rake).flatMap((lods) => lods.flatMap((parts) => parts.map((p) => p.material))),
      ),
    ),
  ];
}

/**
 * Gives standard materials a small studio reflection map from this
 * canvas's renderer. The scenes have none, and without one metal reads flat
 * black. The map belongs to one renderer, so a second canvas needs its own
 * copies of the materials.
 */
export function useStudioReflections(materials: readonly THREE.Material[], intensity = 0.55): void {
  const gl = useThree((state) => state.gl);
  const invalidate = useThree((state) => state.invalidate);
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    const environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    applyReflections(materials, environment, intensity);
    // On-demand canvases would otherwise keep the frame drawn without it.
    invalidate();
    return () => {
      environment.dispose();
      pmrem.dispose();
    };
  }, [gl, invalidate, materials, intensity]);
}

/**
 * The EMU model, ready to instance. Suspends while it loads. Gives the
 * train's materials a small studio reflection map (the scene has none, and
 * without one the metal reads flat black), and turns the lamps and
 * destination boards up at night.
 */
export function useEmuModel(night: boolean): EmuModel {
  const gltf = useGLTF(EMU_MODEL_URL, false, true);
  const model = useMemo(() => readEmuModel(gltf.scene), [gltf]);
  const materials = useMemo(() => modelMaterials(model), [model]);
  useStudioReflections(materials);

  useEffect(() => applyLampBrightness(materials, night), [materials, night]);

  return model;
}

useGLTF.preload(EMU_MODEL_URL, false, true);
