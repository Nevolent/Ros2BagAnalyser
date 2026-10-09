import { useLayoutEffect, useRef, useState } from 'react';
import type { Recording } from '../../data/types';
import { StatusDiagnostic } from './StatusDiagnostic';

export function RecordingThumbnail({ recording }: { recording: Recording }) {
  const thumbnail = recording.thumbnail;
  const [failedUrl, setFailedUrl] = useState('');
  const [loadedUrl, setLoadedUrl] = useState('');
  const url = thumbnail?.url;
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
    <div className="recording-thumbnail" aria-label={`Thumbnail for ${recording.name}`}>
      {url && failedUrl !== url ? (
        <>
          <img
            src={url}
            alt={`Camera scene from ${recording.name}`}
            loading="lazy"
            decoding="async"
            onLoad={() => setLoadedUrl(url)}
            onError={() => setFailedUrl(url)}
          />
          {loadedUrl !== url && <span className="thumbnail-loading">Loading…</span>}
        </>
      ) : thumbnail?.state === 'failed' || (failedUrl === url && !!url) ? (
        <StatusDiagnostic
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
