import type { AnalysisRecording } from '../types';
import { analysisBundle } from './analysis';
export const analysisRecording: AnalysisRecording = {
  name: 'bunker_testing_2025-12-30_10-25-00.bag',
  bundle: analysisBundle,
  info: [
    {
      label: 'Recorded',
      value: '30/12/2025, 10:25',
      kind: 'time',
      dateTime: '2025-12-30T10:25:00+02:00',
    },
    {
      label: 'Duration',
      value: '12:34.560',
      kind: 'text',
    },
    {
      label: 'Source size',
      value: '4.82 GB',
      kind: 'text',
    },
    {
      label: 'Storage',
      value: 'sqlite3',
      kind: 'code',
    },
    {
      label: 'Messages',
      value: '2,486',
      kind: 'text',
    },
    {
      label: 'Topics',
      value: '12',
      kind: 'text',
    },
    {
      label: 'ROS database',
      value: 'Readable',
      kind: 'status',
    },
  ],
  outputs: [
    {
      name: 'Front-camera preview',
      size: '2.11 KiB',
      format: 'MP4 · H.264',
      status: 'Ready',
    },
    {
      name: 'Top-down preview',
      size: '2.11 KiB',
      format: 'MP4 · H.264',
      status: 'Ready',
    },
    {
      name: 'IMU data bundle',
      size: '4.00 KiB',
      format: 'JSON',
      status: 'Ready',
    },
  ],
  sources: [
    {
      name: 'ROS metadata',
      size: '3.73 KiB',
      format: 'metadata.yaml',
      status: 'Readable',
    },
    {
      name: 'Rosbag',
      size: '4.82 GB',
      format: 'data_0.db3',
      status: 'Readable',
    },
  ],
  cameras: [
    {
      id: 'front',
      label: 'Front',
      region: 'Front camera view',
      src: '/assets/front-camera-lunar-bunker.png',
      alt: 'Front camera view of a ROS rover in a lunar observatory testing bunker',
    },
    {
      id: 'top',
      label: 'Top',
      region: 'Top down camera view',
      src: '/assets/top-down-lunar-bunker.png',
      alt: 'Top down camera view of the ROS rover in the testing bunker',
    },
  ],
};
