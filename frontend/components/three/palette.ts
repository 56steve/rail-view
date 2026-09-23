// Scene colours. Kept separate from the UI tokens in app/globals.css
// because lit 3D surfaces need different values than flat UI to read
// the same on screen.
export const SCENE = {
  background: "#05070B",
  sea: "#050A12",
  land: "#161B24",
  inlandWater: "#0A1320",
  buildingBase: "#1A202A",
  buildingTop: "#323B4C",
  roof: "#3D4659",
  platform: "#8C939E",
  skyLight: "#9FB3D9",
  groundLight: "#0B0E14",
  sun: "#F2F4FA",
} as const;
