import { useRememberedState } from '../../app/WorkspaceProvider';
import { graph, channelLabel, encoderChannels } from '../../data/telemetry';
import { stopCamera, syncCamera } from './camera-clock';
import { flushSync } from 'react-dom';
import {
  memo,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  type RefObject,
} from 'react';
import { useWorkspacePanel } from '../../components/Workspace';
import type { AnalysisBundle, Channel, Signal, Wheel } from '../../data/types';

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const plotTop = 26;
const bottom = 10;
type GraphChoice = Channel | 'encoders';
const axes = ['x', 'y', 'z'] as const;
type Axis = (typeof axes)[number];
type ImuGroup = 'angular_velocity' | 'linear_acceleration';
const axisColors = { x: '#00bb7f', y: '#f99c00', z: '#8d54ff' };
const groupLabels = {
  angular_velocity: 'Angular velocity',
  linear_acceleration: 'Linear acceleration',
};
const wheelColors = ['#3b9eff', '#f99c00', '#00bb7f', '#a16aff', '#ff5c9f', '#e5d34f'];
type TimelineState = {
  time: number;
  playing: boolean;
  channel: GraphChoice;
  axes?: Axis[];
  wheels?: Wheel[];
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
  const seekVersion = useRef(0);
  useEffect(() => () => setState({ ...current.current, playing: false }), [setState]);
  const seekFrame = useRef(0);
  const pendingSeek = useRef<number | null>(null);
  function scheduleSeek(time: number) {
    pendingSeek.current = time;
    // Follow the pointer immediately; camera seeks and readouts stay frame-coalesced.
    paintCursor(time);
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
  const [measurementHeight, setMeasurementHeight] = useState(18);
  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [shift, setShift] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [hover, setHover] = useState<{ time: number; x: number; y: number } | null>(null);
  const [notice, setNotice] = useState('');
  const plot = useRef<HTMLDivElement>(null);
  const cursor = useRef<HTMLDivElement>(null);
  const measurement = useRef<HTMLDivElement>(null);
  const hoverTip = useRef<HTMLDivElement>(null);
  const measurementLeft = useRef(Infinity);
  const help = useRef<HTMLDivElement>(null);
  const helpTrigger = useRef<HTMLButtonElement>(null);
  const interaction = useRef<Interaction | null>(null);
  const videos = useRef<HTMLVideoElement[]>([]);
  const availableChannelNames = useMemo(
    () =>
      (Object.keys(channels) as Channel[]).filter(
        (name) => channels[name].available ?? !!channels[name].values.length,
      ),
    [channels],
  );
  const encoderNames = encoderChannels.filter((name) => availableChannelNames.includes(name));
  const channelNames: GraphChoice[] = [
    ...availableChannelNames.filter((name) => !name.startsWith('encoder.')),
    ...(encoderNames.length ? ['encoders' as const, ...encoderNames] : []),
  ];
  const hasTelemetry = channelNames.length > 0;
  const encoderGraph = state.channel.startsWith('encoder');
  const imuGroup: ImuGroup = state.channel.startsWith('linear_acceleration')
    ? 'linear_acceleration'
    : 'angular_velocity';
  const selectedAxes = useMemo(
    () => state.axes ?? [encoderGraph ? 'z' : (state.channel.split('.')[1] as Axis)],
    [state.axes, state.channel, encoderGraph],
  );
  const selectedWheels = useMemo(
    () =>
      state.wheels ??
      (state.channel.startsWith('encoder.')
        ? [state.channel.slice(8) as Wheel]
        : encoderChannels.map((name) => name.slice(8) as Wheel)),
    [state.wheels, state.channel],
  );
  const activeNames = useMemo(
    () =>
      !hasTelemetry
        ? []
        : encoderGraph
          ? availableChannelNames.filter(
              (name) =>
                name.startsWith('encoder.') && selectedWheels.includes(name.slice(8) as Wheel),
            )
          : axes
              .filter((axis) => selectedAxes.includes(axis))
              .map((axis) => `${imuGroup}.${axis}` as Channel)
              .filter((name) => availableChannelNames.includes(name)),
    [hasTelemetry, encoderGraph, selectedWheels, selectedAxes, imuGroup, availableChannelNames],
  );
  // Leave room for wrapped readouts and the top scale label above its grid line.
  const top = Math.max(plotTop, activeNames.length ? measurementHeight + 24 : 0);
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
    seekVersion.current++;
    update((previous) => atTime(previous, time));
    paintCursor();
  }
  function togglePlayback() {
    if (!(duration > 0)) return;
    if (current.current.time >= duration) seekVersion.current++;
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
  function paintCursor(time = current.current.time) {
    const element = cursor.current;
    if (!element) return;
    const { start, span } = current.current;
    const position = clamp((time - start) / span, 0, 1) * size.width;
    const visible = time >= start && time <= start + span;
    plot.current?.setAttribute('aria-valuenow', String(Number(time.toFixed(3))));
    element.style.transform = `translate3d(${position}px, 0, 0)`;
    element.style.display = visible ? '' : 'none';
    const lifted = String(visible && position >= measurementLeft.current);
    if (measurement.current?.getAttribute('data-lifted') !== lifted)
      measurement.current?.setAttribute('data-lifted', lifted);
  }
  useLayoutEffect(() => {
    if (!measurement.current) return;
    const measure = () => {
      const height = measurement.current?.offsetHeight ?? 22;
      setMeasurementHeight((previous) => (previous === height ? previous : height));
    };
    measure();
    const observer = new ResizeObserver(() => flushSync(measure));
    observer.observe(measurement.current);
    return () => observer.disconnect();
  }, [hasTelemetry, encoderGraph, activeNames.length > 0]);
  useLayoutEffect(() => {
    measurementLeft.current = size.width - (measurement.current?.offsetWidth ?? 0) - 10;
    paintCursor(pendingSeek.current ?? current.current.time);
  }, [state, size, channels, top]);
  useLayoutEffect(() => {
    const tip = hoverTip.current;
    if (!hover || !tip) return;
    tip.style.left = `${clamp(hover.x + 12, 0, Math.max(0, size.width - tip.offsetWidth))}px`;
    tip.style.top = `${clamp(hover.y + 12, 0, Math.max(0, size.height - tip.offsetHeight))}px`;
  }, [hover, size, activeNames]);
  useEffect(() => {
    if (!state.playing) return;
    let previous = performance.now();
    let lastReadout = previous;
    let frame = 0;
    function tick(now: number) {
      if (!current.current.playing) return;
      const elapsed = (now - previous) / 1000;
      previous = now;
      const before = current.current;
      current.current = atTime(before, before.time + elapsed);
      paintCursor();
      // Keep movement at the display refresh rate; readouts and camera drift
      // checks need far fewer React commits, especially on 120 Hz displays.
      if (
        now - lastReadout >= 50 ||
        !current.current.playing ||
        before.start !== current.current.start
      ) {
        lastReadout = now;
        setState(current.current);
      }
      if (current.current.playing) frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [state.playing, duration, size.width]);
  useEffect(() => {
    videos.current = Array.from(
      workspaceRef.current?.querySelectorAll<HTMLVideoElement>('.analysis-camera video') ?? [],
    );
    const controller = new AbortController();
    for (const video of videos.current) {
      const sync = () =>
        syncCamera(video, current.current.time, current.current.playing, seekVersion.current);
      for (const event of [
        'emptied',
        'loadedmetadata',
        'loadeddata',
        'canplay',
        'waiting',
        'seeking',
        'seeked',
        'error',
        'camera-statechange',
      ])
        video.addEventListener(event, sync, { signal: controller.signal });
      sync();
    }
    return () => {
      controller.abort();
      videos.current.forEach(stopCamera);
    };
  }, [workspaceRef, duration, bundle.mediaVersion]);
  useEffect(() => {
    for (const video of videos.current)
      syncCamera(video, state.time, state.playing, seekVersion.current);
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
          bundle.absoluteTime !== false
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
    if (!helpOpen) return;
    const controller = new AbortController();
    document.addEventListener(
      'pointerdown',
      (event) => {
        const target = event.target as Node;
        if (!help.current?.contains(target) && !helpTrigger.current?.contains(target))
          setHelpOpen(false);
      },
      { signal: controller.signal },
    );
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key !== 'Escape') return;
        if (helpOpen) {
          setHelpOpen(false);
          helpTrigger.current?.focus();
        }
      },
      { signal: controller.signal },
    );
    return () => controller.abort();
  }, [helpOpen]);
  function plotKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    setHover(null);
    if (interaction.current || event.altKey || event.ctrlKey || event.metaKey) return;
    const step = event.shiftKey ? 10 : 1;
    switch (event.key) {
      case ' ':
      case 'Enter':
        if (!event.repeat) togglePlayback();
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
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (
        event.defaultPrevented ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        interaction.current
      )
        return;
      const target = event.target instanceof Element ? event.target : null;
      if (
        target?.closest(
          'input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="combobox"], [role="menu"], [role="listbox"], [role="separator"]',
        ) ||
        (target?.closest('[role="slider"]') && !plot.current?.contains(target)) ||
        document.querySelector('[role="dialog"], [role="alertdialog"], [aria-modal="true"]')
      )
        return;
      if (event.key === ' ') {
        event.preventDefault();
        if (!event.repeat) togglePlayback();
      } else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
        event.preventDefault();
        const direction = ['ArrowRight', 'ArrowUp'].includes(event.key) ? 1 : -1;
        seek(current.current.time + direction * (event.shiftKey ? 10 : 1));
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [duration]);
  const sample = (seconds: number, source: Signal): number | null => {
    if (source.samples) {
      if (
        seconds < (source.coverageStart ?? Infinity) ||
        seconds > (source.coverageEnd ?? -Infinity)
      )
        return null;
      return graph.sampleAtOrBefore(source.samples, seconds)?.value ?? null;
    }
    if (!source.values.length || duration <= 0) return null;
    const position = clamp(seconds / duration, 0, 1) * (source.values.length - 1);
    const i = Math.floor(position),
      next = Math.min(i + 1, source.values.length - 1);
    return source.values[i] + (source.values[next] - source.values[i]) * (position - i);
  };
  const visibleSeries = useMemo(() => {
    const end = state.start + state.span;
    return activeNames.map((name) => {
      const source = channels[name];
      let points;
      if (source.samples) {
        points = graph.visibleTraceSegments(source.samples, state.start, end, size.width);
        const last = source.samples.at(-1);
        // Visual hold only: samples and readouts retain their measured coverage.
        if (
          !encoderGraph &&
          last?.value != null &&
          last.timeSeconds < end &&
          duration > last.timeSeconds
        ) {
          const tail = { ...last, timeSeconds: end };
          const final = points.at(-1);
          if (final?.at(-1) === last) points[points.length - 1] = [...final, tail];
          else if (state.start > last.timeSeconds)
            points.push([{ ...last, timeSeconds: state.start }, tail]);
        }
      } else {
        const timestamps = [
          state.start,
          ...source.values
            .map((_, i) => (i / (source.values.length - 1)) * duration)
            .filter((time) => time > state.start && time < end),
          end,
        ];
        points = [timestamps.map((time) => ({ timeSeconds: time, value: sample(time, source) }))];
      }
      return { name, points };
    });
  }, [activeNames, channels, state.start, state.span, size.width, duration, encoderGraph]);
  const signal = useMemo((): Signal => {
    let low = Infinity;
    let high = -Infinity;
    const include = (value: number | null) => {
      if (value === null || !Number.isFinite(value)) return;
      low = Math.min(low, value);
      high = Math.max(high, value);
    };
    const end = state.start + state.span;
    for (const { points } of visibleSeries) {
      for (const segment of points) {
        segment.forEach((point, index) => {
          if (point.timeSeconds >= state.start && point.timeSeconds <= end) include(point.value);
          const previous = segment[index - 1];
          if (!previous || previous.value === null || point.value === null) return;
          // Adjacent offscreen samples contribute only where their line enters the view.
          for (const edge of [state.start, end]) {
            if (previous.timeSeconds < edge && point.timeSeconds > edge)
              include(
                previous.value +
                  ((edge - previous.timeSeconds) / (point.timeSeconds - previous.timeSeconds)) *
                    (point.value - previous.value),
              );
          }
        });
      }
    }
    let ticks = [1, 0.5, 0, -0.5, -1];
    if (Number.isFinite(low) && Number.isFinite(high)) {
      const padding = Math.max(
        high > low ? (high - low) * 0.08 : Math.max(Math.abs(low), Math.abs(high)) * 0.01,
        0.001,
      );
      const interval = (high - low + padding * 2) / 4;
      const magnitude = 10 ** Math.floor(Math.log10(interval));
      const step = [1, 2, 2.5, 5, 10].find((factor) => factor * magnitude >= interval)! * magnitude;
      const minimum = Math.floor((low - padding) / step);
      const maximum = Math.ceil((high + padding) / step);
      ticks = Array.from({ length: maximum - minimum + 1 }, (_, i) =>
        Number(((maximum - i) * step).toPrecision(12)),
      );
    } else if (activeNames.length) {
      const sources = activeNames.map((name) => channels[name]);
      high = Math.max(...sources.map((source) => source.ticks[0]));
      low = Math.min(...sources.map((source) => source.ticks.at(-1)!));
      ticks = Array.from({ length: 5 }, (_, i) => high - ((high - low) * i) / 4);
    }
    return {
      available: activeNames.length > 0,
      values: [],
      ticks,
      unit: encoderGraph ? 'RPM' : imuGroup === 'angular_velocity' ? 'rad/s' : 'm/s²',
      spokenUnit: encoderGraph
        ? 'revolutions per minute'
        : imuGroup === 'angular_velocity'
          ? 'radians per second'
          : 'metres per second squared',
    };
  }, [visibleSeries, activeNames, channels, state.start, state.span, encoderGraph, imuGroup]);
  const x = (seconds: number) => ((seconds - state.start) / state.span) * size.width;
  const y = (value: number) =>
    top +
    ((signal.ticks[0] - value) / (signal.ticks[0] - signal.ticks.at(-1)!)) *
      (size.height - top - bottom);
  const traces = useMemo(() => {
    const xPoint = (time: number) => ((time - state.start) / state.span) * size.width;
    const yPoint = (value: number) =>
      top +
      ((signal.ticks[0] - value) / (signal.ticks[0] - signal.ticks.at(-1)!)) *
        (size.height - top - bottom);
    return visibleSeries.map(({ name, points }) => {
      const index = encoderChannels.indexOf(name as (typeof encoderChannels)[number]);
      return {
        name,
        color: encoderGraph ? wheelColors[index] : axisColors[name.split('.')[1] as Axis],
        path: points
          .map((segment) =>
            segment
              .map(
                (point, i) =>
                  `${i ? 'L' : 'M'}${xPoint(point.timeSeconds).toFixed(3)},${yPoint(point.value!).toFixed(3)}`,
              )
              .join(''),
          )
          .join(''),
        singleSamples: [
          ...new Map(
            points
              .filter((segment) => segment.length === 1)
              .map(
                ([point]) =>
                  [
                    Math.floor(xPoint(point.timeSeconds)),
                    { x: xPoint(point.timeSeconds), y: yPoint(point.value!) },
                  ] as const,
              ),
          ).values(),
        ],
      };
    });
  }, [visibleSeries, signal, state.start, state.span, size, encoderGraph, top]);
  const hasData = signal.available ?? !!signal.values.length;
  const selectionStart = selection ? Math.min(selection.start, selection.end) : 0;
  const selectionEnd = selection ? Math.max(selection.start, selection.end) : 0;
  return (
    <section
      className="cn-card analysis-timeline bg-secondary shadow-none ring-0 dark:bg-secondary/50"
      data-slot="card"
      data-component="imu-timeline"
      aria-label={
        hasTelemetry
          ? state.channel.startsWith('encoder')
            ? 'Encoder timeline'
            : 'IMU timeline'
          : 'Recording timeline'
      }
      style={{ '--timeline-plot-bottom': `${bottom}px` } as CSSProperties}
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
          {hasTelemetry && (
            <>
              <GraphPicker
                id="timeline-channel-menu"
                label="Choose sensor graph"
                menuLabel="Sensor channel"
                value={encoderGraph ? 'encoders' : imuGroup}
                displayLabel={encoderGraph ? 'Encoders' : groupLabels[imuGroup]}
                choices={[
                  ...(['angular_velocity', 'linear_acceleration'] as const).map((group) => ({
                    value: group,
                    label: groupLabels[group],
                    unit: group === 'angular_velocity' ? 'rad/s' : 'm/s²',
                    disabled: !availableChannelNames.some((name) => name.startsWith(group)),
                  })),
                  {
                    value: 'encoders',
                    label: 'Encoders',
                    unit: 'RPM',
                    disabled: !encoderNames.length,
                  },
                ]}
                onOpen={() => setHelpOpen(false)}
                onChange={(group) => {
                  if (group === 'encoders') update({ channel: 'encoders' });
                  else {
                    const channel =
                      availableChannelNames.find((name) => name === `${group}.z`) ??
                      availableChannelNames.find((name) => name.startsWith(group));
                    if (channel) update({ channel });
                  }
                }}
              />
              <div
                className="timeline-axes"
                role="group"
                aria-label={encoderGraph ? 'Encoder wheels' : 'IMU axes'}
              >
                {(encoderGraph ? encoderChannels.map((name) => name.slice(8) as Wheel) : axes).map(
                  (key, index) => (
                    <label
                      key={key}
                      style={
                        {
                          '--axis-color': encoderGraph
                            ? wheelColors[index]
                            : axisColors[key as Axis],
                        } as CSSProperties
                      }
                    >
                      <input
                        className="bag-checkbox"
                        type="checkbox"
                        aria-label={encoderGraph ? `${key} wheel` : `${key.toUpperCase()} axis`}
                        checked={
                          encoderGraph
                            ? selectedWheels.includes(key as Wheel)
                            : selectedAxes.includes(key as Axis)
                        }
                        disabled={
                          !availableChannelNames.includes(
                            encoderGraph ? `encoder.${key as Wheel}` : `${imuGroup}.${key as Axis}`,
                          )
                        }
                        onChange={(event) => {
                          if (encoderGraph)
                            update({
                              wheels: event.target.checked
                                ? [...selectedWheels, key as Wheel]
                                : selectedWheels.filter((wheel) => wheel !== key),
                            });
                          else
                            update({
                              axes: event.target.checked
                                ? [...selectedAxes, key as Axis]
                                : selectedAxes.filter((axis) => axis !== key),
                            });
                        }}
                      />
                      <span>{key.toUpperCase()}</span>
                    </label>
                  ),
                )}
              </div>
            </>
          )}
          {!hasTelemetry && (
            <span className="timeline-channel-label" data-channel-label="">
              Recording timeline
            </span>
          )}
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
            Press <kbd>Space</kbd> to play or pause, and arrow keys to seek. Hold <kbd>Shift</kbd>{' '}
            for ten-second steps, or drag on the graph to zoom in.
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
              ? `${bundle.absoluteTime === false ? 'Recording position' : 'Unix time'} ${formatUnix(state.time)}, ends at ${formatUnix(duration)}, ${activeNames
                  .map(
                    (name) =>
                      `${channelLabel(name)}: ${sample(state.time, channels[name])?.toFixed(3) ?? '—'} ${signal.spokenUnit}`,
                  )
                  .join(', ')}`
              : `Recording position ${state.time.toFixed(1)} of ${duration.toFixed(1)} seconds`
          }

          aria-orientation="horizontal"
          onKeyDown={plotKeyDown}
          onPointerDown={(event) => {
            if (event.button !== 0 || !event.isPrimary || interaction.current) return;
            event.preventDefault();
            setHover(null);
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
            if (!event.currentTarget.hasPointerCapture(event.pointerId) || !interaction.current) {
              if (event.pointerType !== 'touch' && activeNames.length) {
                const rect = event.currentTarget.getBoundingClientRect();
                setHover({
                  time: pointerTime(event),
                  x: event.clientX - rect.left,
                  y: event.clientY - rect.top,
                });
              }
              return;
            }
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
          onPointerLeave={() => setHover(null)}
          onPointerCancel={() => finishInteraction(true)}
          onLostPointerCapture={() => finishInteraction(true)}
        >
          {bundle.message && !hasTelemetry && (
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
              <clipPath id="timeline-bounds">
                <rect x="0" y={top} width={size.width} height={size.height - top - bottom} />
              </clipPath>
              <linearGradient id="timeline-edge-fade">
                <stop offset="0%" stopColor="white" stopOpacity="0" />
                <stop offset="2%" stopColor="white" />
                <stop offset="98%" stopColor="white" />
                <stop offset="100%" stopColor="white" stopOpacity="0" />
              </linearGradient>
              <mask
                id="timeline-grid-mask"
                maskUnits="userSpaceOnUse"
                x="0"
                y="0"
                width={size.width}
                height={size.height}
              >
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
              <mask
                id="timeline-area-edge-mask"
                maskUnits="userSpaceOnUse"
                x="0"
                y="0"
                width={size.width}
                height={size.height}
              >
                <rect
                  width={size.width}
                  height={size.height}
                  fill="url(#timeline-area-edge-fade)"
                />
              </mask>
            </defs>
            <g className="timeline-grid">
              <g mask="url(#timeline-grid-mask)">
                {(hasTelemetry ? signal.ticks : []).map((tick) => (
                  <line key={tick} x1="0" x2={size.width} y1={y(tick)} y2={y(tick)} />
                ))}
              </g>
              {(hasData ? signal.ticks : []).map((tick) => (
                <text key={tick} x="9" y={y(tick) - 7}>
                  {Number(tick.toPrecision(4))}
                </text>
              ))}
            </g>
            <g clipPath="url(#timeline-bounds)">
              <Traces traces={traces} />
            </g>
            {!hasTelemetry && (
              <g mask="url(#timeline-area-edge-mask)">
                <path
                  d={`M0,${top}L${size.width},${top}L${size.width},${size.height - bottom}L0,${size.height - bottom}Z`}
                  fill="url(#timeline-fill)"
                />
                <path
                  className="timeline-line"
                  d={`M0,${top}L${size.width},${top}`}
                  style={{ strokeWidth: 1.2 }}
                />
              </g>
            )}
          </svg>
          <svg
            data-timeline-svg=""
            preserveAspectRatio="none"
            aria-hidden="true"
            viewBox={`0 0 ${size.width} ${size.height}`}
          >
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
                {duration > 0 && (
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
          <div
            ref={cursor}
            className="timeline-cursor"
            aria-hidden="true"
            style={{ top, bottom }}
          />
          {activeNames.length > 0 && (
            <div
              ref={measurement}
              className={`timeline-measurement${encoderGraph ? ' is-encoder' : ''}`}
              role="group"
              aria-label={encoderGraph ? 'Wheel encoder readings' : 'IMU readings'}
            >
              {activeNames.map((name) => {
                const source = channels[name];
                const value = sample(state.time, source);
                const axis = name.split('.')[1] as Axis;
                const digits = Math.max(6, ...source.ticks.map((tick) => tick.toFixed(3).length));
                return (
                  <span
                    className="timeline-axis-reading"
                    key={name}
                    style={
                      {
                        color: encoderGraph
                          ? wheelColors[
                              encoderChannels.indexOf(name as (typeof encoderChannels)[number])
                            ]
                          : axisColors[axis],
                        '--reading-digits': `${digits}ch`,
                      } as CSSProperties
                    }
                    title={
                      state.time > (source.coverageEnd ?? Infinity)
                        ? encoderGraph
                          ? 'Outside sensor coverage.'
                          : 'Outside sensor coverage. The line holds the final sample visually.'
                        : undefined
                    }
                  >
                    <span className="timeline-reading-label">
                      {encoderGraph ? name.slice(8) : axis.toUpperCase()}
                    </span>
                    <strong
                      data-axis-value={!encoderGraph ? axis : undefined}
                      data-encoder-value={encoderGraph ? name : undefined}
                      data-timeline-value={
                        name ===
                        (activeNames.includes(state.channel as Channel)
                          ? state.channel
                          : activeNames[0])
                          ? ''
                          : undefined
                      }
                    >
                      {value === null ? '—' : value.toFixed(3)}
                    </strong>
                  </span>
                );
              })}
              <span data-timeline-unit="">{hasData ? signal.unit : ''}</span>
            </div>
          )}
          {hover && !interaction.current && activeNames.length > 0 && (
            <div ref={hoverTip} className="chart-tooltip" role="tooltip">
              <time>{formatUnix(hover.time)}</time>
              {activeNames.map((name) => {
                const axis = name.split('.')[1] as Axis;
                const index = encoderChannels.indexOf(name as (typeof encoderChannels)[number]);
                return (
                  <span
                    key={name}
                    style={{ color: encoderGraph ? wheelColors[index] : axisColors[axis] }}
                  >
                    <span>{encoderGraph ? name.slice(8) : axis.toUpperCase()}</span>
                    <strong>{sample(hover.time, channels[name])?.toFixed(3) ?? '—'}</strong>
                    <span>{signal.unit}</span>
                  </span>
                );
              })}
            </div>
          )}
        </div>
        {duration > 0 && (
          <div
            className="timeline-axis"
            aria-label={bundle.absoluteTime === false ? 'Recording seconds' : 'Unix timestamps'}
          >
            <time
              data-timeline-time=""
              dateTime={
                bundle.absoluteTime === false
                  ? undefined
                  : new Date((startUnix + state.time) * 1000).toISOString()
              }
              title={
                bundle.absoluteTime === false ? 'Current recording position' : 'Current Unix time'
              }
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
              title={
                bundle.absoluteTime === false ? 'Visible end position' : 'Visible end Unix time'
              }
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
const Traces = memo(function Traces({
  traces,
}: {
  traces: {
    name: Channel;
    color: string;
    path: string;
    singleSamples: { x: number; y: number }[];
  }[];
}) {
  return (
    <g mask="url(#timeline-area-edge-mask)">
      {traces.map((trace) => (
        <g
          key={trace.name}
          data-encoder-trace={trace.name.startsWith('encoder.') ? trace.name : undefined}
          data-axis-trace={!trace.name.startsWith('encoder.') ? trace.name : undefined}
        >
          <path
            className="timeline-line"
            d={trace.path}
            style={{ stroke: trace.color }}
            vectorEffect="non-scaling-stroke"
          />
          {trace.singleSamples.map((point, index) => (
            <circle
              key={index}
              data-timeline-single-sample=""
              cx={point.x}
              cy={point.y}
              r=".75"
              fill={trace.color}
            />
          ))}
        </g>
      ))}
    </g>
  );
});

function GraphPicker({
  id,
  label,
  menuLabel,
  value,
  displayLabel,
  choices,
  onOpen,
  onChange,
}: {
  id: string;
  label: string;
  menuLabel: string;
  value: string;
  displayLabel: string;
  choices: { value: string; label: string; unit?: string; disabled?: boolean }[];
  onOpen(): void;
  onChange(value: string): void;
}) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const options = useRef(new Map<string, HTMLButtonElement>());
  const pointerDownOnTrigger = useRef(false);
  useEffect(() => {
    if (!open) return;
    const selected =
      choices.find((choice) => choice.value === value && !choice.disabled) ??
      choices.find((choice) => !choice.disabled);
    if (selected) options.current.get(selected.value)?.focus();
    const controller = new AbortController();
    document.addEventListener(
      'pointerdown',
      (event) => {
        if (
          !menu.current?.contains(event.target as Node) &&
          !trigger.current?.contains(event.target as Node)
        )
          setOpen(false);
      },
      { signal: controller.signal },
    );
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key === 'Escape') {
          setOpen(false);
          trigger.current?.focus();
        }
      },
      { signal: controller.signal },
    );
    return () => controller.abort();
  }, [open]);
  return (
    <div className="timeline-channel-picker">
      <button
        ref={trigger}
        className="timeline-channel-trigger"
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={id}
        onPointerDown={() => {
          pointerDownOnTrigger.current = true;
        }}
        onClick={() => {
          pointerDownOnTrigger.current = false;
          setOpen(!open);
          onOpen();
        }}
        onKeyDown={(event) => {
          if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
            event.preventDefault();
            setOpen(true);
            onOpen();
          }
        }}
      >
        <span data-channel-label={id === 'timeline-channel-menu' ? '' : undefined}>
          {displayLabel}
        </span>
        <svg
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          aria-hidden="true"
        >
          <path d="m5 6.5 3 3 3-3" />
        </svg>
      </button>
      <div
        ref={menu}
        className="timeline-channel-menu"
        id={id}
        role="menu"
        aria-label={menuLabel}
        hidden={!open}
        onBlur={(event) => {
          if (
            !pointerDownOnTrigger.current &&
            !event.currentTarget.contains(event.relatedTarget) &&
            !trigger.current?.contains(event.relatedTarget)
          )
            setOpen(false);
        }}
        onKeyDown={(event) => {
          const enabled = choices.filter((choice) => !choice.disabled);
          let index = enabled.findIndex(
            (choice) => options.current.get(choice.value) === document.activeElement,
          );
          switch (event.key) {
            case 'ArrowDown':
            case 'ArrowRight':
              index = (index + 1) % enabled.length;
              break;
            case 'ArrowUp':
            case 'ArrowLeft':
              index = (index + enabled.length - 1) % enabled.length;
              break;
            case 'Home':
              index = 0;
              break;
            case 'End':
              index = enabled.length - 1;
              break;
            default:
              return;
          }
          event.preventDefault();
          options.current.get(enabled[index]?.value)?.focus();
        }}
      >
        {choices.map((choice) => (
          <button
            key={choice.value}
            type="button"
            role="menuitemradio"
            aria-label={choice.label}
            ref={(element) => {
              if (element) options.current.set(choice.value, element);
              else options.current.delete(choice.value);
            }}
            aria-checked={value === choice.value}
            disabled={choice.disabled}
            data-channel={choice.value}
            tabIndex={value === choice.value ? 0 : -1}
            onClick={() => {
              onChange(choice.value);
              setOpen(false);
              trigger.current?.focus();
            }}
          >
            <span>{choice.label}</span>
            {choice.unit && <span className="timeline-channel-unit">{choice.unit}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}
