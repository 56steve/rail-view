// Screen-space labels anchored to 3D points (station names, the next
// station pin). Labels are ordinary DOM elements rendered outside the
// canvas - crisp text, no font download inside WebGL - and a projector
// running in the render loop (components/three/OverlayProjector.tsx)
// moves them every frame by writing styles directly, so camera motion
// never triggers React re-renders.

export interface OverlayAnchor {
  element: HTMLElement;
  x: number;
  y: number;
  z: number;
  /** Hidden when the camera is farther than this from the anchor. */
  maxDistance: number;
}

const anchors = new Map<string, OverlayAnchor>();

export function registerAnchor(id: string, anchor: OverlayAnchor): void {
  anchors.set(id, anchor);
}

export function unregisterAnchor(id: string): void {
  anchors.delete(id);
}

export function moveAnchor(id: string, x: number, y: number, z: number): void {
  const anchor = anchors.get(id);
  if (anchor) {
    anchor.x = x;
    anchor.y = y;
    anchor.z = z;
  }
}

export function allAnchors(): IterableIterator<OverlayAnchor> {
  return anchors.values();
}
