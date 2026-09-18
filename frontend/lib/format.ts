export function formatEta(etaSeconds: number | null): string {
  if (etaSeconds == null) return "--";
  const minutes = Math.round(etaSeconds / 60);
  if (minutes <= 0) return "Arriving";
  return `${minutes} min`;
}

export function formatDelay(delaySeconds: number): string {
  const minutes = Math.round(Math.abs(delaySeconds) / 60);
  if (minutes === 0) return "On time";
  return delaySeconds > 0 ? `Running ${minutes} min late` : `Running ${minutes} min early`;
}

export function formatLastUpdated(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatSpeed(speedKmh: number): string {
  return `${Math.round(speedKmh)} km/h`;
}

export function delayTone(delaySeconds: number): "on-time" | "late" | "early" {
  const minutes = Math.round(Math.abs(delaySeconds) / 60);
  if (minutes === 0) return "on-time";
  return delaySeconds > 0 ? "late" : "early";
}
