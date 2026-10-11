import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { Recording } from '../../data/types';
import { StatusDiagnostic } from './StatusDiagnostic';

export function RecordingThumbnail({
  recording,
  navigable = false,
  priority = false,
}: {
  recording: Recording;
  navigable?: boolean;
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
    const link = preview.current?.closest('a');
    if (!link) return;
    const focus = () => setHovered(true);
    const blur = () => setHovered(false);
    link.addEventListener('focus', focus);
    link.addEventListener('blur', blur);
    return () => {
      link.removeEventListener('focus', focus);
      link.removeEventListener('blur', blur);
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
      if (!motion.matches)
        timer = setInterval(() => setFrame((current) => (current + 1) % count), 650);
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
      ? 'Thumbnail failed'
      : ({
          queued: 'Queued',
          processing: 'Processing',
          failed: 'Thumbnail failed',
          unavailable: 'No Thumbnail',
        }[thumbnail?.state ?? ''] ?? 'No Thumbnail');
  return (
    <div
      ref={preview}
      className="recording-thumbnail"
      aria-label={`Thumbnail for ${recording.name}`}
      data-thumbnail-frame={frame}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      onFocus={() => setHovered(true)}
      onBlur={() => setHovered(false)}
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
      ) : thumbnail?.state === 'failed' ||
        (thumbnail?.state === 'unavailable' && thumbnail.issue) ||
        (failedUrl === url && !!url) ? (
        <StatusDiagnostic
          navigable={navigable}
          side="right"
          status={label}
          className="thumbnail-diagnostic"
          issues={[
            thumbnail?.issue ??
              'The thumbnail could not be loaded. Prepare Selected can retry missing or failed output.',
          ]}
        />
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
