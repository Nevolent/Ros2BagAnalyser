import type { Recording } from '../types';
const mockFolders: [string, string, number][] = [
  ['bunker-december', 'bunker_field_test', 18],
  ['bunker-november', 'bunker_night_run', 12],
  ['bunker-mapping', 'bunker_lidar_mapping', 16],
  ['bunker-localization', 'bunker_loop_closure', 14],
  ['lunar-long-range', 'lunar_long_range', 15],
  ['lunar-obstacles', 'lunar_obstacle_avoidance', 12],
  ['lunar-low-light', 'lunar_low_light', 11],
  ['lunar-terrain', 'lunar_terrain', 9],
  ['calibration-cameras', 'camera_calibration', 10],
  ['calibration-lidar', 'lidar_calibration', 8],
  ['calibration-imu', 'imu_calibration', 6],
  ['calibration-sync', 'sensor_sync', 7],
  ['outdoor-campus', 'campus_navigation', 14],
  ['outdoor-forest', 'forest_trail', 11],
  ['outdoor-underground', 'underground_mapping', 9],
  ['simulation-regression', 'regression', 8],
  ['simulation-playback', 'scenario_playback', 6],
  ['archive-2025', 'archive_field_test', 10],
  ['archive-2024', 'archive_baseline', 7],
];

export function createRecordings(): Recording[] {
  const bags: Recording[] = [
    {
      id: 'bunker_testing_2025-12-30_10-25-00.bag',
      name: 'bunker_testing_2025-12-30_10-25-00.bag',
      folderId: 'bunker-december',
      recordedAt: '2025-12-30T10:25:00+02:00',
      duration: '12:34.560',
      size: '4.82 GB',
      health: 'Readable',
      analysis: 'Ready',
    },
    {
      id: 'lunar_testing_low_light_2025-12-29_14-10-00.bag',
      name: 'lunar_testing_low_light_2025-12-29_14-10-00.bag',
      folderId: 'lunar-low-light',
      recordedAt: '2025-12-29T14:10:00+02:00',
      duration: '08:42.315',
      size: '2.16 GB',
      health: 'Readable',
      analysis: 'Ready',
    },
    {
      id: 'bunker_lidar_mapping_run_03_2025-12-29_09-45-00.bag',
      name: 'bunker_lidar_mapping_run_03_2025-12-29_09-45-00.bag',
      folderId: 'bunker-mapping',
      recordedAt: '2025-12-29T09:45:00+02:00',
      duration: '24:16.082',
      size: '8.74 GB',
      health: 'Readable',
      analysis: 'Not planned',
    },
    {
      id: 'lunar_terrain_navigation_long_range_2025-12-28_16-32-00.bag',
      name: 'lunar_terrain_navigation_long_range_2025-12-28_16-32-00.bag',
      folderId: 'lunar-long-range',
      recordedAt: '2025-12-28T16:32:00+02:00',
      duration: '18:05.740',
      size: '6.38 GB',
      health: 'Readable',
      analysis: 'Ready',
    },
    {
      id: 'outdoor_lidar_camera_calibration_2025-12-28_11-08-00.bag',
      name: 'outdoor_lidar_camera_calibration_2025-12-28_11-08-00.bag',
      folderId: 'calibration-cameras',
      recordedAt: '2025-12-28T11:08:00+02:00',
      duration: '03:28.196',
      size: '1.24 GB',
      health: 'Readable',
      analysis: 'Not planned',
    },
    {
      id: 'bunker_localization_loop_closure_2025-12-27_15-20-00.bag',
      name: 'bunker_localization_loop_closure_2025-12-27_15-20-00.bag',
      folderId: 'bunker-localization',
      recordedAt: '2025-12-27T15:20:00+02:00',
      duration: '32:11.905',
      size: '12.60 GB',
      health: 'Readable',
      analysis: 'Ready',
    },
    {
      id: 'lunar_testing_obstacle_avoidance_2025-12-27_10-14-00.bag',
      name: 'lunar_testing_obstacle_avoidance_2025-12-27_10-14-00.bag',
      folderId: 'lunar-obstacles',
      recordedAt: '2025-12-27T10:14:00+02:00',
      duration: '06:52.430',
      size: '2.91 GB',
      health: 'Readable',
      analysis: 'Not planned',
    },
    {
      id: 'sensor_sync_validation_2025-12-26_08-30-00.bag',
      name: 'sensor_sync_validation_2025-12-26_08-30-00.bag',
      folderId: 'calibration-sync',
      recordedAt: '2025-12-26T08:30:00+02:00',
      duration: '01:46.028',
      size: '0.68 GB',
      health: 'Readable',
      analysis: 'Not planned',
    },
  ];
  let sequence = 0;
  mockFolders.forEach(([folderId, prefix, count]) => {
    for (let i = 0; i < count; i++) {
      sequence++;
      const month = folderId === 'bunker-november' ? 10 : 11;
      const date = new Date(
        Date.UTC(
          folderId === 'archive-2024' ? 2024 : 2025,
          month,
          24 - i,
          8 + (i % 10),
          (sequence * 7) % 60,
        ),
      );
      const stamp = date.toISOString().slice(0, 19).replace('T', '_').replaceAll(':', '-');
      const name = `${prefix}_${String(i + 1).padStart(2, '0')}_${stamp}.bag`;
      bags.push({
        id: name,
        health: sequence % 21 === 0 ? 'Damaged' : 'Readable',
        name: `${prefix}_${String(i + 1).padStart(2, '0')}_${stamp}.bag`,
        folderId,
        recordedAt: date.toISOString(),
        duration: `${String(3 + ((sequence * 7) % 42)).padStart(2, '0')}:${String((sequence * 13) % 60).padStart(2, '0')}.${String((sequence * 137) % 1000).padStart(3, '0')}`,
        size: `${(0.48 + ((sequence * 1.37) % 14)).toFixed(2)} GB`,
        analysis: sequence % 7 === 0 ? 'Failed' : sequence % 3 === 0 ? 'Not planned' : 'Ready',
      });
    }
  });

  return bags.map((bag) => ({
    ...bag,
    healthIssues:
      bag.health === 'Damaged' ? ['E_SQLITE_INTEGRITY: source recording is damaged.'] : [],
  }));
}
