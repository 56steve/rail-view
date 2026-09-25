import { useRailView, type SceneMode } from "@/lib/store";

// Scene colours. Kept separate from the UI tokens in app/globals.css
// because lit 3D surfaces need different values than flat UI to read the
// same on screen. Day colours are the real ones - mangrove, maidan grass,
// beach sand, concrete - toned so trains and route lines still lead;
// night keeps the same land use as quiet tints on a dark canvas.

/** Land cover classes, in the order backend/scripts/build_osm_data.py
 * writes them to landcover.bin. */
export const LANDCOVER_CLASSES = [
  "residential",
  "commercial",
  "industrial",
  "grass",
  "farmland",
  "scrub",
  "forest",
  "wetland",
  "mangrove",
  "sand",
] as const;
export type LandcoverClass = (typeof LANDCOVER_CLASSES)[number];

/** Road classes, in the order written to roads.bin (links fold into
 * their parent class). */
export const ROAD_CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary", "minor"] as const;
export type RoadClass = (typeof ROAD_CLASSES)[number];

/** Close-up track. Ballast is a tint over a neutral stone texture. */
export interface TrackPalette {
  ballast: string;
  sleeper: string;
  rail: string;
  railHead: string;
  fastening: string;
}

export interface ScenePalette {
  background: string;
  fog: string;
  sea: string;
  land: string;
  inlandWater: string;
  landcover: Record<LandcoverClass, string>;
  roads: Record<RoadClass, string>;
  buildingBase: string;
  buildingTop: string;
  roof: string;
  platform: string;
  track: TrackPalette;
  skyLight: string;
  groundLight: string;
  hemisphereIntensity: number;
  sun: string;
  sunIntensity: number;
  ambientIntensity: number;
}

const NIGHT: ScenePalette = {
  background: "#05070B",
  fog: "#05070B",
  sea: "#050A12",
  land: "#161B24",
  inlandWater: "#0A1320",
  landcover: {
    residential: "#171C25",
    commercial: "#191D27",
    industrial: "#181B24",
    grass: "#15211D",
    farmland: "#181E1B",
    scrub: "#171E1C",
    forest: "#122019",
    wetland: "#101C1D",
    mangrove: "#0F1E1A",
    sand: "#242320",
  },
  roads: {
    motorway: "#2D3443",
    trunk: "#2A3140",
    primary: "#272E3C",
    secondary: "#242B38",
    tertiary: "#222834",
    minor: "#1F2530",
  },
  buildingBase: "#1A202A",
  buildingTop: "#323B4C",
  roof: "#3D4659",
  platform: "#8C939E",
  track: {
    ballast: "#6F6A64",
    sleeper: "#7A7874",
    rail: "#4A3A30",
    railHead: "#B9C0C8",
    fastening: "#202328",
  },
  skyLight: "#9FB3D9",
  groundLight: "#0B0E14",
  hemisphereIntensity: 0.75,
  sun: "#F2F4FA",
  sunIntensity: 1.35,
  ambientIntensity: 0.18,
};

const DAY: ScenePalette = {
  background: "#C9D6E2",
  fog: "#CBD7E2",
  sea: "#7FA4BF",
  land: "#E2DCCF",
  inlandWater: "#8AAFC8",
  landcover: {
    residential: "#E0D9CB",
    commercial: "#E4D8CC",
    industrial: "#D9D5D0",
    grass: "#BCD49C",
    farmland: "#D8D9A8",
    scrub: "#C7CC9C",
    forest: "#93B783",
    wetland: "#A9C3A6",
    mangrove: "#86A889",
    sand: "#EEDFB9",
  },
  roads: {
    motorway: "#F6D48E",
    trunk: "#FBE3A6",
    primary: "#FFFFFF",
    secondary: "#FFFFFF",
    tertiary: "#FBFAF7",
    minor: "#F6F4EF",
  },
  buildingBase: "#CFC9BE",
  buildingTop: "#EDE9E2",
  roof: "#F3F0EA",
  platform: "#B8B1A5",
  track: {
    ballast: "#A39A8E",
    sleeper: "#A9A59E",
    rail: "#7A5641",
    railHead: "#E6EAEE",
    fastening: "#2E3136",
  },
  skyLight: "#E4EEF8",
  groundLight: "#B5AC9C",
  hemisphereIntensity: 1.1,
  sun: "#FFF4E2",
  sunIntensity: 2.1,
  ambientIntensity: 0.3,
};

export const PALETTES: Record<SceneMode, ScenePalette> = { day: DAY, night: NIGHT };

export function usePalette(): ScenePalette {
  return PALETTES[useRailView((s) => s.lighting.mode)];
}
