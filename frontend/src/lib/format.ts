const dateFormat = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/Tallinn',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});
/** Calendar timestamps share a single locale and workspace timezone. */
export const formatDateTime = (value: string | number | Date) => dateFormat.format(new Date(value));
export const formatJobDate = formatDateTime;
export const formatDuration = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
