import { describe, expect, it } from 'vitest';
import {
  builderToCron,
  createDefaultCronBuilderState,
  cronToBuilder,
} from '@/components/schedules/cronBuilderUtils';

describe('cronBuilderUtils', () => {
  it('builds a weekday cron from the default builder state', () => {
    expect(builderToCron(createDefaultCronBuilderState())).toBe('0 9 * * 1-5');
  });

  it('parses supported cron expressions back into builder state', () => {
    expect(cronToBuilder('15 */4 * * *')).toEqual({
      mode: 'every_hours',
      interval: 4,
      minute: 15,
      hour: 0,
      daysOfWeek: [1, 2, 3, 4, 5],
      dayOfMonth: 1,
    });
  });

  it('returns null for unsupported cron expressions', () => {
    expect(cronToBuilder('0 9 1 1 *')).toBeNull();
  });
});
