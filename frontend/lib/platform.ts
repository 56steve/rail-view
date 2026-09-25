// How a train's platform reads: "PF 3", or "Usually PF 5–7" where it
// varies from train to train, and which side its doors open.

import type { DoorSide, Platform } from "./types";

const PLAIN_NUMBER = /^\d+$/;

function follows(previous: string | undefined, next: string | undefined): boolean {
  if (previous === undefined || next === undefined) return false;
  return PLAIN_NUMBER.test(previous) && PLAIN_NUMBER.test(next) && Number(next) === Number(previous) + 1;
}

/** "5–7" for three or more consecutive plain numbers; otherwise "1, 1A, 4". */
function numberRuns(numbers: readonly string[]): string {
  const parts: string[] = [];
  let start = 0;
  while (start < numbers.length) {
    let end = start;
    while (end + 1 < numbers.length && follows(numbers[end], numbers[end + 1])) end++;
    parts.push(end - start >= 2 ? `${numbers[start]}–${numbers[end]}` : numbers.slice(start, end + 1).join(", "));
    start = end + 1;
  }
  return parts.join(", ");
}

export function platformLabel(platform: Platform): string {
  const label = `PF ${numberRuns(platform.numbers)}`;
  return platform.certain ? label : `Usually ${label}`;
}

export function doorLabel(door: DoorSide | null): string | null {
  if (door === null) return null;
  return door === "both" ? "Doors both sides" : `Doors ${door}`;
}

/** The next stop's platform from the live table's scalar columns. */
export function livePlatform(numbers: string | null, certain: boolean, door: DoorSide | null): Platform | null {
  if (numbers === null || numbers === "") return null;
  return { numbers: numbers.split(","), door, certain };
}
