// Where the sun is over Mumbai right now, from the NOAA solar position
// equations (accurate to well under a degree - plenty for lighting a map
// and deciding whether it's day).

import { ORIGIN_LAT, ORIGIN_LON } from "./geo";

export interface SunPosition {
  /** Degrees above the horizon (negative once it has set). */
  elevationDeg: number;
  /** Compass bearing in degrees: 0 = north, 90 = east. */
  azimuthDeg: number;
}

const DEG = Math.PI / 180;

export function sunPosition(date: Date, lat = ORIGIN_LAT, lon = ORIGIN_LON): SunPosition {
  const julianDay = date.getTime() / 86_400_000 + 2440587.5;
  const t = (julianDay - 2451545) / 36525; // Julian centuries since J2000

  const meanLongitude = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360;
  const meanAnomaly = 357.52911 + t * (35999.05029 - 0.0001537 * t);
  const eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t);
  const centre =
    Math.sin(meanAnomaly * DEG) * (1.914602 - t * (0.004817 + 0.000014 * t)) +
    Math.sin(2 * meanAnomaly * DEG) * (0.019993 - 0.000101 * t) +
    Math.sin(3 * meanAnomaly * DEG) * 0.000289;
  const trueLongitude = meanLongitude + centre;
  const omega = 125.04 - 1934.136 * t;
  const apparentLongitude = trueLongitude - 0.00569 - 0.00478 * Math.sin(omega * DEG);
  const meanObliquity = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60;
  const obliquity = meanObliquity + 0.00256 * Math.cos(omega * DEG);
  const declination = Math.asin(Math.sin(obliquity * DEG) * Math.sin(apparentLongitude * DEG));

  const y = Math.tan((obliquity / 2) * DEG) ** 2;
  const equationOfTimeMin =
    4 *
    (y * Math.sin(2 * meanLongitude * DEG) -
      2 * eccentricity * Math.sin(meanAnomaly * DEG) +
      4 * eccentricity * y * Math.sin(meanAnomaly * DEG) * Math.cos(2 * meanLongitude * DEG) -
      0.5 * y * y * Math.sin(4 * meanLongitude * DEG) -
      1.25 * eccentricity * eccentricity * Math.sin(2 * meanAnomaly * DEG)) /
    DEG;

  const utcMinutes = date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60;
  const trueSolarMinutes = (((utcMinutes + equationOfTimeMin + 4 * lon) % 1440) + 1440) % 1440;
  const hourAngle = trueSolarMinutes / 4 - 180;

  const latRad = lat * DEG;
  const cosZenith =
    Math.sin(latRad) * Math.sin(declination) + Math.cos(latRad) * Math.cos(declination) * Math.cos(hourAngle * DEG);
  const zenith = Math.acos(Math.min(Math.max(cosZenith, -1), 1));
  const azimuth =
    Math.atan2(
      Math.sin(hourAngle * DEG),
      Math.cos(hourAngle * DEG) * Math.sin(latRad) - Math.tan(declination) * Math.cos(latRad),
    ) /
      DEG +
    180;

  return { elevationDeg: 90 - zenith / DEG, azimuthDeg: azimuth % 360 };
}

/** Unit vector pointing from the ground towards the sun, in scene space
 * (x = east, y = up, z = -north). */
export function sunDirection(sun: SunPosition): [number, number, number] {
  const el = sun.elevationDeg * DEG;
  const az = sun.azimuthDeg * DEG;
  return [Math.sin(az) * Math.cos(el), Math.sin(el), -Math.cos(az) * Math.cos(el)];
}
