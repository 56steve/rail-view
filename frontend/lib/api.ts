import type { JourneyPlan, JourneySort, NetworkOut, ServiceDay, StationIndexEntry, TrainDetail } from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/live";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
  ) {
    super(`RailView API ${path} responded ${status}`);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal, cache: "no-store" });
  if (!response.ok) throw new ApiError(response.status, path);
  return (await response.json()) as T;
}

export function fetchNetwork(signal?: AbortSignal): Promise<NetworkOut> {
  return getJson<NetworkOut>("/api/network", signal);
}

export function fetchStations(signal?: AbortSignal): Promise<StationIndexEntry[]> {
  return getJson<StationIndexEntry[]>("/api/stations", signal);
}

export function fetchServiceDay(signal?: AbortSignal): Promise<ServiceDay> {
  return getJson<ServiceDay>("/api/service-day", signal);
}

export function fetchTrainDetail(trainId: string, signal?: AbortSignal): Promise<TrainDetail> {
  return getJson<TrainDetail>(`/api/trains/${encodeURIComponent(trainId)}`, signal);
}

export function fetchJourney(
  fromId: string,
  toId: string,
  sort: JourneySort,
  signal?: AbortSignal,
): Promise<JourneyPlan> {
  const query = new URLSearchParams({ from: fromId, to: toId, sort });
  return getJson<JourneyPlan>(`/api/journeys?${query.toString()}`, signal);
}
