import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { Recording } from '../../data/types';
import { StatusDiagnostic } from './StatusDiagnostic';

export function RecordingThumbnail({
  recording,
  priority = false,
}: {
  recording: Recording;
  priority?: boolean;
}) {
  const thumbnail = recording.thumbnail;
  const [failedUrl, setFailedUrl] = useState('');
  const [loadedUrl, setLoadedUrl] = useState('');
  const count = thumbnail?.frameCount ?? 1;
  const [hovered, setHovered] = useState(false);
  const [frame, setFrame] = useState(Math.floor(count / 2));
  const [aspect, setAspect] = useState(16 / 9);
  const url = thumbnail?.url;
  const preview = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const row = preview.current?.closest('tr') ?? preview.current;
    if (!row) return;
    const enter = (event: Event) => {
      if (
        (event as PointerEvent).pointerType !== 'touch' &&
        window.matchMedia('(min-width: 701px) and (hover: hover) and (pointer: fine)').matches
      )
        setHovered(true);
    };
    const focus = () => setHovered(true);
    const blur = () => setHovered(false);
    row.addEventListener('pointerenter', enter);
    row.addEventListener('pointerleave', blur);
    row.addEventListener('focusin', focus);
    row.addEventListener('focusout', blur);
    return () => {
      row.removeEventListener('pointerenter', enter);
      row.removeEventListener('pointerleave', blur);
      row.removeEventListener('focusin', focus);
      row.removeEventListener('focusout', blur);
    };
  }, []);
  useEffect(() => {
    setFrame(Math.floor(count / 2));
    if (!hovered || count < 2 || loadedUrl !== url) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let timer: ReturnType<typeof setInterval> | undefined;
    const update = () => {
      clearInterval(timer);
      setFrame(Math.floor(count / 2));
      if (
        !motion.matches &&
        window.matchMedia('(min-width: 701px) and (hover: hover) and (pointer: fine)').matches
      ) {
        setFrame((Math.floor(count / 2) + 1) % count);
        timer = setInterval(() => setFrame((current) => (current + 1) % count), 750);
      }
    };
    motion.addEventListener('change', update);
    update();
    return () => {
      clearInterval(timer);
      motion.removeEventListener('change', update);
    };
  }, [hovered, count, url, loadedUrl]);
  const label =
    url && failedUrl === url
      ? 'No Thumbnail'
      : ({
          queued: 'Queued',
          processing: 'Processing',
          failed: 'No Thumbnail',
          unavailable: 'No Thumbnail',
        }[thumbnail?.state ?? ''] ?? 'No Thumbnail');
  return (
    <div
      ref={preview}
      className="recording-thumbnail"
      aria-label={`Thumbnail for ${recording.name}`}
      data-thumbnail-frame={frame}
    >
      {url && failedUrl !== url ? (
        <>
          <div
            className="thumbnail-frames"
            style={{
              aspectRatio: aspect,
              width: aspect >= 16 / 9 ? '100%' : 'auto',
              height: aspect >= 16 / 9 ? 'auto' : '100%',
            }}
          >
            <img
              src={url}
              alt={`Camera scene from ${recording.name}`}
              loading={priority ? 'eager' : 'lazy'}
              fetchPriority={priority ? 'high' : 'auto'}
              decoding="async"
              style={{
                width: `${count * 100}%`,
                transform: `translateX(-${(frame * 100) / count}%)`,
              }}
              onLoad={(event) => {
                setAspect(
                  event.currentTarget.naturalWidth / count / event.currentTarget.naturalHeight,
                );
                setLoadedUrl(url);
              }}
              onError={() => setFailedUrl(url)}
            />
          </div>
          {loadedUrl !== url && <span className="thumbnail-loading">Loading…</span>}
        </>
      ) : (
        <span>{label}</span>
      )}
    </div>
  );
}

export function RecordingDescription({ description }: { description: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [clipped, setClipped] = useState(false);
  useLayoutEffect(() => {
    const element = ref.current!;
    const measure = () =>
      setClipped(
        element.scrollWidth > element.clientWidth ||
          (element.firstElementChild?.scrollWidth ?? 0) > element.clientWidth,
      );
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [description]);
  return (
    <div ref={ref} className="recording-description">
      {clipped ? (
        <StatusDiagnostic
          navigable
          side="right"
          status={description}
          issues={[description]}
          tone="muted"
          raw
          className="recording-description-trigger"
        />
      ) : (
        <span>{description}</span>
      )}
    </div>
  );
}
