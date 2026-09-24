import type { Page, Route } from '@playwright/test';
import type { ApiJob, Catalog, Detail, Kind, Output } from '../src/data/api-types';
const kinds: Kind[] = ['front_preview', 'topdown_preview', 'imu_series'];
export const diagnostic = {
  code: 'synthetic_failure',
  message: '<script>not markup</script> Output failed.',
};
export function detail(id = 42): Detail {
  const outputs: Output[] = kinds.map((kind, index) => ({
    kind,
    state: 'ready',
    diagnostic: null,
    artifact: {
      id: index + 1,
      url: `/api/recordings/${id}/${['front-preview/media', 'topdown-preview/media', 'imu-series/data'][index]}/${index + 1}`,
      mime_type: index === 2 ? 'application/json' : 'video/mp4',
      size_bytes: '1024',
      coverage_start_ns: '1000000000',
      coverage_end_ns: '4000000000',
    },
  }));
  return {
    id,
    name: `recording-${id}`,
    folder_path: 'experiments/session',
    start_time_ns: '1767083100000000000',
    duration_ns: '6000000000',
    total_source_size_bytes: '1048576',
    storage_format: 'sqlite3',
    topic_count: 2,
    presentation_health: 'readable',
    analysis_state: 'ready',
    diagnostic: null,
    outputs,
    message_count: '500',
    source_present: true,
    components: [
      {
        role: 'ros_database',
        condition: 'readable',
        file_name: 'bag.db3',
        size_bytes: '1048576',
        diagnostic: null,
      },
    ],
  };
}
export function job(id: number, kind: Kind = 'front_preview'): ApiJob {
  return {
    id,
    recording_id: 45,
    recording_name: 'recording-42',
    kind,
    state: 'queued',
    queued_at: '2026-09-24T10:00:00Z',
    finished_at: null,
    elapsed_ms: null,
    active_elapsed_ms: null,
    runtime_ms: null,
    diagnostic: null,
    output_size_bytes: null,
    estimate: null,
    queue_estimate: null,
    control_state: 'none',
    allowed_controls: ['cancel', 'move_earlier', 'move_later'],
  };
}
export function telemetry() {
  const components = [
    'angular_velocity.x',
    'angular_velocity.y',
    'angular_velocity.z',
    'linear_acceleration.x',
    'linear_acceleration.y',
    'linear_acceleration.z',
  ];
  const values = [1, 8, 9, null, 4];
  return {
    state: {
      state: 'ready',
      artifact: {
        data_url: '/api/recordings/42/imu-series/data/3',
        size_bytes: '1024',
        coverage_start_ns: '1000000000',
        coverage_end_ns: '4000000000',
        delivered_sample_count: '5',
        default_series_id: 'angular_velocity_z',
        series: components.map((component, index) => ({
          id: component.replace('.', '_'),
          component,
          display_label: component,
          units: index < 3 ? 'rad/s' : 'm/s²',
          column_index: index + 1,
          finite_sample_count: '4',
          non_finite_sample_count: '1',
          minimum_value: 1,
          maximum_value: 9,
          available: true,
        })),
      },
    },
    data: {
      schema_version: 2,
      samples: ['1000000000', '2000000000', '2000000000', '2500000000', '4000000000'].map(
        (time, i) => [time, ...Array(6).fill(values[i])],
      ),
    },
  };
}
export async function apiFixture(page: Page) {
  const recording = detail();
  const review = { ...detail(43), duration_ns: '0', analysis_state: 'not_planned', outputs: [] };
  const partial = { ...detail(44), analysis_state: 'not_planned', outputs: [recording.outputs[0]] };
  const catalog: Catalog = {
    scan: { completed_at: '2026-09-24T09:00:00Z' },
    folders: [
      { path: 'experiments', parent_path: '', name: 'experiments' },
      { path: 'experiments/session', parent_path: 'experiments', name: 'session' },
    ],
    recordings: [recording, review, partial],
  };
  const state = {
    catalog,
    recording,
    queue: [job(10), job(11, 'imu_series')],
    failures: [{ ...job(12), state: 'failed', diagnostic }],
    history: [
      {
        ...job(13),
        state: 'succeeded',
        finished_at: '2026-09-24T10:01:00Z',
        runtime_ms: 65000,
        output_size_bytes: '2048',
      },
    ],
    active: {
      ...job(9),
      recording_id: 42,
      state: 'running',
      elapsed_ms: 12000,
      active_elapsed_ms: 10000,
      allowed_controls: ['pause', 'cancel'],
    } as ApiJob | null,
    posts: [] as { path: string; body: unknown }[],
    requests: [] as string[],
    override: null as ((route: Route, path: string) => Promise<boolean>) | null,
    imu: telemetry(),
  };
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname;
    state.requests.push(path);
    if (state.override && (await state.override(route, path))) return;
    const json = (value: unknown, status = 200) => route.fulfill({ status, json: value });
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      state.posts.push({ path, body });
      if (path.endsWith('/rescan')) return json({ scan: state.catalog.scan, diagnostics: [] });
      if (path.endsWith('/prepare'))
        return json(
          {
            recordings: [
              { outputs: kinds.map((kind) => ({ kind, outcome: 'queued', state: 'queued' })) },
            ],
          },
          202,
        );
      if (path.endsWith('/jobs/cancel')) {
        state.queue = [];
        return json({ items: [{ outcome: 'canceled' }] });
      }
      if (path.endsWith('/jobs/retry')) {
        state.failures = [];
        return json({ items: [{ outcome: 'queued', state: 'queued' }] });
      }
      if (path.endsWith('/pause') && state.active) {
        state.active.control_state = 'pause_requested';
        state.active.allowed_controls = ['cancel'];
        return json({ outcome: 'requested' }, 202);
      }
      if (path.endsWith('/resume') && state.active) {
        state.active.control_state = 'none';
        state.active.allowed_controls = ['pause', 'cancel'];
        return json({ outcome: 'resumed' });
      }
      if (path.endsWith('/cancel') && state.active) {
        state.active.control_state = 'cancel_requested';
        state.active.allowed_controls = [];
        return json({ outcome: 'requested' }, 202);
      }
    }
    if (path === '/api/v1/catalog') return json(state.catalog);
    if (path === '/api/v1/processing/overview')
      return json({
        current: state.active,
        queue: state.queue,
        worker_online: true,
        recommended_poll_interval_ms: 1000,
      });
    if (path === '/api/v1/processing/jobs') {
      const view = url.searchParams.get('view');
      return json({
        items: view === 'queued' ? state.queue : view === 'failed' ? state.failures : state.history,
        next_cursor: null,
      });
    }
    if (path === '/api/v1/recordings/42') return json(state.recording);
    if (path === '/api/recordings/42/imu-series') return json(state.imu.state);
    if (path === '/api/recordings/42/imu-series/data/3') return json(state.imu.data);
    if (path.includes('/media/')) return route.fulfill({ status: 404, body: '' });
    return json({ detail: { message: 'Recording not found.' } }, 404);
  });
  return state;
}
