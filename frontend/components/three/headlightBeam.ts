import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { LampAnchors } from "./emuModel";

// Night-time headlights for the leading cab of a train: a soft cone of
// light down the line ahead, a pool of light on the track it falls on, and
// a glow on the lamps. Everything is additive and unlit (light added on top
// of the scene), shared by every train, and only the driving end in the
// direction of travel gets it, as on the real trains.
//
// Positions are in a cab coach's local frame (x across, y up from rail
// level, the front at -z), from the lamp markers in the EMU model.

const BEAM_LENGTH_M = 75;
const BEAM_HALF_ANGLE_RAD = THREE.MathUtils.degToRad(7);
const BEAM_APEX_RADIUS_M = 0.28;
/** The beam dips to reach the rails about this far ahead. */
const BEAM_REACH_M = 70;
const POOL_WIDTH_M = 8;
const POOL_LENGTH_M = 55;
const POOL_NEAR_M = 4; // gap between the front of the cab and the pool
const LAMP_GLOW_SIZE_M = 1.1;
const WARM_WHITE = new THREE.Color("#FFE9C2");

/** The beam cone, pointing along -z from its apex at the origin, with an
 * `along` attribute running 0 at the apex to 1 at the far end. */
function beamGeometry(): THREE.BufferGeometry {
  const farRadius = BEAM_APEX_RADIUS_M + Math.tan(BEAM_HALF_ANGLE_RAD) * BEAM_LENGTH_M;
  const geometry = new THREE.CylinderGeometry(BEAM_APEX_RADIUS_M, farRadius, BEAM_LENGTH_M, 32, 1, true);
  geometry.translate(0, -BEAM_LENGTH_M / 2, 0);
  geometry.rotateX(Math.PI / 2);
  const position = geometry.getAttribute("position");
  const along = new Float32Array(position.count);
  for (let i = 0; i < position.count; i++) along[i] = -position.getZ(i) / BEAM_LENGTH_M;
  geometry.setAttribute("along", new THREE.BufferAttribute(along, 1));
  return geometry;
}

/** Bright near the lamp and fading to nothing down the line; brightest
 * where you look across the cone's middle, soft at its edges. */
function beamMaterial(intensity: number): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: { uColor: { value: WARM_WHITE }, uIntensity: { value: intensity } },
    vertexShader: /* glsl */ `
      attribute float along;
      varying float vAlong;
      varying vec3 vNormal;
      varying vec3 vView;
      void main() {
        vAlong = along;
        vec4 view = modelViewMatrix * vec4(position, 1.0);
        vView = -view.xyz;
        vNormal = normalMatrix * normal;
        gl_Position = projectionMatrix * view;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor;
      uniform float uIntensity;
      varying float vAlong;
      varying vec3 vNormal;
      varying vec3 vView;
      void main() {
        float facing = abs(dot(normalize(vNormal), normalize(vView)));
        float fade = pow(1.0 - vAlong, 2.4) * smoothstep(0.0, 0.03, vAlong);
        gl_FragColor = vec4(uColor * uIntensity * pow(facing, 1.5) * fade, 1.0);
      }
    `,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    toneMapped: false,
  });
}

/** An elliptical radial gradient, white centre to transparent edge. */
function gradientTexture(width: number, height: number): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas unavailable for the headlight glow");
  ctx.setTransform(width / 2, 0, 0, height / 2, width / 2, height / 2);
  const gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.35, "rgba(255,255,255,0.45)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(-1, -1, 2, 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** The pool of light on the track ahead, lying flat, its near edge
 * POOL_NEAR_M in front of the foremost lamp. */
function poolGeometry(lamps: LampAnchors): THREE.BufferGeometry {
  const front = Math.min(lamps.top.z, lamps.left.z, lamps.right.z);
  const geometry = new THREE.PlaneGeometry(POOL_WIDTH_M, POOL_LENGTH_M);
  geometry.rotateX(-Math.PI / 2);
  geometry.translate(0, 0.03, front - POOL_NEAR_M - POOL_LENGTH_M / 2);
  return geometry;
}

/** A small glowing disc facing forward just in front of each lamp. */
function lampGlowGeometry(lamps: LampAnchors): THREE.BufferGeometry {
  const quads = [lamps.top, lamps.left, lamps.right].map(({ x, y, z }) =>
    new THREE.PlaneGeometry(LAMP_GLOW_SIZE_M, LAMP_GLOW_SIZE_M).translate(x, y, z - 0.04),
  );
  const merged = mergeGeometries(quads);
  for (const quad of quads) quad.dispose();
  if (!merged) throw new Error("Headlight lamp glows could not be merged");
  return merged;
}

function glowMaterial(map: THREE.Texture, opacity: number): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    map,
    color: WARM_WHITE,
    transparent: true,
    opacity,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    toneMapped: false,
  });
}

export interface HeadlightResources {
  beam: THREE.BufferGeometry;
  pool: THREE.BufferGeometry;
  lampGlow: THREE.BufferGeometry;
  beamMaterial: THREE.ShaderMaterial;
  /** Dimmer, for a train whose position has gone stale. */
  staleBeamMaterial: THREE.ShaderMaterial;
  /** Fainter, for the far-away glyph. */
  glyphBeamMaterial: THREE.ShaderMaterial;
  poolMaterial: THREE.MeshBasicMaterial;
  lampGlowMaterial: THREE.MeshBasicMaterial;
  /** Where the beam's apex sits and how it dips, in the cab's frame. */
  beamOrigin: THREE.Vector3;
  beamDip: number;
}

const shared = new WeakMap<LampAnchors, HeadlightResources>();

/** One set of headlight geometry and materials for every train, for the
 * model's lamps. They live as long as the page, like the model. */
export function headlightResources(lamps: LampAnchors): HeadlightResources {
  const cached = shared.get(lamps);
  if (cached) return cached;
  const poolTexture = gradientTexture(64, 256);
  const lampTexture = gradientTexture(64, 64);
  const resources: HeadlightResources = {
    beam: beamGeometry(),
    pool: poolGeometry(lamps),
    lampGlow: lampGlowGeometry(lamps),
    beamMaterial: beamMaterial(1.1),
    staleBeamMaterial: beamMaterial(0.35),
    glyphBeamMaterial: beamMaterial(0.35),
    poolMaterial: glowMaterial(poolTexture, 0.75),
    lampGlowMaterial: glowMaterial(lampTexture, 0.95),
    beamOrigin: lamps.top.clone().setZ(lamps.top.z - 0.08),
    beamDip: Math.atan(lamps.top.y / BEAM_REACH_M),
  };
  shared.set(lamps, resources);
  return resources;
}
