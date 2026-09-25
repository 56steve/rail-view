# Close-up 3D track

Status: approved 2026-09-25 (approach A: real track near the camera, the
existing strip further away; overhead electrics come in a later pass).

## Why

Up close, the tracks are a flat ribbon with a 64x128 canvas texture
stretched over it: ballast, sleepers and rails painted on. Next to the
detailed Blender EMU in the Follow view it reads as a blurry dark strip.
The target look is the Blender mock-up (`track_close.png`,
`track_with_train.png`): a raised ballast bed, concrete sleepers with
clips, and real rails with polished tops.

## What it looks like

Indian Railways broad gauge, per track:

| Part | Size |
| --- | --- |
| Gauge (inner faces of the rail heads) | 1.676 m |
| Rail (60 kg): height / head / foot / web | 0.172 / 0.072 / 0.150 / 0.016 m |
| Rail pad under each rail | 0.01 m |
| PSC sleeper (L x W x H), spacing | 2.75 x 0.25 x 0.21 m, every 0.60 m |
| Rail clips | two per rail per sleeper, 0.05 x 0.10 x 0.04 m |
| Ballast bed | top 0.35 m past the sleeper ends, 1.5:1 side slopes, ~0.3 m under the sleepers |

Heights, in scene metres: the formation (ballast foot) sits on the ground
at `y = 0.02`; the rail tops are at `RAIL_TOP_Y` (about 0.72). **Trains
are raised to `RAIL_TOP_Y`** (today they are drawn at 0 with the strip at
0.4), so wheels sit on the rails. `RAIL_TOP_Y` is one exported constant
used by both the track and `Trains.tsx`.

Materials (MeshStandardMaterial, Day and Night palettes):
- Ballast: a 512 px canvas stone texture generated in the browser
  (deterministic), repeating about every 1.5 m, grey-brown.
- Sleepers: concrete grey, rough.
- Rails: rust-brown sides; a separate thin polished-steel strip on the
  running surface.
- Clips: dark steel.

## How it's built

**Tiling.** On load, the track polylines from `tracks.bin` are cut into
square tiles of `TILE_SIZE_M = 500` (a polyline crossing a tile edge is
split there, with a shared point so nothing gaps).

**Near the camera only.** Each frame (throttled), the set of tiles within
`DETAIL_RADIUS_M` (~700 m) of the camera's ground point is computed, only
while the camera is below `DETAIL_MAX_HEIGHT_M` (~400 m). Tiles entering
the set are queued and built **at most one per frame**; tiles leaving it
are disposed (geometry and instance buffers). Nothing is built above that
height, so the network view costs nothing new.

**Per tile, three draw calls:**
1. Ballast: the trapezoid profile swept along each polyline (merged).
2. Rails: the rail profile swept along both rails of each polyline, plus
   the polished head strips (merged; one material each).
3. Sleepers and clips: `InstancedMesh`es, one sleeper every 0.6 m along
   each polyline, rotated to the local heading.

Sweeping: offset along per-vertex normals (the same corner-averaged
normals `trackGeometry.ts` already uses for ribbons), so curves stay
continuous.

**Far away:** the existing ballast ribbon stays as the far layer (lowered
under the 3D bed so it never shows through), and above city height only
the coloured route lines, as now.

## Code layout

- `lib/trackDetail/profiles.ts`: rail and ballast profiles, dimensions.
- `lib/trackDetail/sweep.ts`: sweep a 2D profile along a polyline.
- `lib/trackDetail/tiles.ts`: split polylines into tiles; which tiles are
  near a point.
- `lib/trackDetail/sleepers.ts`: sleeper/clip transforms along a polyline.
- `components/three/TrackDetail.tsx`: the tile manager (queue, build one
  per frame, dispose) and the materials.
- `RailLines.tsx` keeps the route glow, the far ribbon and platforms, and
  mounts `TrackDetail`.

Pure functions in `lib/trackDetail/` are unit-tested (tiling splits
polylines exactly at tile edges; sweep vertex counts and normals; sleeper
spacing along curves).

## Checks

- `npm run lint`, `npx tsc --noEmit`, `npm run build`, unit tests.
- Browser: the Follow view close-up (train on the rails, no gaps at
  tile edges), a multi-track station yard (Kurla, Thane), zooming out
  (detail drops away cleanly), Day and Night, and a phone-sized viewport
  (no stutter while panning along the line).
