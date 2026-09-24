import type { Folder } from '../types';
// Demo archive: 30 folders, including repeated names and four levels of nesting.
export const folders: Folder[] = [
  {
    id: 'bunker',
    name: 'Bunker',
    children: [
      {
        id: 'bunker-tests',
        name: 'Field tests',
        children: [
          {
            id: 'bunker-2025',
            name: '2025',
            children: [
              { id: 'bunker-december', name: 'December' },
              { id: 'bunker-november', name: 'November' },
            ],
          },
        ],
      },
      { id: 'bunker-mapping', name: 'Mapping' },
      { id: 'bunker-localization', name: 'Localization' },
    ],
  },
  {
    id: 'lunar',
    name: 'Lunar',
    children: [
      {
        id: 'lunar-navigation',
        name: 'Navigation',
        children: [
          { id: 'lunar-long-range', name: 'Long range' },
          { id: 'lunar-obstacles', name: 'Obstacle avoidance' },
        ],
      },
      { id: 'lunar-low-light', name: 'Low light' },
      { id: 'lunar-terrain', name: 'Terrain' },
    ],
  },
  {
    id: 'calibration',
    name: 'Calibration',
    children: [
      { id: 'calibration-cameras', name: 'Cameras' },
      { id: 'calibration-lidar', name: 'LiDAR' },
      { id: 'calibration-imu', name: 'IMU' },
      { id: 'calibration-sync', name: 'Sensor sync' },
    ],
  },
  {
    id: 'outdoor',
    name: 'Outdoor',
    children: [
      { id: 'outdoor-campus', name: 'Campus' },
      { id: 'outdoor-forest', name: 'Forest' },
      { id: 'outdoor-underground', name: 'Underground' },
    ],
  },
  {
    id: 'simulation',
    name: 'Simulation',
    children: [
      { id: 'simulation-regression', name: 'Regression' },
      { id: 'simulation-playback', name: 'Scenario playback' },
    ],
  },
  {
    id: 'archive',
    name: 'Archive',
    children: [
      { id: 'archive-2025', name: '2025' },
      { id: 'archive-2024', name: '2024' },
    ],
  },
  { id: 'shared', name: 'Shared', children: [{ id: 'shared-incoming', name: 'Incoming' }] },
];
