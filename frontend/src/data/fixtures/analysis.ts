import type { Channel, Signal } from '../types';
import { emptyChannels, encoderChannels } from '../telemetry';

// Deterministic preview signals only; API telemetry keeps its recorded samples.
export const duration = 75;
export const startUnix = 1771027200;
const pointCount = 6_000;
function denseSignal(offset: number, amplitude: number, phase: number): number[] {
  return Array.from({ length: pointCount }, (_, i) => {
    const fluctuation =
      Math.sin(i * (0.73 + phase * 0.07)) * 0.15 +
      Math.sin(i * 2.17) * 0.09 +
      Math.sin(i * 0.041) * 0.24 +
      Math.sin(i * 0.007) * 0.35;
    const period = 463 + phase * 37;
    const distance = Math.abs((i % period) - (190 + phase * 23));
    const peak =
      Math.max(0, 1 - distance / (3 + phase)) * (Math.floor(i / period) % 3 === 1 ? -1.6 : 2.6);
    return offset + amplitude * (fluctuation + peak);
  });
}
const angular = (values: number[]): Signal => ({
  values,
  ticks: [4, 2, 0, -2, -4],
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
  ...emptyChannels(),
  ...Object.fromEntries(
    encoderChannels.map((name, index) => [
      name,
      {
        values: denseSignal(16 + index * 0.25, 3, index + 1),
        ticks: [30, 22.5, 15, 7.5, 0],
        unit: 'RPM',
        spokenUnit: 'revolutions per minute',
      },
    ]),
  ),
  'angular_velocity.x': angular(denseSignal(0, 0.6, 0)),
  'angular_velocity.y': angular(denseSignal(1.06, 0.7, 1)),
  'angular_velocity.z': angular(denseSignal(0.937, 0.8, 2)),
  'linear_acceleration.x': linear(denseSignal(0, 2.1, 3)),
  'linear_acceleration.y': linear(denseSignal(0, 1.8, 4)),
  'linear_acceleration.z': linear(denseSignal(9.81, 0.6, 5)),
};
export const analysisBundle = { duration, startUnix, channels };
