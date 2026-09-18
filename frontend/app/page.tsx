import { RailPulseApp } from "@/components/RailPulseApp";
import type { RouteOut } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const DEFAULT_ROUTE_ID = "CR-thane-dadar";

async function fetchDefaultRoute(): Promise<RouteOut | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/routes/${DEFAULT_ROUTE_ID}`, {
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as RouteOut;
  } catch {
    // Backend not reachable at request time - the client falls back to
    // fetching it itself (see components/RailPulseApp.tsx) once it mounts.
    return null;
  }
}

export default async function Page() {
  const route = await fetchDefaultRoute();
  return <RailPulseApp initialRoute={route} />;
}
