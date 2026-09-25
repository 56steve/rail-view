"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, Bell, BellOff, Star, View } from "lucide-react";
import { useShallow } from "zustand/react/shallow";
import { useIsDesktop } from "@/hooks/useLayout";
import { useNowSeconds } from "@/hooks/useNow";
import { ApiError, fetchTrainDetail } from "@/lib/api";
import { delayTone, formatClock, formatSpeed, minutesUntil, trainIdentity, trainTypeLabel } from "@/lib/format";
import { navigate, navigateBack } from "@/lib/navigation";
import { useRailView } from "@/lib/store";
import type { StopTime, TrainDetail } from "@/lib/types";
import { AlertSheet } from "../ui/AlertSheet";
import { Card, PrimaryButton } from "../ui/primitives";
import { TrainPreview } from "../ui/TrainPreview";

const REFRESH_MS = 5000;

export function TrainDetailsScreen({ trainId }: { trainId: string }) {
  const [detail, setDetail] = useState<TrainDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [alertOpen, setAlertOpen] = useState(false);
  const saved = useRailView((s) => s.savedTrainIds.includes(trainId));
  const alerts = useRailView(useShallow((s) => s.alerts.filter((a) => a.trainId === trainId)));
  const isDesktop = useIsDesktop();
  const now = useNowSeconds(10_000);

  useEffect(() => {
    const controller = new AbortController();
    const load = () =>
      fetchTrainDetail(trainId, controller.signal)
        .then((d) => {
          setDetail(d);
          setError(null);
        })
        .catch((e: unknown) => {
          if (controller.signal.aborted) return;
          setError(e instanceof ApiError && e.status === 404 ? "This train isn't reporting right now." : "Couldn't reach RailView. Retrying…");
        });
    void load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [trainId]);

  const train = detail?.position;
  const stale = train?.status === "stale";
  const atPlatform = detail?.stops.some((s) => s.state === "at_platform");

  return (
    <div className="pointer-events-auto flex h-full flex-col overflow-y-auto bg-ink-950 md:rounded-3xl md:border md:hairline md:shadow-float">
      <div className="relative shrink-0">
        {train ? <TrainPreview ac={train.ac} /> : <div className="h-52 bg-ink-900" />}
        <div className="absolute inset-x-0 top-0 flex justify-between px-4 pt-safe md:pt-4">
          <button type="button" aria-label="Back" onClick={navigateBack} className="glass flex h-10 w-10 items-center justify-center rounded-full">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <button
            type="button"
            aria-label={saved ? "Remove from saved" : "Save train"}
            onClick={() => useRailView.getState().toggleSavedTrain(trainId)}
            className="glass flex h-10 w-10 items-center justify-center rounded-full"
          >
            <Star className={`h-5 w-5 ${saved ? "fill-warning text-warning" : ""}`} />
          </button>
        </div>
      </div>

      <div className="relative -mt-4 flex flex-1 flex-col gap-4 rounded-t-3xl bg-ink-950 px-5 pb-6 pt-5">
        {!train && <p className="text-[14px] text-fg-muted">{error ?? "Loading train…"}</p>}
        {train && detail && (
          <>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-[24px] font-semibold tracking-[-0.01em] text-fg">{trainTypeLabel(train)}</h1>
                <StatusBadge stale={stale} atPlatform={Boolean(atPlatform)} />
              </div>
              <p className="mt-1 text-[16px] text-fg-muted">{train.direction_label}</p>
              <p className="mt-1.5 text-[13px] text-fg-subtle">
                Train {trainIdentity(train)} <span className="mx-1.5 text-fg-subtle/60">|</span> {train.coach_count} Coaches
                <span className="mx-1.5 text-fg-subtle/60">|</span> {train.line_name} line
              </p>
            </div>

            <Card className="grid grid-cols-3 divide-x divide-white/8 py-3.5">
              <Figure value={formatSpeed(train.speed_kmh)} unit="km/h" label="Speed" />
              <DelayFigure seconds={train.delay_seconds} />
              <Figure
                value={formatClock(train.last_updated_epoch + train.destination_eta_seconds)}
                label={`ETA at ${train.destination.name}`}
              />
            </Card>

            <Timeline stops={detail.stops} now={now} />

            {alerts.length > 0 && (
              <div className="flex flex-col gap-2">
                {alerts.map((alert) => (
                  <div key={alert.id} className="flex items-center gap-3 rounded-xl border hairline bg-ink-850 px-3.5 py-2.5">
                    <Bell className="h-4 w-4 text-primary" />
                    <span className="flex-1 text-[13.5px] text-fg">Alert before {alert.stationName}</span>
                    <button
                      type="button"
                      aria-label={`Cancel alert for ${alert.stationName}`}
                      onClick={() => useRailView.getState().removeAlert(alert.id)}
                      className="text-fg-subtle hover:text-fg"
                    >
                      <BellOff className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="mt-auto flex flex-col gap-2.5 pt-2">
              <PrimaryButton onClick={() => setAlertOpen(true)} disabled={stale}>
                <Bell className="h-[18px] w-[18px]" />
                Set Alert
              </PrimaryButton>
              {!isDesktop && (
                <button
                  type="button"
                  onClick={() => navigate({ name: "follow", trainId })}
                  className="flex h-12 items-center justify-center gap-2 rounded-2xl border hairline text-[14.5px] font-medium text-fg transition hover:bg-white/5"
                >
                  <View className="h-[18px] w-[18px]" />
                  Follow in 3D
                </button>
              )}
            </div>
          </>
        )}
      </div>

      {alertOpen && detail && <AlertSheet trainId={trainId} stops={detail.stops} onClose={() => setAlertOpen(false)} />}
    </div>
  );
}

function StatusBadge({ stale, atPlatform }: { stale: boolean; atPlatform: boolean }) {
  const [label, className] = stale
    ? ["Signal lost", "border-warning/40 text-warning"]
    : atPlatform
      ? ["At platform", "border-primary/40 text-primary"]
      : ["Running", "border-success/40 text-success"];
  return <span className={`rounded-full border px-2.5 py-0.5 text-[12px] font-medium ${className}`}>{label}</span>;
}

const TONE_TEXT = { "on-time": "text-success", late: "text-danger", early: "text-primary" } as const;

function Figure({
  value,
  unit,
  label,
  tone,
}: {
  value: string;
  unit?: string;
  label: string;
  tone?: keyof typeof TONE_TEXT;
}) {
  return (
    <div className="flex flex-col items-center gap-1 px-2 text-center">
      <span className={`text-[18px] font-semibold tabular-nums ${tone ? TONE_TEXT[tone] : "text-fg"}`}>
        {value}
        {unit && <span className="ml-1 text-[12px] font-medium text-fg-muted">{unit}</span>}
      </span>
      <span className="truncate text-[12px] text-fg-muted">{label}</span>
    </div>
  );
}

function DelayFigure({ seconds }: { seconds: number }) {
  const tone = delayTone(seconds);
  const minutes = Math.round(Math.abs(seconds) / 60);
  if (tone === "on-time") return <Figure value="On time" label="Delay" tone={tone} />;
  return <Figure value={`${minutes} min`} label={tone === "late" ? "Delay" : "Early"} tone={tone} />;
}

function Timeline({ stops, now }: { stops: StopTime[]; now: number }) {
  return (
    <ol className="flex flex-col">
      {stops.map((stop, i) => {
        const passed = stop.state === "departed";
        const current = stop.state === "next" || stop.state === "at_platform";
        const last = i === stops.length - 1;
        let detail: string;
        if (stop.state === "departed") {
          detail = stop.observed_arrival_epoch
            ? `Departed • ${formatClock(stop.observed_arrival_epoch)}`
            : `Departed • sched. ${formatClock(stop.scheduled_epoch)}`;
        } else if (stop.state === "at_platform") {
          detail = "At platform";
        } else if (stop.state === "next") {
          const minutes = minutesUntil(stop.expected_epoch, now);
          detail = minutes === 0 ? "Arriving now" : `Arriving in ${minutes} min`;
        } else {
          detail = formatClock(stop.expected_epoch);
        }
        return (
          <li key={stop.station.code} className="relative flex items-center gap-4 py-2">
            {!last && (
              <span
                className={`absolute left-[7px] top-1/2 h-full w-0.5 ${passed ? "bg-success/70" : "bg-white/10"}`}
                aria-hidden="true"
              />
            )}
            <span
              className={`relative z-10 flex shrink-0 items-center justify-center rounded-full ${
                current
                  ? "h-4 w-4 bg-primary ring-4 ring-primary/25"
                  : passed
                    ? "h-4 w-4 bg-success"
                    : "h-4 w-4 border-2 border-white/25 bg-ink-950"
              }`}
            />
            <span className={`w-28 shrink-0 truncate text-[14.5px] ${current ? "font-semibold text-fg" : passed ? "text-fg-muted" : "text-fg"}`}>
              {stop.station.name}
            </span>
            <span
              className={`truncate text-[13px] tabular-nums ${current ? "font-medium text-primary" : "text-fg-subtle"}`}
            >
              {detail}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
