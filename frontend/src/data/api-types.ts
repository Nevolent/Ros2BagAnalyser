/** Wire contracts owned by src/rosbag_analyser/api/v1_schemas.py. */
export type Kind = 'front_preview' | 'topdown_preview' | 'imu_series';
export interface Diagnostic {
  code: string;
  message: string;
}
export interface Artifact {
  id: number;
  url: string;
  mime_type: string;
  size_bytes: string;
  coverage_start_ns: string;
  coverage_end_ns: string;
}
export interface Output {
  kind: Kind;
  state: string;
  job_id?: number | null;
  diagnostic: Diagnostic | null;
  artifact?: Artifact | null;
}
export interface CatalogRecording {
  id: number;
  name: string;
  folder_path: string;
  start_time_ns: string | null;
  duration_ns: string | null;
  total_source_size_bytes: string | null;
  storage_format: string | null;
  topic_count: number | null;
  presentation_health: string;
  analysis_state: string;
  diagnostic: Diagnostic | null;
  outputs: Output[];
}
export interface Catalog {
  scan: { completed_at: string | null };
  folders: { path: string; parent_path: string; name: string }[];
  recordings: CatalogRecording[];
}
export interface Detail extends CatalogRecording {
  message_count: string | null;
  source_present: boolean;
  components: {
    role: string;
    condition: string;
    file_name: string | null;
    size_bytes: string | null;
    diagnostic: Diagnostic | null;
  }[];
}
export interface ApiJob {
  id: number;
  recording_id: number;
  recording_name: string;
  kind: Kind;
  state: string;
  queued_at: string;
  finished_at: string | null;
  elapsed_ms: number | null;
  active_elapsed_ms: number | null;
  runtime_ms: number | null;
  diagnostic: Diagnostic | null;
  output_size_bytes: string | null;
  estimate: {
    status: 'available' | 'unavailable' | 'exceeded';
    estimated_total_ms: number | null;
  } | null;
  queue_estimate: { status: string; ready_in_ms: number | null } | null;
  control_state: string;
  allowed_controls: string[];
}
export interface Overview {
  current: ApiJob | null;
  queue: ApiJob[];
  worker_online: boolean;
  recommended_poll_interval_ms: number;
}
export interface JobsPage {
  items: ApiJob[];
  next_cursor: string | null;
}
