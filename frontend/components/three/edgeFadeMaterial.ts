import * as THREE from "three";
import type { SceneBounds } from "@/lib/environment";

/**
 * An unlit, flat-coloured material whose opacity falls to zero across
 * the last `fadeM` metres inside `bounds`, so a layer with a finite data
 * extent (land cover, roads) blends into plain land instead of ending at
 * a hard rectangle. Ground layers are unlit on purpose: they are map
 * colours, and a low evening sun shouldn't turn a park grey.
 */
export function edgeFadeMaterial(color: string, bounds: SceneBounds, fadeM: number): THREE.MeshBasicMaterial {
  // Double-sided: the build's triangulation doesn't guarantee a winding,
  // and flat ground has no back to hide anyway.
  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const uniforms = {
    uFadeBounds: { value: new THREE.Vector4(bounds.minX, bounds.maxX, bounds.minZ, bounds.maxZ) },
    uFadeWidth: { value: fadeM },
  };
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec2 vFadeXZ;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvFadeXZ = (modelMatrix * vec4(transformed, 1.0)).xz;");
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        "#include <common>\nvarying vec2 vFadeXZ;\nuniform vec4 uFadeBounds;\nuniform float uFadeWidth;",
      )
      .replace(
        "#include <color_fragment>",
        `#include <color_fragment>
        float fadeEdge = min(
          min(vFadeXZ.x - uFadeBounds.x, uFadeBounds.y - vFadeXZ.x),
          min(vFadeXZ.y - uFadeBounds.z, uFadeBounds.w - vFadeXZ.y)
        );
        diffuseColor.a *= smoothstep(0.0, uFadeWidth, fadeEdge);`,
      );
  };
  material.customProgramCacheKey = () => "rv-edge-fade";
  return material;
}
