import { useRememberedState } from '../../app/WorkspaceProvider';
import { graph, channelLabel, encoderChannels } from '../../data/telemetry';
import { stopCamera, syncCamera } from './camera-clock';
import { createPortal, flushSync } from 'react-dom';
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
import type { AnalysisBundle, Channel, Sample, Signal, Wheel } from '../../data/types';

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
const wheelGuideLabels: Record<Wheel, string> = {
  FL: 'Front left wheel',
  FR: 'Front right wheel',
  ML: 'Middle left wheel',
  MR: 'Middle right wheel',
  RL: 'Rear left wheel',
  RR: 'Rear right wheel',
};
const formatReading = (value: number | null) => {
  if (value === null) return '—';
  const fixed = value.toFixed(3);
  if (fixed.length <= 8) return fixed;
  const scientific = value.toExponential(1);
  return scientific.length <= 8 ? scientific : value.toExponential(0);
};
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
  const [emptyTextSize, setEmptyTextSize] = useState({ width: 0, height: 0 });
  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [shift, setShift] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [wheelGuide, setWheelGuide] = useState<{ x: number; y: number } | null>(null);
  const [hover, setHover] = useState<{
    time: number;
    x: number;
    y: number;
    spikes: { name: Channel; sample: Sample }[];
  } | null>(null);
  const [notice, setNotice] = useState('');
  const plot = useRef<HTMLDivElement>(null);
  const cursor = useRef<HTMLDivElement>(null);
  const measurement = useRef<HTMLDivElement>(null);
  const measurementReserve = useRef<HTMLDivElement>(null);
  const emptyText = useRef<HTMLSpanElement>(null);
  const hoverTip = useRef<HTMLDivElement>(null);
  const wheelGuideTip = useRef<HTMLDivElement>(null);
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
  const displaySeries = useMemo(
    () =>
      new Map(
        activeNames.map((name) => [name, graph.extremeSpikeGaps(channels[name].samples ?? [])]),
      ),
    [activeNames, channels],
  );
  // Keep the first line just below the readouts; the scale label has its own left lane.
  const top = Math.max(plotTop, hasTelemetry ? measurementHeight + 12 : 0);
  const formatUnix = (seconds: number) =>
    bundle.absoluteTime === false ? `${seconds.toFixed(3)} s` : (startUnix + seconds).toFixed(3);
  function update(next: Partial<TimelineState> | ((previous: TimelineState) => TimelineState)) {
    current.current =
      typeof next === 'function' ? next(current.current) : { ...current.current, ...next };
    setState(current.current);
  }
  function atTime(previous: TimelineState, next: number, follow = true): TimelineState {
    const time = clamp(next, 0, duration);
    const start =
      follow && (time < previous.start || time > previous.start + previous.span)
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
      ...(previous.time >= duration ? atTime(previous, 0) : previous),
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
  function pan(direction: -1 | 1) {
    update((previous) => ({
      ...previous,
      start: clamp(previous.start + direction * previous.span * 0.2, 0, duration - previous.span),
    }));
    setHover(null);
  }
  function measurePlot() {
    // SVG coordinates and HTML offsets both use local CSS pixels. A rendered
    // bounding rectangle can include zoom/scaling and would apply it twice.
    const style = getComputedStyle(plot.current!);
    const next = {
      width: Math.max(1, parseFloat(style.width)),
      height: Math.max(100, parseFloat(style.height)),
    };
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
  useLayoutEffect(() => {
    const text = emptyText.current;
    if (hasTelemetry || !text) return;
    const measure = () => {
      const { width, height } = text.getBoundingClientRect();
      setEmptyTextSize((previous) =>
        previous.width === width && previous.height === height ? previous : { width, height },
      );
    };
    measure();
    const observer = new ResizeObserver(() => flushSync(measure));
    observer.observe(text);
    return () => observer.disconnect();
  }, [hasTelemetry, bundle.message]);
  function paintCursor(time = current.current.time) {
    const element = cursor.current;
    if (!element) return;
    const { start, span } = current.current;
    const position = clamp((time - start) / span, 0, 1) * size.width;
    const visible = time >= start && time <= start + span;
    plot.current?.setAttribute('aria-valuenow', String(Number(time.toFixed(3))));
    element.style.transform = `translate3d(${position}px, 0, 0)`;
    element.style.display = visible ? '' : 'none';
  }
  useLayoutEffect(() => {
    if (!measurementReserve.current) return;
    const measure = () => {
      const height = measurementReserve.current?.offsetHeight ?? 18;
      setMeasurementHeight((previous) => (previous === height ? previous : height));
    };
    measure();
    const observer = new ResizeObserver(() => flushSync(measure));
    observer.observe(measurementReserve.current);
    return () => observer.disconnect();
  }, [hasTelemetry]);
  useLayoutEffect(() => {
    paintCursor(pendingSeek.current ?? current.current.time);
  }, [state, size, channels, top]);
  useLayoutEffect(() => {
    const tip = hoverTip.current;
    if (!hover || !tip) return;
    const rect = plot.current!.getBoundingClientRect();
    tip.style.left = `${clamp(rect.left + hover.x + 12, 8, Math.max(8, innerWidth - tip.offsetWidth - 8))}px`;
    tip.style.top = `${clamp(rect.top + hover.y + 12, 8, Math.max(8, innerHeight - tip.offsetHeight - 8))}px`;
  }, [hover, size, activeNames]);
  useLayoutEffect(() => {
    const tip = wheelGuideTip.current;
    if (!wheelGuide || !tip) return;
    const left =
      wheelGuide.x + tip.offsetWidth + 12 > innerWidth - 8
        ? wheelGuide.x - tip.offsetWidth - 12
        : wheelGuide.x + 12;
    const top =
      wheelGuide.y + tip.offsetHeight + 12 > innerHeight - 8
        ? wheelGuide.y - tip.offsetHeight - 12
        : wheelGuide.y + 12;
    tip.style.left = `${clamp(left, 8, Math.max(8, innerWidth - tip.offsetWidth - 8))}px`;
    tip.style.top = `${clamp(top, 8, Math.max(8, innerHeight - tip.offsetHeight - 8))}px`;
  }, [wheelGuide, size]);
  useEffect(() => setWheelGuide(null), [state.channel, activeNames.length]);
  const wheelGuideOpen = wheelGuide !== null;
  useEffect(() => {
    if (!wheelGuideOpen) return;
    const controller = new AbortController();
    const { signal } = controller;
    const hide = () => setWheelGuide(null);
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key === 'Escape') hide();
      },
      { signal },
    );
    document.addEventListener('scroll', hide, { capture: true, signal });
    window.addEventListener('resize', hide, { signal });
    window.addEventListener('blur', hide, { signal });
    return () => controller.abort();
  }, [wheelGuideOpen]);
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
      // Keep following a visible playhead; allow a panned-away window to stay put.
      current.current = atTime(
        before,
        before.time + elapsed,
        before.time >= before.start && before.time <= before.start + before.span,
      );
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
  const sample = (seconds: number, source: Signal, name: Channel): number | null => {
    if (source.samples) {
      if (
        seconds < (source.coverageStart ?? Infinity) ||
        seconds > (source.coverageEnd ?? -Infinity)
      )
        return null;
      return graph.sampleAtOrBefore(displaySeries.get(name)!.samples, seconds)?.value ?? null;
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
        points = graph.visibleTraceSegments(
          displaySeries.get(name)!.samples,
          state.start,
          end,
          size.width,
        );
      } else {
        const timestamps = [
          state.start,
          ...source.values
            .map((_, i) => (i / (source.values.length - 1)) * duration)
            .filter((time) => time > state.start && time < end),
          end,
        ];
        points = [
          timestamps.map((time) => ({ timeSeconds: time, value: sample(time, source, name) })),
        ];
      }
      return { name, points };
    });
  }, [activeNames, channels, displaySeries, state.start, state.span, size.width, duration]);
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
          const previous = segment[index - 1];
          // Adjacent offscreen samples contribute only where their line enters the view.
          if (previous && previous.value !== null && point.value !== null) {
            for (const edge of [state.start, end]) {
              if (previous.timeSeconds < edge && point.timeSeconds > edge)
                include(
                  previous.value +
                    ((edge - previous.timeSeconds) / (point.timeSeconds - previous.timeSeconds)) *
                      (point.value - previous.value),
                );
            }
          }
          if (point.timeSeconds >= state.start && point.timeSeconds <= end) include(point.value);
        });
      }
    }
    if (!Number.isFinite(low)) {
      for (const name of activeNames) {
        const source = channels[name];
        if (source.samples)
          displaySeries.get(name)!.samples.forEach((point) => include(point.value));
        else source.values.forEach(include);
      }
    }
    let ticks = [1, 0.5, 0, -0.5, -1];
    if (Number.isFinite(low) && Number.isFinite(high)) {
      // Fit one shared axis to visible selected data, including one-sided signals.
      const center = low + (high - low) / 2;
      const padding = Math.max(
        high > low ? (high - low) * 0.04 : Math.max(Math.abs(low), Math.abs(high)) * 0.01,
        0.001,
      );
      const interval = (high - low + padding * 2) / 4;
      const magnitude = 10 ** (Math.floor(Math.log10(interval)) - 1);
      const step = Math.ceil(interval / magnitude) * magnitude;
      ticks = Array.from({ length: 5 }, (_, i) =>
        Number((center + (2 - i) * step).toPrecision(12)),
      );
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
  }, [
    visibleSeries,
    activeNames,
    channels,
    displaySeries,
    state.start,
    state.span,
    encoderGraph,
    imuGroup,
  ]);
  const x = (seconds: number) => ((seconds - state.start) / state.span) * size.width;
  const gridY = (index: number) => top + (index / 4) * (size.height - top - bottom);
  const tickDecimals = Math.min(
    12,
    Math.max(0, 1 - Math.floor(Math.log10(signal.ticks[0] - signal.ticks[1]))),
  );
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
  const spikeMarkers = useMemo(() => {
    const gaps: { start: number; end: number; spikes: { name: Channel; sample: Sample }[] }[] = [];
    for (const name of activeNames) {
      for (const gap of displaySeries.get(name)!.gaps) {
        if (gap.end < state.start || gap.start > state.start + state.span) continue;
        const sample = gap.spikes.reduce((largest, sample) =>
          Math.abs(sample.value!) > Math.abs(largest.value!) ? sample : largest,
        );
        gaps.push({ start: gap.start, end: gap.end, spikes: [{ name, sample }] });
      }
    }
    // Merge overlapping gaps and nearby display buckets so tiny markers remain inspectable.
    gaps.sort((a, b) => a.start - b.start);
    const groups: typeof gaps = [];
    for (const gap of gaps) {
      const previous = groups.at(-1);
      if (!previous || ((gap.start - previous.end) / state.span) * size.width > 6) {
        groups.push(gap);
        continue;
      }
      previous.end = Math.max(previous.end, gap.end);
      for (const spike of gap.spikes) {
        const prior = previous.spikes.findIndex(({ name }) => name === spike.name);
        if (prior < 0) previous.spikes.push(spike);
        else if (Math.abs(spike.sample.value!) > Math.abs(previous.spikes[prior].sample.value!))
          previous.spikes[prior] = spike;
      }
    }
    return groups;
  }, [activeNames, displaySeries, state.start, state.span, size.width]);
  const selectionStart = selection ? Math.min(selection.start, selection.end) : 0;
  const selectionEnd = selection ? Math.max(selection.start, selection.end) : 0;
  // 13px monospace timestamps need up to 8px per character plus edge padding.
  const selectionLabelWidth =
    Math.max(formatUnix(selectionStart).length, formatUnix(selectionEnd).length) * 8 + 10;
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
                className={`timeline-axes${encoderGraph ? ' is-encoder' : ''}`}
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
          <div
            className="timeline-help-control"
            onPointerEnter={() => setHelpOpen(true)}
            onPointerLeave={() => setHelpOpen(false)}
          >
            <button
              ref={helpTrigger}
              className="analysis-graph-button timeline-help-trigger"
              type="button"
              data-timeline-help=""
              aria-label="Graph help"
              aria-describedby={helpOpen ? 'timeline-help' : undefined}
              onFocus={() => setHelpOpen(true)}
              onBlur={() => setHelpOpen(false)}
              onClick={() => setHelpOpen(true)}
            >
              ?
            </button>
            <div
              ref={help}
              id="timeline-help"
              className="timeline-help"
              role="tooltip"
              hidden={!helpOpen}
            >
              <p>
                Hold <kbd>Shift</kbd> and drag on the graph to zoom in.
              </p>
            </div>
          </div>
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
                      `${channelLabel(name)}: ${sample(state.time, channels[name], name)?.toFixed(3) ?? '—'} ${signal.spokenUnit}`,
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
          {hasTelemetry && (
            <div
              ref={measurementReserve}
              className="timeline-measurement-reserve"
              aria-hidden="true"
            >
              {Array.from({ length: encoderNames.length ? 6 : 3 }, (_, index) => (
                <span className="timeline-reading-reserve" key={index}>
                  <strong>−000.000</strong>
                  <span style={{ width: '2ch' }}>RR</span>
                </span>
              ))}
              <span data-reading-reserve-unit="">rad/s</span>
            </div>
          )}
          {bundle.message && !hasTelemetry && (
            <p className="timeline-state" role="status">
              <span ref={emptyText}>{bundle.message}</span>
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
                {bundle.message && !hasTelemetry && (
                  <rect
                    data-timeline-empty-label-mask=""
                    x={(size.width - emptyTextSize.width) / 2}
                    y={gridY(2) - emptyTextSize.height / 2}
                    width={emptyTextSize.width}
                    height={emptyTextSize.height}
                    fill="black"
                  />
                )}
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
                {signal.ticks.map((tick, index) => (
                  <line key={index} x1="0" x2={size.width} y1={gridY(index)} y2={gridY(index)} />
                ))}
              </g>
              {(hasData ? signal.ticks : []).map((tick, index) => (
                <text key={index} x="9" y={gridY(index) - 7}>
                  {Number(tick.toFixed(tickDecimals))}
                </text>
              ))}
            </g>
            <g clipPath="url(#timeline-bounds)">
              <Traces traces={traces} />
            </g>
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
                      x={clamp(
                        x(selectionStart) + 5,
                        5,
                        Math.max(5, size.width - selectionLabelWidth),
                      )}
                      y={top + 17}
                      data-selection-start=""
                    >
                      {formatUnix(selectionStart)}
                    </text>
                    <text
                      x={clamp(
                        x(selectionEnd) - 5,
                        Math.min(size.width - 5, selectionLabelWidth),
                        size.width - 5,
                      )}
                      y={size.height - bottom - 8}
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
          {spikeMarkers.map(({ start, end, spikes }) => {
            const { name, sample: spike } = spikes[0];
            const markerLeft = clamp(x(start), 0, size.width - 1);
            const markerWidth = Math.max(1, clamp(x(end), 0, size.width) - markerLeft);
            const hitWidth = Math.max(12, markerWidth);
            const hitLeft = clamp(
              markerLeft - (hitWidth - markerWidth) / 2,
              0,
              Math.max(0, size.width - hitWidth),
            );
            const description =
              spikes
                .map(
                  ({ name, sample }) =>
                    `${name.split('.')[1]} extreme spike: ${sample.value} ${signal.unit} at ${formatUnix(sample.timeSeconds)}.`,
                )
                .join(' ') + ' Omitted from the trace and scale; recorded values preserved.';
            const show = () =>
              setHover({
                time: spike.timeSeconds,
                x: markerLeft + markerWidth / 2,
                y: top,
                spikes,
              });
            return (
              <button
                key={`${name}-${spike.timeNs}`}
                type="button"
                className="timeline-spike-marker"
                data-spike-thin={markerWidth < 3}
                data-spike-channel={spikes.map(({ name }) => name).join(' ')}
                aria-label={description}
                aria-describedby={hover?.spikes === spikes ? 'timeline-spike-tooltip' : undefined}
                style={{ left: hitLeft, width: hitWidth, top, bottom }}
                onPointerDown={(event) => {
                  // Shift dragging uses the graph's normal selection gesture.
                  if (!event.shiftKey) event.stopPropagation();
                }}
                onPointerMove={(event) => {
                  event.stopPropagation();
                  show();
                }}
                onPointerEnter={show}
                onPointerLeave={() => setHover(null)}
                onFocus={show}
                onBlur={() => setHover(null)}
                onClick={(event) => {
                  event.stopPropagation();
                  if (event.shiftKey) return;
                  seek(spike.timeSeconds);
                  plot.current?.focus({ preventScroll: true });
                  show();
                }}
                onKeyDown={(event) => {
                  event.stopPropagation();
                  if (event.key === 'Escape') setHover(null);
                  if (event.key === ' ') {
                    event.preventDefault();
                    if (!event.repeat) togglePlayback();
                    setHover(null);
                  }
                }}
              >
                <span
                  className="timeline-spike-fill"
                  aria-hidden="true"
                  style={{ left: markerLeft - hitLeft, width: markerWidth }}
                />
              </button>
            );
          })}
          {activeNames.length > 0 && (
            <div
              ref={measurement}
              className={`timeline-measurement${encoderGraph ? ' is-encoder' : ''}`}
              role="group"
              aria-label={encoderGraph ? 'Wheel encoder readings' : 'IMU readings'}
              tabIndex={encoderGraph ? 0 : undefined}
              aria-describedby={wheelGuideOpen && encoderGraph ? 'encoder-wheel-guide' : undefined}
              style={{
                top: 'auto',
                bottom: `calc(${size.height - top}px + var(--timeline-playhead-height) + var(--timeline-reading-gap))`,
              }}
              onPointerEnter={(event) => {
                if (!encoderGraph || event.pointerType === 'touch') return;
                setHover(null);
                setWheelGuide({ x: event.clientX, y: event.clientY });
              }}
              onPointerMove={(event) => {
                if (encoderGraph && wheelGuideOpen && event.pointerType !== 'touch')
                  setWheelGuide({ x: event.clientX, y: event.clientY });
              }}
              onPointerLeave={(event) => {
                if (document.activeElement !== event.currentTarget) setWheelGuide(null);
              }}
              onPointerDown={(event) => {
                if (encoderGraph) event.stopPropagation();
              }}
              onFocus={(event) => {
                if (!encoderGraph) return;
                const rect = event.currentTarget.getBoundingClientRect();
                setHover(null);
                setWheelGuide({ x: rect.right, y: rect.bottom });
              }}
              onBlur={() => setWheelGuide(null)}
            >
              {activeNames.map((name) => {
                const source = channels[name];
                const value = sample(state.time, source, name);
                const axis = name.split('.')[1] as Axis;
                const recorded =
                  source.samples && graph.sampleAtOrBefore(source.samples, state.time);
                const isSpike =
                  value === null &&
                  recorded?.value != null &&
                  state.time >= source.coverageStart! &&
                  state.time <= source.coverageEnd!;
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
                      } as CSSProperties
                    }
                    title={
                      isSpike
                        ? `Extreme spike: ${recorded!.value} ${source.unit}. See the red gap on the graph.`
                        : state.time < (source.coverageStart ?? -Infinity) ||
                            state.time > (source.coverageEnd ?? Infinity)
                          ? 'Outside sensor coverage.'
                          : undefined
                    }
                  >
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
                      {isSpike ? '⚠' : formatReading(value)}
                    </strong>
                    <span className="timeline-reading-label">
                      {encoderGraph ? name.slice(8) : axis.toUpperCase()}
                    </span>
                  </span>
                );
              })}
              <span data-timeline-unit="">{hasData ? signal.unit : ''}</span>
            </div>
          )}
          {wheelGuide &&
            encoderGraph &&
            activeNames.length > 0 &&
            createPortal(
              <div
                ref={wheelGuideTip}
                id="encoder-wheel-guide"
                role="tooltip"
                className="chart-tooltip encoder-wheel-guide"
              >
                <h3>Wheel guide</h3>
                <dl>
                  {encoderChannels.map((name, index) => {
                    const wheel = name.slice(8) as Wheel;
                    return (
                      <div key={wheel}>
                        <dt style={{ color: wheelColors[index] }}>{wheel}</dt>
                        <dd>{wheelGuideLabels[wheel]}</dd>
                      </div>
                    );
                  })}
                </dl>
              </div>,
              document.body,
            )}
          {hover &&
            !interaction.current &&
            activeNames.length > 0 &&
            createPortal(
              <div
                ref={hoverTip}
                className="chart-tooltip is-spike"
                role="tooltip"
                id="timeline-spike-tooltip"
              >
                <time>{formatUnix(hover.time)}</time>
                {hover.spikes.map(({ name, sample }, index) => (
                  <span key={index} className="timeline-spike-detail">
                    {name.split('.')[1]} extreme spike: {sample.value} {signal.unit} at{' '}
                    {formatUnix(sample.timeSeconds)}.
                  </span>
                ))}
                <span className="timeline-spike-detail">
                  Omitted from the trace and scale; recorded values preserved.
                </span>
              </div>,
              document.body,
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
            <div className="timeline-pan" role="group" aria-label="Move visible time window">
              {([-1, 1] as const).map((direction) => (
                <button
                  key={direction}
                  type="button"
                  className="analysis-graph-button"
                  aria-label={direction < 0 ? 'Move view earlier' : 'Move view later'}
                  title={`Move ${direction < 0 ? 'earlier' : 'later'} by ${(state.span * 0.2).toFixed(3)} s (20% of view)`}
                  disabled={
                    duration <= 0 ||
                    (direction < 0 ? state.start <= 0 : state.start >= duration - state.span)
                  }
                  onClick={() => pan(direction)}
                >
                  <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path
                      d={direction < 0 ? 'M10 4 6 8l4 4' : 'm6 4 4 4-4 4'}
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              ))}
            </div>
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
          opacity={traces.length > 1 ? 0.78 : 1}
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
