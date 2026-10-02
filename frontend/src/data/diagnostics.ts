import type { Diagnostic } from './api-types';

/** Machine codes stay in API/logs; the UI explains the action once. */
export function diagnosticMessage(diagnostic: Diagnostic): string {
  const messages: Record<string, string> = {
    front_topic_unavailable: 'No usable raw camera stream was found.',
    front_topic_empty: 'The camera stream has no frames.',
    front_encoding_unsupported: 'No camera uses a supported image encoding (rgb8 or bgr8).',
    imu_topic_empty: 'The IMU stream has no samples.',
    topdown_video_unavailable: 'No top-down video was found.',
    topdown_timestamps_unavailable: 'No top-down timestamps were found.',
    catalog_source_changed: 'Source changed since the last scan. Rescan before preparing.',
  };
  return messages[diagnostic.code] ?? diagnostic.message;
}

export function conciseIssues(issues: string[]): string[] {
  return [
    ...new Set(
      issues
        .map((issue) => issue.replace(/\b(?:E_[A-Z0-9_]+|[a-z]+_[a-z0-9_]+):\s*/g, '').trim())
        .filter(Boolean),
    ),
  ];
}
