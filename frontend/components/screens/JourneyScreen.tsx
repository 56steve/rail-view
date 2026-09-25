"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowUpDown, Box, ChevronRight, Clock, Info, Star } from "lucide-react";
import { useNowSeconds } from "@/hooks/useNow";
import { fetchJourney } from "@/lib/api";
import { formatClock, formatDuration, formatMinutesAway, trainIdentity, trainTypeLabel } from "@/lib/format";
import { directSegment } from "@/lib/journey";
import { navigate, navigateBack } from "@/lib/navigation";
import { doorLabel, platformLabel } from "@/lib/platform";
import { useRailView } from "@/lib/store";
import type { JourneyOption, JourneyPlan, JourneySort, StationIndexEntry } from "@/lib/types";
import { JourneyMiniMap } from "../ui/JourneyMiniMap";
import { EmptyState, LineSwatch, PrimaryButton, SectionTitle } from "../ui/primitives";
import { StationPicker } from "../ui/StationPicker";

const REFRESH_MS = 5000;

export function JourneyScreen({ fromId, toId }: { fromId: string | null; toId: string | null }) {
  const stations = useRailView((s) => s.stations);
  const routes = useRailView((s) => s.routes);
  const lines = useRailView((s) => s.lines);
  const tracks = useRailView((s) => s.tracks);
  const saved = useRailView((s) => s.savedJourneys.some((j) => j.fromId === fromId && j.toId === toId));
  const [picking, setPicking] = useState<"from" | "to" | null>(null);
  const [sort, setSort] = useState<JourneySort>("fastest");
  const [plan, setPlan] = useState<JourneyPlan | null>(null);
  const now = useNowSeconds(10_000);

  const from = stations.find((s) => s.id === fromId) ?? null;
  const to = stations.find((s) => s.id === toId) ?? null;
  const segment = useMemo(() => (from && to ? directSegment(from, to, routes, tracks) : null), [from, to, routes, tracks]);

  const setEnds = (nextFrom: string | null, nextTo: string | null) =>
    useRailView.getState().replaceTop({ name: "journey", fromId: nextFrom, toId: nextTo });

  useEffect(() => {
    if (!fromId || !toId || fromId === toId) return;
    const controller = new AbortController();
    const load = () =>
      fetchJourney(fromId, toId, sort, controller.signal)
        .then((result) => setPlan(result))
        .catch(() => {
          // Keep showing the last plan; the next refresh retries.
        });
    void load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [fromId, toId, sort]);

  // Frame the journey on the map (visible beside the panel on desktop).
  useEffect(() => {
    if (segment) useRailView.getState().requestCamera({ kind: "frame-points", points: segment.points });
  }, [segment]);

  // A plan for a previous from/to pair (or sort) is stale until the new one arrives.
  const current = plan && plan.from_station.id === fromId && plan.to_station.id === toId && plan.sort === sort ? plan : null;
  const options = current?.options ?? [];
  // Only running trains can be shown in 3D; the rest haven't left yet.
  const firstLive = options.find((option) => option.is_live);
  const loading = Boolean(fromId && toId && fromId !== toId && !current);

  return (
    <div className="pointer-events-auto flex h-full flex-col overflow-y-auto bg-ink-950 px-4 pb-6 pt-safe md:rounded-3xl md:border md:hairline md:px-5 md:pt-5 md:shadow-float">
      <header className="flex items-center gap-3 py-2">
        <button type="button" aria-label="Back" onClick={navigateBack} className="-ml-2 rounded-full p-2 text-fg hover:bg-white/5">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <h1 className="flex-1 text-[19px] font-semibold text-fg">Plan Your Journey</h1>
        {fromId && toId && (
          <button
            type="button"
            aria-label={saved ? "Remove saved journey" : "Save journey"}
            onClick={() => useRailView.getState().toggleSavedJourney({ fromId, toId })}
            className="rounded-full p-2 text-fg hover:bg-white/5"
          >
            <Star className={`h-5 w-5 ${saved ? "fill-warning text-warning" : ""}`} />
          </button>
        )}
      </header>

      <div className="relative mt-2 rounded-2xl border hairline bg-ink-800">
        <EndpointRow dot="bg-primary" label={from?.name ?? "From station"} placeholder={!from} onClick={() => setPicking("from")} />
        <div className="ml-12 border-t hairline" />
        <EndpointRow dot="bg-danger" label={to?.name ?? "To station"} placeholder={!to} onClick={() => setPicking("to")} />
        <button
          type="button"
          aria-label="Swap stations"
          onClick={() => setEnds(toId, fromId)}
          className="absolute right-3 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-xl border hairline bg-ink-700 text-fg transition hover:bg-ink-600"
        >
          <ArrowUpDown className="h-[18px] w-[18px]" />
        </button>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2.5">
        <div className="flex h-11 items-center gap-2 rounded-xl border hairline bg-ink-800 px-3.5 text-[13.5px] text-fg-muted" title="Journeys are planned from trains running right now">
          <Clock className="h-4 w-4" />
          Leaving now
        </div>
        <label className="relative flex h-11 items-center rounded-xl border hairline bg-ink-800 px-3.5 text-[13.5px] text-fg">
          <span className="sr-only">Sort by</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as JourneySort)}
            className="w-full appearance-none bg-transparent outline-none"
          >
            <option value="fastest">Fastest</option>
            <option value="soonest">Soonest</option>
          </select>
          <ChevronRight className="pointer-events-none h-4 w-4 rotate-90 text-fg-subtle" />
        </label>
      </div>

      {from && to && (
        <section className="mt-6 flex flex-col gap-3">
          <SectionTitle>Recommended Trains</SectionTitle>
          {current?.interchange_hint && (
            <div className="flex gap-2.5 rounded-2xl border hairline bg-ink-800 px-4 py-3 text-[13.5px] text-fg-muted">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              {current.interchange_hint}
            </div>
          )}
          {options.map((option) => (
            <JourneyOptionRow
              key={option.train_id}
              option={option}
              color={lines[option.line_code]?.color_hex ?? "#888"}
              now={now}
            />
          ))}
          {current && options.length === 0 && !current.interchange_hint && (
            <EmptyState
              title={`No direct trains to ${to.name} soon`}
              body="Nothing in the timetable leaves for there in the next three hours."
            />
          )}
          {loading && <p className="px-1 text-[13px] text-fg-subtle">Finding trains…</p>}

          <JourneyMiniMap from={from} to={to} segment={segment} trainIds={options.map((o) => o.train_id)} />
        </section>
      )}

      {!(from && to) && (
        <div className="mt-6">
          <EmptyState title="Where are you going?" body="Pick your start and destination to see trains that will take you there." />
        </div>
      )}

      <div className="mt-auto pt-5">
        <PrimaryButton
          disabled={!firstLive}
          onClick={() => firstLive && navigate({ name: "follow", trainId: firstLive.train_id })}
        >
          <Box className="h-[18px] w-[18px]" />
          View in 3D
        </PrimaryButton>
      </div>

      {picking && (
        <StationPicker
          title={picking === "from" ? "Starting from" : "Going to"}
          excludeId={picking === "from" ? toId : fromId}
          onClose={() => setPicking(null)}
          onPick={(station: StationIndexEntry) => {
            setPicking(null);
            if (picking === "from") setEnds(station.id, toId);
            else setEnds(fromId, station.id);
          }}
        />
      )}
    </div>
  );
}

function EndpointRow({
  dot,
  label,
  placeholder,
  onClick,
}: {
  dot: string;
  label: string;
  placeholder: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className="flex h-14 w-full items-center gap-4 pl-4 pr-16 text-left">
      <span className={`h-3 w-3 shrink-0 rounded-full ${dot} ring-4 ring-white/5`} />
      <span className={`truncate text-[16px] ${placeholder ? "text-fg-subtle" : "font-medium text-fg"}`}>{label}</span>
    </button>
  );
}

function JourneyOptionRow({ option, color, now }: { option: JourneyOption; color: string; now: number }) {
  const late = option.is_live && option.delay_seconds >= 60;
  const status = option.is_live ? (late ? `${Math.round(option.delay_seconds / 60)} min late` : "On time") : "Scheduled";
  // Which side to get out at the destination, like m-Indicator.
  const alightDoor = doorLabel(option.alight_platform?.door ?? null);
  const body = (
    <>
      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 items-center gap-2 text-[15px] font-medium text-fg">
          <LineSwatch color={color} className="h-2 w-2 shrink-0" />
          <span className="shrink-0 whitespace-nowrap">{trainTypeLabel(option)}</span>
          <span className="truncate text-[11.5px] font-normal text-fg-subtle">{trainIdentity(option)}</span>
        </span>
        <span className="mt-1 block truncate text-[13px] font-medium">
          <span className="text-success">{formatMinutesAway(option.board_expected_epoch, now)}</span>
          <span className={late ? "text-warning" : "text-fg-subtle"}>
            {" · "}
            {status}
          </span>
        </span>
        {option.board_platform && (
          <span className="mt-0.5 block truncate text-[11.5px] text-fg-muted">{platformLabel(option.board_platform)}</span>
        )}
      </span>
      <span className="text-right">
        <span className="block text-[15px] font-semibold text-success">~{formatDuration(option.duration_seconds)}</span>
        <span className="mt-1 block text-[12.5px] tabular-nums text-fg-muted">
          {formatClock(option.board_expected_epoch)} – {formatClock(option.alight_expected_epoch)}
        </span>
        {alightDoor && <span className="mt-0.5 block text-[11.5px] text-fg-subtle">{alightDoor}</span>}
      </span>
    </>
  );
  const frame = "flex items-center gap-3 rounded-2xl border hairline bg-ink-800 px-4 py-3.5 text-left";

  // A train that hasn't started its run has no live position to open.
  if (!option.is_live) return <div className={`${frame} pr-[46px]`}>{body}</div>;
  return (
    <button
      type="button"
      onClick={() => navigate({ name: "train", trainId: option.train_id })}
      className={`${frame} transition hover:bg-ink-750`}
    >
      {body}
      <ChevronRight className="h-5 w-5 shrink-0 text-fg-subtle" />
    </button>
  );
}
