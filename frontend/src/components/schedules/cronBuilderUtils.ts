export type CronBuilderMode =
  | 'every_minutes'
  | 'every_hours'
  | 'daily'
  | 'weekdays'
  | 'weekly'
  | 'monthly';

export interface CronBuilderState {
  mode: CronBuilderMode;
  interval: number;
  minute: number;
  hour: number;
  daysOfWeek: number[];
  dayOfMonth: number;
}

export const WEEKDAY_OPTIONS = [
  { value: 1, label: 'Mon' },
  { value: 2, label: 'Tue' },
  { value: 3, label: 'Wed' },
  { value: 4, label: 'Thu' },
  { value: 5, label: 'Fri' },
  { value: 6, label: 'Sat' },
  { value: 0, label: 'Sun' },
] as const;

export function createDefaultCronBuilderState(): CronBuilderState {
  return {
    mode: 'weekdays',
    interval: 1,
    minute: 0,
    hour: 9,
    daysOfWeek: [1, 2, 3, 4, 5],
    dayOfMonth: 1,
  };
}

function clampInteger(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.round(value)));
}

function normalizeWeekdays(values: number[]): number[] {
  return [...new Set(values.map((value) => (value === 7 ? 0 : value)).filter((value) => value >= 0 && value <= 6))]
    .sort((left, right) => left - right);
}

function isDigits(value: string): boolean {
  return /^\d+$/.test(value);
}

export function builderToCron(builder: CronBuilderState): string {
  const minute = clampInteger(builder.minute, 0, 59, 0);
  const hour = clampInteger(builder.hour, 0, 23, 9);
  const interval = clampInteger(builder.interval, 1, 59, 1);
  const dayOfMonth = clampInteger(builder.dayOfMonth, 1, 31, 1);
  const daysOfWeek = normalizeWeekdays(builder.daysOfWeek);

  switch (builder.mode) {
    case 'every_minutes':
      return `*/${interval} * * * *`;
    case 'every_hours':
      return `${minute} */${clampInteger(builder.interval, 1, 23, 1)} * * *`;
    case 'daily':
      return `${minute} ${hour} * * *`;
    case 'weekdays':
      return `${minute} ${hour} * * 1-5`;
    case 'weekly':
      return `${minute} ${hour} * * ${daysOfWeek.length > 0 ? daysOfWeek.join(',') : '1'}`;
    case 'monthly':
      return `${minute} ${hour} ${dayOfMonth} * *`;
    default:
      return `${minute} ${hour} * * 1-5`;
  }
}

export function cronToBuilder(expression: string): CronBuilderState | null {
  const normalized = String(expression || '').trim().replace(/\s+/g, ' ');
  const fields = normalized.split(' ');
  if (fields.length !== 5) {
    return null;
  }

  const [minute, hour, dayOfMonth, month, dayOfWeek] = fields;

  if (minute.startsWith('*/') && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    const interval = Number(minute.slice(2));
    if (!Number.isFinite(interval)) {
      return null;
    }
    return {
      mode: 'every_minutes',
      interval: clampInteger(interval, 1, 59, 1),
      minute: 0,
      hour: 0,
      daysOfWeek: [1, 2, 3, 4, 5],
      dayOfMonth: 1,
    };
  }

  if (isDigits(minute) && hour.startsWith('*/') && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    const interval = Number(hour.slice(2));
    if (!Number.isFinite(interval)) {
      return null;
    }
    return {
      mode: 'every_hours',
      interval: clampInteger(interval, 1, 23, 1),
      minute: clampInteger(Number(minute), 0, 59, 0),
      hour: 0,
      daysOfWeek: [1, 2, 3, 4, 5],
      dayOfMonth: 1,
    };
  }

  if (isDigits(minute) && isDigits(hour) && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    return {
      mode: 'daily',
      interval: 1,
      minute: clampInteger(Number(minute), 0, 59, 0),
      hour: clampInteger(Number(hour), 0, 23, 9),
      daysOfWeek: [1, 2, 3, 4, 5],
      dayOfMonth: 1,
    };
  }

  if (isDigits(minute) && isDigits(hour) && dayOfMonth === '*' && month === '*' && dayOfWeek === '1-5') {
    return {
      mode: 'weekdays',
      interval: 1,
      minute: clampInteger(Number(minute), 0, 59, 0),
      hour: clampInteger(Number(hour), 0, 23, 9),
      daysOfWeek: [1, 2, 3, 4, 5],
      dayOfMonth: 1,
    };
  }

  if (isDigits(minute) && isDigits(hour) && dayOfMonth === '*' && month === '*' && /^[0-7](,[0-7])*$/.test(dayOfWeek)) {
    return {
      mode: 'weekly',
      interval: 1,
      minute: clampInteger(Number(minute), 0, 59, 0),
      hour: clampInteger(Number(hour), 0, 23, 9),
      daysOfWeek: normalizeWeekdays(dayOfWeek.split(',').map(Number)),
      dayOfMonth: 1,
    };
  }

  if (isDigits(minute) && isDigits(hour) && isDigits(dayOfMonth) && month === '*' && dayOfWeek === '*') {
    return {
      mode: 'monthly',
      interval: 1,
      minute: clampInteger(Number(minute), 0, 59, 0),
      hour: clampInteger(Number(hour), 0, 23, 9),
      daysOfWeek: [1, 2, 3, 4, 5],
      dayOfMonth: clampInteger(Number(dayOfMonth), 1, 31, 1),
    };
  }

  return null;
}
