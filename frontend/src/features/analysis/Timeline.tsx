import { useRememberedState } from '../../app/WorkspaceProvider';
import { graph } from '../../data/telemetry';
import { stopCamera, syncCamera } from './camera-clock';
import { flushSync } from 'react-dom';
import {
  memo,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type RefObject,
} from 'react';
import { useWorkspacePanel } from '../../components/Workspace';
import type { AnalysisBundle, Channel } from '../../data/types';

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const top = 26;
const bottom = 10;
type TimelineState = {
  time: number;
  playing: boolean;
  channel: Channel;
  start: number;
  span: number;
};
type Interaction = { kind: 'seek' | 'select'; start: number; end: number; resume: boolean };

/** Playback and all controls are local React state, independent of the workspace store. */
export const Timeline = memo(function Timeline({
  bundle,
  workspaceRef,
  recordingKey,
}: {
  recordingKey: string;
  bundle: AnalysisBundle;
  workspaceRef: RefObject<HTMLDivElement | null>;
}) {
  const { duration, startUnix, channels } = bundle;
  const panel = useWorkspacePanel();
  const [state, setState] = useRememberedState<TimelineState>(`timeline.${recordingKey}`, {
    time: 0,
    playing: false,
    channel:
      (channels['angular_velocity.z'].available ?? !!channels['angular_velocity.z'].values.length)
        ? 'angular_velocity.z'
        : ((Object.keys(channels) as Channel[]).find(
            (name) => channels[name].available ?? !!channels[name].values.length,
          ) ?? 'angular_velocity.z'),
    start: 0,
    span: Math.max(duration, 0.001),
  });
  const current = useRef(state);
  useEffect(() => () => setState({ ...current.current, playing: false }), [setState]);
  const seekFrame = useRef(0);
  const pendingSeek = useRef<number | null>(null);
  function scheduleSeek(time: number) {
    pendingSeek.current = time;
    if (seekFrame.current) return;
    seekFrame.current = requestAnimationFrame(() => {
      seekFrame.current = 0;
      if (pendingSeek.current !== null) seek(pendingSeek.current);
      pendingSeek.current = null;
    });
  }
  useEffect(() => () => cancelAnimationFrame(seekFrame.current), []);
  const lastDuration = useRef(duration);
  const [size, setSize] = useState({ width: 1, height: 100 });
  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [shift, setShift] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const plot = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const pointerDownOnTrigger = useRef(false);
  const help = useRef<HTMLDivElement>(null);
  const helpTrigger = useRef<HTMLButtonElement>(null);
  const options = useRef(new Map<Channel, HTMLButtonElement>());
  const interaction = useRef<Interaction | null>(null);
  const videos = useRef<HTMLVideoElement[]>([]);
  const channelNames = (Object.keys(channels) as Channel[]).filter(
    (name) => channels[name].available ?? !!channels[name].values.length,
  );
  const hasTelemetry = channelNames.length > 0;
  const formatUnix = (seconds: number) =>
    bundle.absoluteTime === false ? `${seconds.toFixed(3)} s` : (startUnix + seconds).toFixed(3);
  function update(next: Partial<TimelineState> | ((previous: TimelineState) => TimelineState)) {
    current.current =
      typeof next === 'function' ? next(current.current) : { ...current.current, ...next };
    setState(current.current);
  }
  function atTime(previous: TimelineState, next: number): TimelineState {
    const time = clamp(next, 0, duration);
    const start =
      time < previous.start || time > previous.start + previous.span
        ? clamp(time - previous.span * 0.2, 0, duration - previous.span)
        : previous.start;
    return { ...previous, time, start, playing: time < duration && previous.playing };
  }
  function seek(time: number) {
    update((previous) => atTime(previous, time));
  }
  function togglePlayback() {
    if (!(duration > 0)) return;
    update((previous) => ({
      ...atTime(previous, previous.time >= duration ? 0 : previous.time),
      playing: !previous.playing,
    }));
  }
  function zoom(factor: number) {
    if (!(duration > 0)) return;
    update((previous) => {
      const span = clamp(previous.span * factor, duration / 32, duration);
      const anchor =
        previous.time >= previous.start && previous.time <= previous.start + previous.span
          ? previous.time
          : previous.start + previous.span / 2;
      return {
        ...previous,
        span,
        start: clamp(
          anchor - ((anchor - previous.start) / previous.span) * span,
          0,
          duration - span,
        ),
      };
    });
  }
  function resetZoom() {
    update({ start: 0, span: Math.max(duration, 0.001) });
  }
  function measurePlot() {
    const rect = plot.current!.getBoundingClientRect();
    const next = { width: Math.max(1, rect.width), height: Math.max(100, rect.height) };
    setSize((previous) =>
      previous.width === next.width && previous.height === next.height ? previous : next,
    );
  }
  // Panel changes commit their layout and SVG dimensions together, before paint.
  // Observing only the plot can otherwise lag a pending React panel update.
  useLayoutEffect(measurePlot, [panel.width, panel.collapsed]);
  useLayoutEffect(() => {
    const observer = new ResizeObserver(() => flushSync(measurePlot));
    observer.observe(plot.current!);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!state.playing) return;
    let previous = performance.now();
    let frame = 0;
    function tick(now: number) {
      if (!current.current.playing) return;
      const elapsed = (now - previous) / 1000;
      previous = now;
      update((value) => atTime(value, value.time + elapsed));
      if (current.current.playing) frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [state.playing, duration]);
  useEffect(() => {
    videos.current = Array.from(
      workspaceRef.current?.querySelectorAll<HTMLVideoElement>('.analysis-camera video') ?? [],
    );
    const controller = new AbortController();
    for (const video of videos.current) {
      const sync = () => syncCamera(video, current.current.time, current.current.playing);
      for (const event of ['loadedmetadata', 'canplay', 'waiting', 'seeking', 'seeked', 'error'])
        video.addEventListener(event, sync, { signal: controller.signal });
      sync();
    }
    return () => {
      controller.abort();
      videos.current.forEach(stopCamera);
    };
  }, [workspaceRef, duration, bundle.mediaVersion]);
  useEffect(() => {
    for (const video of videos.current) syncCamera(video, state.time, state.playing);
  }, [state.time, state.playing, duration, bundle.mediaVersion]);
  useEffect(() => {
    const oldDuration = lastDuration.current;
    lastDuration.current = duration;
    update((previous) => ({
      ...previous,
      time: Math.min(previous.time, duration),
      span: Math.max(
        0.001,
        previous.span >= oldDuration ? duration : Math.min(previous.span, duration),
      ),
      start: Math.max(0, Math.min(previous.start, duration - previous.span)),
    }));
  }, [duration]);
  useEffect(() => {
    if (channelNames.length && !channelNames.includes(current.current.channel))
      update({ channel: channelNames[0] });
  }, [channels]);
  function pointerTime(event: PointerEvent<HTMLDivElement>) {
    const rect = plot.current!.getBoundingClientRect();
    return (
      current.current.start +
      clamp((event.clientX - rect.left) / rect.width, 0, 1) * current.current.span
    );
  }
  function finishInteraction(cancelled = false) {
    cancelAnimationFrame(seekFrame.current);
    seekFrame.current = 0;
    pendingSeek.current = null;
    document.documentElement.classList.remove('is-timeline-dragging');
    const active = interaction.current;
    if (!active) return;
    let resume = active.resume;
    if (active.kind === 'select') {
      const start = Math.min(active.start, active.end),
        end = Math.max(active.start, active.end);
      if (!cancelled && ((end - start) / current.current.span) * plot.current!.clientWidth >= 8) {
        const span = clamp(end - start, duration / 32, duration);
        const windowStart = clamp((start + end - span) / 2, 0, duration - span);
        update({ span, start: windowStart });
        setNotice(
          hasTelemetry
            ? `Zoomed to Unix time ${formatUnix(windowStart)} through ${formatUnix(windowStart + span)}.`
            : `Zoomed to recording position ${windowStart.toFixed(1)} through ${(windowStart + span).toFixed(1)} seconds.`,
        );
        resume = false;
      }
    }
    interaction.current = null;
    setSelection(null);
    setDragging(false);
    if (resume && current.current.time < duration) update({ playing: true });
  }
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key === 'Shift') setShift(true);
        if (event.key === 'Escape' && interaction.current?.kind === 'select') {
          event.preventDefault();
          finishInteraction(true);
        }
      },
      { signal },
    );
    document.addEventListener(
      'keyup',
      (event) => {
        if (event.key === 'Shift') setShift(false);
      },
      { signal },
    );
    const pause = () => {
      finishInteraction(true);
      setShift(false);
      update({ playing: false });
    };
    window.addEventListener('blur', pause, { signal });
    document.addEventListener(
      'visibilitychange',
      () => {
        if (document.hidden) pause();
      },
      { signal },
    );
    return () => {
      controller.abort();
      document.documentElement.classList.remove('is-timeline-dragging');
    };
  }, [duration, startUnix]);
  useEffect(() => {
    if (menuOpen) options.current.get(state.channel)?.focus();
  }, [menuOpen]);
  useEffect(() => {
    if (!menuOpen && !helpOpen) return;
    const controller = new AbortController();
    document.addEventListener(
      'pointerdown',
      (event) => {
        const target = event.target as Node;
        if (!menu.current?.contains(target) && !trigger.current?.contains(target))
          setMenuOpen(false);
        if (!help.current?.contains(target) && !helpTrigger.current?.contains(target))
          setHelpOpen(false);
      },
      { signal: controller.signal },
    );
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key !== 'Escape') return;
        if (menuOpen) {
          setMenuOpen(false);
          trigger.current?.focus();
        }
        if (helpOpen) {
          setHelpOpen(false);
          helpTrigger.current?.focus();
        }
      },
      { signal: controller.signal },
    );
    return () => controller.abort();
  }, [menuOpen, helpOpen]);
  function plotKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (interaction.current || event.altKey || event.ctrlKey || event.metaKey) return;
    const step = event.shiftKey ? 10 : 1;
    switch (event.key) {
      case ' ':
      case 'Enter':
        togglePlayback();
        break;
      case 'ArrowRight':
      case 'ArrowUp':
        seek(current.current.time + step);
        break;
      case 'ArrowLeft':
      case 'ArrowDown':
        seek(current.current.time - step);
        break;
      case 'Home':
        seek(0);
        break;
      case 'End':
        seek(duration);
        break;
      case '+':
      case '=':
        zoom(0.5);
        break;
      case '-':
        zoom(2);
        break;
      case '0':
        resetZoom();
        break;
      default:
        return;
    }
    event.preventDefault();
  }
  function menuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    let index = channelNames.findIndex(
      (name) => options.current.get(name) === document.activeElement,
    );
    switch (event.key) {
      case 'ArrowDown':
        index = (index + 1) % channelNames.length;
        break;
      case 'ArrowUp':
        index = (index + channelNames.length - 1) % channelNames.length;
        break;
      case 'ArrowRight':
      case 'ArrowLeft':
        index = (index + 3) % channelNames.length;
        break;
      case 'Home':
        index = 0;
        break;
      case 'End':
        index = channelNames.length - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    options.current.get(channelNames[index])?.focus();
  }
  const signal = channels[state.channel];
  const sample = (seconds: number): number | null => {
    if (signal.samples) {
      if (
        seconds < (signal.coverageStart ?? Infinity) ||
        seconds > (signal.coverageEnd ?? -Infinity)
      )
        return null;
      return graph.sampleAtOrBefore(signal.samples, seconds)?.value ?? null;
    }
    if (!signal.values.length || duration <= 0) return null;
    const position = clamp(seconds / duration, 0, 1) * (signal.values.length - 1);
    const i = Math.floor(position),
      next = Math.min(i + 1, signal.values.length - 1);
    return signal.values[i] + (signal.values[next] - signal.values[i]) * (position - i);
  };
  const x = (seconds: number) => ((seconds - state.start) / state.span) * size.width;
  const y = (value: number) =>
    top +
    ((signal.ticks[0] - value) / (signal.ticks[0] - signal.ticks.at(-1)!)) *
      (size.height - top - bottom);
  const segments = useMemo(() => {
    const samples = signal.samples;
    if (!samples) return null;
    const end = state.start + state.span;
    const visible = graph.visibleTraceSegments(samples, state.start, end, size.width);
    const last = samples.at(-1);
    // Visual hold only: raw samples and the numeric readout retain measured coverage.
    if (last?.value != null && last.timeSeconds < end && duration > last.timeSeconds) {
      const tail = { ...last, timeSeconds: end };
      const final = visible.at(-1);
      if (final?.at(-1) === last) visible[visible.length - 1] = [...final, tail];
      else if (state.start > last.timeSeconds)
        visible.push([{ ...last, timeSeconds: state.start }, tail]);
    }
    return visible;
  }, [signal, state.start, state.span, size.width, duration]);
  const path = useMemo(() => {
    if (segments)
      return segments
        .map((segment) =>
          segment
            .map(
              (sample, i) =>
                `${i ? 'L' : 'M'}${x(sample.timeSeconds).toFixed(3)},${y(sample.value!).toFixed(3)}`,
            )
            .join(''),
        )
        .join('');
    const timestamps = [
      state.start,
      ...signal.values
        .map((_, i) => (i / (signal.values.length - 1)) * duration)
        .filter((time) => time > state.start && time < state.start + state.span),
      state.start + state.span,
    ];
    return timestamps
      .map((time, i) => `${i ? 'L' : 'M'}${x(time).toFixed(3)},${y(sample(time) ?? 0).toFixed(3)}`)
      .join('');
  }, [state.start, state.span, signal, size, duration, segments]);
  const area = useMemo(
    () =>
      segments
        ? segments
            .map((segment) => {
              const line = segment
                .map((sample, i) => `${i ? 'L' : 'M'}${x(sample.timeSeconds)},${y(sample.value!)}`)
                .join('');
              return `${line}L${x(segment.at(-1)!.timeSeconds)},${size.height - bottom}L${x(segment[0].timeSeconds)},${size.height - bottom}Z`;
            })
            .join('')
        : `${path}L${size.width},${size.height - bottom}L0,${size.height - bottom}Z`,
    [segments, path, size, state.start, state.span, signal],
  );
  const value = sample(state.time);
  const singleSamples = useMemo(() => {
    const byPixel = new Map<number, { x: number; y: number }>();
    for (const segment of segments ?? []) {
      if (segment.length !== 1) continue;
      const point = segment[0];
      byPixel.set(Math.floor(x(point.timeSeconds)), {
        x: x(point.timeSeconds),
        y: y(point.value!),
      });
    }
    return [...byPixel.values()];
  }, [segments, size, state.start, state.span, signal]);
  const hasData = signal.available ?? !!signal.values.length;
  const selectionStart = selection ? Math.min(selection.start, selection.end) : 0;
  const selectionEnd = selection ? Math.max(selection.start, selection.end) : 0;
  return (
    <section
      className="cn-card analysis-timeline bg-secondary shadow-none ring-0 dark:bg-secondary/50"
      data-slot="card"
      data-component="imu-timeline"
      aria-label="IMU timeline"
    >
      <div className="analysis-graph-header" data-slot="card-header">
        <div className="analysis-graph-heading">
          <button
            className="analysis-graph-button"
            type="button"
            data-timeline-play=""
            aria-label={state.playing ? 'Pause timeline' : 'Play timeline'}
            title={state.playing ? 'Pause timeline' : 'Play timeline'}
            disabled={duration <= 0}
            onClick={togglePlayback}
          >
            <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
              {state.playing ? (
                <>
                  <rect x="4" y="3" width="3" height="10" rx=".5" />
                  <rect x="9" y="3" width="3" height="10" rx=".5" />
                </>
              ) : (
                <path d="M5 3v10l8-5z" />
              )}
            </svg>
          </button>
          <div className="timeline-channel-picker">
            <button
              ref={trigger}
              className="timeline-channel-trigger"
              type="button"
              data-channel-trigger=""
              aria-label="Choose sensor graph"
              disabled={!channelNames.length}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-controls="timeline-channel-menu"
              onPointerDown={() => {
                pointerDownOnTrigger.current = true;
              }}
              onClick={() => {
                pointerDownOnTrigger.current = false;
                setMenuOpen((open) => !open);
                setHelpOpen(false);
              }}
              onKeyDown={(event) => {
                if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
                  event.preventDefault();
                  setMenuOpen(true);
                  setHelpOpen(false);
                }
              }}
            >
              <span data-channel-label="">
                {channelNames.length ? state.channel : 'Recording timeline'}
              </span>
              <svg
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="m5 6.5 3 3 3-3" />
              </svg>
            </button>
            <div
              ref={menu}
              className="timeline-channel-menu"
              id="timeline-channel-menu"
              role="menu"
              aria-label="Sensor channel"
              hidden={!menuOpen}
              onKeyDown={menuKeyDown}
              onBlur={(event) => {
                if (
                  !pointerDownOnTrigger.current &&
                  !event.currentTarget.contains(event.relatedTarget) &&
                  !trigger.current?.contains(event.relatedTarget)
                )
                  setMenuOpen(false);
              }}
            >
              {(['angular_velocity', 'linear_acceleration'] as const).map((group) => (
                <div
                  key={group}
                  className="timeline-channel-group"
                  role="group"
                  aria-label={
                    group === 'angular_velocity' ? 'Angular velocity' : 'Linear acceleration'
                  }
                >
                  {channelNames
                    .filter((name) => name.startsWith(group))
                    .map((name) => (
                      <button
                        key={name}
                        ref={(element) => {
                          if (element) options.current.set(name, element);
                          else options.current.delete(name);
                        }}
                        type="button"
                        role="menuitemradio"
                        aria-label={name}
                        aria-checked={state.channel === name}
                        data-channel={name}
                        tabIndex={state.channel === name ? 0 : -1}
                        onClick={() => {
                          update({ channel: name });
                          setMenuOpen(false);
                          trigger.current?.focus();
                        }}
                      >
                        <span>{name}</span>
                        <span className="timeline-channel-unit">{channels[name].unit}</span>
                      </button>
                    ))}
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="analysis-graph-actions">
          <button
            className="analysis-graph-button"
            type="button"
            data-timeline-reset=""
            aria-label="Reset zoom"
            title="Reset zoom"
            disabled={state.span >= duration}
            onClick={resetZoom}
          >
            <svg
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M3 6a5 5 0 1 1 0 4M3 2.5V6h3.5" />
            </svg>
          </button>
          <button
            className="analysis-graph-button"
            type="button"
            data-timeline-zoom="out"
            aria-label="Zoom out"
            title="Zoom out"
            disabled={state.span >= duration}
            onClick={() => zoom(2)}
          >
            <svg
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M4 8h8" />
            </svg>
          </button>
          <button
            className="analysis-graph-button"
            type="button"
            data-timeline-zoom="in"
            aria-label="Zoom in"
            title="Zoom in"
            disabled={duration <= 0 || state.span <= duration / 32}
            onClick={() => zoom(0.5)}
          >
            <svg
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M4 8h8M8 4v8" />
            </svg>
          </button>
          <button
            ref={helpTrigger}
            className="analysis-graph-button timeline-help-trigger"
            type="button"
            data-timeline-help=""
            aria-label="Graph help"
            aria-expanded={helpOpen}
            aria-controls="timeline-help"
            title="Graph help"
            onClick={() => {
              setHelpOpen(!helpOpen);
              setMenuOpen(false);
            }}
          >
            ?
          </button>
        </div>
        <div
          ref={help}
          id="timeline-help"
          className="timeline-help"
          role="region"
          aria-label="Timeline controls"
          hidden={!helpOpen}
        >
          <p>
            Hold <kbd>Shift</kbd> and drag on the graph to zoom in.
          </p>
        </div>
      </div>
      <div className="timeline-content" data-slot="card-content">
        <div
          ref={plot}
          className={`timeline-plot${shift ? ' is-shift-ready' : ''}${selection ? ' is-selecting' : ''}${dragging ? ' is-scrubbing' : ''}`}
          data-timeline-plot=""
          role="slider"
          tabIndex={0}
          aria-label="Recording timeline"
          aria-valuemin={0}
          aria-valuemax={duration}
          aria-valuenow={Number(state.time.toFixed(3))}
          aria-valuetext={
            hasTelemetry
              ? `Unix time ${formatUnix(state.time)}, ends at ${formatUnix(duration)}, ${state.channel}: ${value === null ? '—' : value.toFixed(3)} ${signal.spokenUnit}`
              : `Recording position ${state.time.toFixed(1)} of ${duration.toFixed(1)} seconds`
          }
          aria-orientation="horizontal"
          onKeyDown={plotKeyDown}
          onPointerDown={(event) => {
            if (event.button !== 0 || !event.isPrimary || interaction.current) return;
            event.preventDefault();
            document.documentElement.classList.add('is-timeline-dragging');
            const time = pointerTime(event);
            interaction.current = {
              kind: event.shiftKey ? 'select' : 'seek',
              start: time,
              end: time,
              resume: current.current.playing,
            };
            update({ playing: false });
            event.currentTarget.focus({ preventScroll: true });
            event.currentTarget.setPointerCapture(event.pointerId);
            if (event.shiftKey) setSelection({ start: time, end: time });
            else {
              setDragging(true);
              seek(time);
            }
          }}
          onPointerMove={(event) => {
            setShift(event.shiftKey);
            if (!event.currentTarget.hasPointerCapture(event.pointerId) || !interaction.current)
              return;
            event.preventDefault();
            document.documentElement.classList.add('is-timeline-dragging');
            const time = pointerTime(event);
            interaction.current.end = time;
            if (interaction.current.kind === 'select')
              setSelection({ start: interaction.current.start, end: time });
            else scheduleSeek(time);
          }}
          onPointerUp={(event) => {
            if (interaction.current) {
              interaction.current.end = pointerTime(event);
              if (interaction.current.kind === 'seek') seek(interaction.current.end);
            }
            finishInteraction();
            if (event.currentTarget.hasPointerCapture(event.pointerId))
              event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onPointerCancel={() => finishInteraction(true)}
          onLostPointerCapture={() => finishInteraction(true)}
        >
          {bundle.message && (
            <p className="timeline-state" role="status">
              {bundle.message}
            </p>
          )}
          <svg
            className="timeline-static"
            data-timeline-trace-svg=""
            preserveAspectRatio="none"
            aria-hidden="true"
            viewBox={`0 0 ${size.width} ${size.height}`}
          >
            <defs>
              <linearGradient id="timeline-fill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="var(--timeline-line)" stopOpacity=".14" />
                <stop offset="100%" stopColor="var(--timeline-line)" stopOpacity="0" />
              </linearGradient>
              <linearGradient id="timeline-edge-fade">
                <stop offset="0%" stopColor="white" stopOpacity="0" />
                <stop offset="2%" stopColor="white" />
                <stop offset="98%" stopColor="white" />
                <stop offset="100%" stopColor="white" stopOpacity="0" />
              </linearGradient>
              <mask id="timeline-grid-mask">
                <rect width={size.width} height={size.height} fill="url(#timeline-edge-fade)" />
              </mask>
              <linearGradient
                id="timeline-area-edge-fade"
                gradientUnits="userSpaceOnUse"
                x1="0"
                x2={size.width}
                y1="0"
                y2="0"
              >
                <stop offset="0%" stopColor="white" stopOpacity="0" />
                <stop offset="3%" stopColor="white" />
                <stop offset="97%" stopColor="white" />
                <stop offset="100%" stopColor="white" stopOpacity="0" />
              </linearGradient>
              <mask id="timeline-area-edge-mask">
                <rect
                  width={size.width}
                  height={size.height}
                  fill="url(#timeline-area-edge-fade)"
                />
              </mask>
            </defs>
            <g className="timeline-grid">
              <g mask="url(#timeline-grid-mask)">
                {(hasData ? signal.ticks : []).map((tick) => (
                  <line key={tick} x1="0" x2={size.width} y1={y(tick)} y2={y(tick)} />
                ))}
              </g>
              {(hasData ? signal.ticks : []).map((tick) => (
                <text key={tick} x="9" y={y(tick) - 7}>
                  {bundle.timestamped ? Number(tick.toPrecision(4)) : tick}
                </text>
              ))}
            </g>
            <Trace path={path} area={area} singleSamples={singleSamples} />
          </svg>
          <svg
            data-timeline-svg=""
            preserveAspectRatio="none"
            aria-hidden="true"
            viewBox={`0 0 ${size.width} ${size.height}`}
          >
            <g
              className="timeline-cursor"
              transform={`translate(${clamp(x(state.time), 0, size.width)},0)`}
              style={{
                display:
                  state.time < state.start || state.time > state.start + state.span
                    ? 'none'
                    : undefined,
              }}
            >
              <line x1="0" x2="0" y1={top} y2={size.height - bottom} />
              <path d={`M-3,${top - 6}H3V${top - 3}L0,${top}L-3,${top - 3}Z`} />
            </g>
            {selection && (
              <g className="timeline-selection">
                <rect
                  x={x(selectionStart)}
                  y={top}
                  width={Math.max(1, x(selectionEnd) - x(selectionStart))}
                  height={size.height - top - bottom}
                />
                <line
                  x1={x(selectionStart)}
                  x2={x(selectionStart)}
                  y1={top}
                  y2={size.height - bottom}
                />
                <line
                  x1={x(selectionEnd)}
                  x2={x(selectionEnd)}
                  y1={top}
                  y2={size.height - bottom}
                />
                {hasTelemetry && (
                  <>
                    <text
                      x={clamp(x(selectionStart) + 5, 5, Math.max(5, size.width - 89))}
                      y={top + 15}
                      data-selection-start=""
                    >
                      {formatUnix(selectionStart)}
                    </text>
                    <text
                      x={clamp(x(selectionEnd) - 5, Math.min(size.width - 5, 89), size.width - 5)}
                      y={size.height - 11}
                      textAnchor="end"
                      data-selection-end=""
                    >
                      {formatUnix(selectionEnd)}
                    </text>
                  </>
                )}
              </g>
            )}
          </svg>
          {hasTelemetry && (
            <div
              className="timeline-measurement"
              title={
                state.time > (signal.coverageEnd ?? Infinity)
                  ? 'Outside IMU coverage. The line holds the final sample visually.'
                  : undefined
              }
            >
              <strong data-timeline-value="">{value === null ? '—' : value.toFixed(3)}</strong>
              <span data-timeline-unit="">{hasData ? signal.unit : ''}</span>
            </div>
          )}
        </div>
        {hasTelemetry && (
          <div className="timeline-axis" aria-label="Unix timestamps">
            <time
              data-timeline-time=""
              dateTime={
                bundle.absoluteTime === false
                  ? undefined
                  : new Date((startUnix + state.time) * 1000).toISOString()
              }
              title="Current Unix time"
            >
              {formatUnix(state.time)}
            </time>
            <time
              data-timeline-end=""
              dateTime={
                bundle.absoluteTime === false
                  ? undefined
                  : new Date(
                      (startUnix + Math.min(duration, state.start + state.span)) * 1000,
                    ).toISOString()
              }
              title="Visible end Unix time"
            >
              {formatUnix(Math.min(duration, state.start + state.span))}
            </time>
          </div>
        )}
        <span className="sr-only" data-timeline-notice="" role="status">
          {notice}
        </span>
      </div>
    </section>
  );
});

// Memoization avoids rebuilding geometry; the separate composited SVG also keeps
// cursor/readout changes from rasterizing the dense masked trace on every frame.
const Trace = memo(function Trace({
  path,
  area,
  singleSamples,
}: {
  path: string;
  area: string;
  singleSamples: { x: number; y: number }[];
}) {
  return (
    <g mask="url(#timeline-area-edge-mask)">
      <path d={path ? area : ''} fill="url(#timeline-fill)" />
      <path className="timeline-line" d={path} />
      {singleSamples.map((point, index) => (
        <circle
          key={index}
          data-timeline-single-sample=""
          cx={point.x}
          cy={point.y}
          r="1.5"
          fill="var(--timeline-line)"
        />
      ))}
    </g>
  );
});
