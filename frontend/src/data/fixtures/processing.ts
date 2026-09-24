import type { Job } from '../types';
export function createProcessing(loadedAt: number) {
  const job = (
    id: string,
    name: string,
    minutesAgo: number,
    duration: number,
    outputs: number,
    size: string,
  ): Job => ({
    id,
    name,
    queuedAt: loadedAt - minutesAgo * 60_000,
    duration,
    outputs,
    size,
  });
  const queue: Job[] = [
    job('mapping', 'bunker_lidar_mapping_run_03_2025-12-29_09-45-00.bag', 8, 280, 3, '8.74 GB'),
    job(
      'calibration',
      'outdoor_lidar_camera_calibration_2025-12-28_11-08-00.bag',
      6,
      140,
      2,
      '1.24 GB',
    ),
    job(
      'obstacles',
      'lunar_testing_obstacle_avoidance_2025-12-27_10-14-00.bag',
      4,
      210,
      3,
      '2.91 GB',
    ),
    job('sync', 'sensor_sync_validation_2025-12-26_08-30-00.bag', 2, 95, 1, '0.68 GB'),
  ];
  const failures: Job[] = [
    {
      ...job(
        'failed-low-light',
        'lunar_low_light_03_2025-12-22_10-17-00.bag',
        16,
        185,
        3,
        '2.16 GB',
      ),
      failures: [{ output: 'Top-down preview', code: 'E_RENDER_TIMEOUT' }],
    },
    {
      ...job(
        'failed-mapping',
        'bunker_lidar_mapping_05_2025-12-20_12-05-00.bag',
        23,
        250,
        3,
        '6.43 GB',
      ),
      failures: [
        {
          output: 'Front-camera preview',
          code: 'E_VIDEO_DECODE_UNSUPPORTED_PIXEL_FORMAT: Could not decode frame 1482 from /camera/front/image_raw; expected yuv420p, received bayer_rggb16.',
        },
        {
          output: 'Top-down preview',
          code: 'E_TRANSFORM_LOOKUP_EXTRAPOLATION: No transform from lidar_link to map at 1766232300.428. Requested timestamp is outside the available transform buffer.',
        },
      ],
    },
    {
      ...job('failed-imu', 'imu_calibration_02_2025-12-23_09-49-00.bag', 35, 110, 1, '1.85 GB'),
      failures: [{ output: 'IMU data bundle', code: 'E_INVALID_TIMESTAMP' }],
    },
  ];
  const history: Job[] = [
    job('history-bunker', 'bunker_testing_2025-12-30_10-25-00.bag', 12, 221, 3, '842 MB'),
    job('history-lunar', 'lunar_testing_low_light_2025-12-29_14-10-00.bag', 24, 194, 2, '486 MB'),
    job(
      'history-terrain',
      'lunar_terrain_navigation_long_range_2025-12-28_16-32-00.bag',
      32,
      317,
      3,
      '1.12 GB',
    ),
    job(
      'history-localization',
      'bunker_localization_loop_closure_2025-12-27_15-20-00.bag',
      45,
      402,
      3,
      '1.64 GB',
    ),
  ].map((item) => ({ ...item, completedAt: item.queuedAt + item.duration * 1000 }));
  const active = {
    name: 'LunaTesting_MBS_01',
    elapsed: 48,
    duration: 221,
    paused: false,
    cancelled: false,
  };

  return { queue, failures, history, active };
}
