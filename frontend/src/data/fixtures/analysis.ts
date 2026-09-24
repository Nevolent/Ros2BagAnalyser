import type { Channel, Signal } from '../types';
// Local preview fixture. Replace this bundle with timestamped IMU samples when
// archive outputs are connected; the clock and both camera adapters stay shared.
export const duration = 754.56;
export const startUnix = 1771027200;
const referenceY = [
  55.205, 54.228, 58.265, 51.536, 55.103, 47.983, 42.32, 48.402, 63.449, 60.975, 67.206, 59.678,
  67.853, 68.313, 51.21, 41.994, 47.039, 37.047, 42.771, 43.403, 41.613, 49.95, 39.409, 49.89,
  56.609, 47.416, 55.014, 56.818, 49.202, 45.384,
];
const angular = (values: number[], ticks = [2, 1, 0, -1, -2]): Signal => ({
  values,
  ticks,
  unit: 'rad/s',
  spokenUnit: 'radians per second',
});
const linear = (values: number[]): Signal => ({
  values,
  ticks: [12, 6, 0, -6, -12],
  unit: 'm/s²',
  spokenUnit: 'metres per second squared',
});
export const channels: Record<Channel, Signal> = {
  'angular_velocity.x': angular(
    referenceY.map((y, i) => Math.sin(i * 0.55) * 0.85 + (55 - y) / 40),
  ),
  'angular_velocity.y': angular(referenceY.map((y, i) => Math.cos(i * 0.4) * 0.6 + (y - 55) / 32)),
  'angular_velocity.z': angular(
    referenceY.map((y) => ((186 - y) / 186) * 4),
    [4, 3, 2, 1, 0],
  ),
  'linear_acceleration.x': linear(
    referenceY.map((y, i) => Math.sin(i * 0.45) * 2.5 + (55 - y) / 8),
  ),
  'linear_acceleration.y': linear(
    referenceY.map((y, i) => Math.cos(i * 0.35) * 1.8 + (y - 55) / 10),
  ),
  'linear_acceleration.z': linear(
    referenceY.map((y, i) => 9.81 + Math.sin(i * 0.6) * 0.7 + (55 - y) / 18),
  ),
};

export const analysisBundle = { duration, startUnix, channels };
