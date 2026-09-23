// Trains run on Indian Standard Time regardless of where the viewer is,
// so clock times are always rendered in Asia/Kolkata.
const clockFormatter = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

export function formatClock(epochSeconds: number): string {
  return clockFormatter.format(new Date(epochSeconds * 1000)).toUpperCase();
}

export function minutesUntil(epochSeconds: number, nowSeconds: number): number {
  return Math.max(0, Math.round((epochSeconds - nowSeconds) / 60));
}

export function formatMinutesAway(epochSeconds: number, nowSeconds: number): string {
  const minutes = minutesUntil(epochSeconds, nowSeconds);
  return minutes === 0 ? "Now" : `${minutes} min away`;
}

export function formatEta(seconds: number | null): string {
  if (seconds == null) return "—";
  const minutes = Math.round(seconds / 60);
  return minutes <= 0 ? "Now" : `${minutes} min`;
}

/** "Next Dadar in 3 min", or "Arriving at Dadar" within the last minute. */
export function formatNextStop(stationName: string, etaSeconds: number | null): string {
  if (etaSeconds !== null && etaSeconds < 45) return `Arriving at ${stationName}`;
  return `Next ${stationName} in ${formatEta(etaSeconds)}`;
}

export function formatDuration(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes % 60} min`;
}

export type DelayTone = "on-time" | "late" | "early";

export function delayTone(delaySeconds: number): DelayTone {
  if (Math.abs(delaySeconds) < 60) return "on-time";
  return delaySeconds > 0 ? "late" : "early";
}

export function formatDelay(delaySeconds: number): string {
  const tone = delayTone(delaySeconds);
  if (tone === "on-time") return "On time";
  const minutes = Math.round(Math.abs(delaySeconds) / 60);
  return tone === "late" ? `${minutes} min late` : `${minutes} min early`;
}

export function formatSpeed(speedKmh: number): string {
  return `${Math.round(speedKmh)}`;
}

export function formatDistance(metres: number): string {
  return metres < 1000 ? `${Math.round(metres / 10) * 10} m` : `${(metres / 1000).toFixed(1)} km`;
}

export function trainTypeLabel(trainType: "FAST" | "SLOW"): string {
  return trainType === "FAST" ? "Fast Local" : "Slow Local";
}
