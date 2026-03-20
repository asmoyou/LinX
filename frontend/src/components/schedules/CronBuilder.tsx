import React from 'react';
import { useTranslation } from 'react-i18next';
import type { CronBuilderState } from './cronBuilderUtils';
import { WEEKDAY_OPTIONS } from './cronBuilderUtils';

interface CronBuilderProps {
  value: CronBuilderState;
  isSupported: boolean;
  onChange: (nextValue: CronBuilderState) => void;
}

function updateNumberField(
  value: CronBuilderState,
  key: keyof Pick<CronBuilderState, 'interval' | 'minute' | 'hour' | 'dayOfMonth'>,
  nextValue: string
): CronBuilderState {
  const numericValue = Number(nextValue);
  return {
    ...value,
    [key]: Number.isFinite(numericValue) ? numericValue : 0,
  };
}

export const CronBuilder: React.FC<CronBuilderProps> = ({ value, isSupported, onChange }) => {
  const { t } = useTranslation();
  const weekdayLabels: Record<number, string> = {
    1: t('schedules.builder.weekdays.mon', 'Mon'),
    2: t('schedules.builder.weekdays.tue', 'Tue'),
    3: t('schedules.builder.weekdays.wed', 'Wed'),
    4: t('schedules.builder.weekdays.thu', 'Thu'),
    5: t('schedules.builder.weekdays.fri', 'Fri'),
    6: t('schedules.builder.weekdays.sat', 'Sat'),
    0: t('schedules.builder.weekdays.sun', 'Sun'),
  };

  const toggleWeekday = (dayValue: number) => {
    const nextDays = value.daysOfWeek.includes(dayValue)
      ? value.daysOfWeek.filter((currentValue) => currentValue !== dayValue)
      : [...value.daysOfWeek, dayValue];
    onChange({
      ...value,
      daysOfWeek: nextDays,
    });
  };

  return (
    <div className="space-y-4 rounded-3xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-900/50 p-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {t('schedules.builder.title', '可视化计划配置')}
          </p>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {t(
              'schedules.builder.subtitle',
              '支持常见频率，复杂 cron 仍可在下方高级区直接编辑。'
            )}
          </p>
        </div>
        {!isSupported && (
          <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[11px] font-semibold text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300">
            {t('schedules.builder.unsupported', '当前 cron 超出可视化模式')}
          </span>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <label className="space-y-2">
          <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
            {t('schedules.builder.mode', '模式')}
          </span>
          <select
            aria-label={t('schedules.builder.mode', '模式')}
            value={value.mode}
            onChange={(event) =>
              onChange({
                ...value,
                mode: event.target.value as CronBuilderState['mode'],
              })
            }
            className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
          >
            <option value="every_minutes">{t('schedules.builder.modes.everyMinutes', '每 N 分钟')}</option>
            <option value="every_hours">{t('schedules.builder.modes.everyHours', '每 N 小时')}</option>
            <option value="daily">{t('schedules.builder.modes.daily', '每天')}</option>
            <option value="weekdays">{t('schedules.builder.modes.weekdays', '工作日')}</option>
            <option value="weekly">{t('schedules.builder.modes.weekly', '每周多选')}</option>
            <option value="monthly">{t('schedules.builder.modes.monthly', '每月某日')}</option>
          </select>
        </label>

        {value.mode === 'every_minutes' && (
          <label className="space-y-2">
            <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
              {t('schedules.builder.intervalMinutes', '间隔分钟')}
            </span>
            <input
              type="number"
              min={1}
              max={59}
              value={value.interval}
              onChange={(event) => onChange(updateNumberField(value, 'interval', event.target.value))}
              className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
            />
          </label>
        )}

        {value.mode === 'every_hours' && (
          <>
            <label className="space-y-2">
              <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
                {t('schedules.builder.intervalHours', '间隔小时')}
              </span>
              <input
                type="number"
                min={1}
                max={23}
                value={value.interval}
                onChange={(event) =>
                  onChange(updateNumberField(value, 'interval', event.target.value))
                }
                className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              />
            </label>
            <label className="space-y-2">
              <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
                {t('schedules.builder.minuteOfHour', '每次执行的分钟')}
              </span>
              <input
                type="number"
                min={0}
                max={59}
                value={value.minute}
                onChange={(event) => onChange(updateNumberField(value, 'minute', event.target.value))}
                className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              />
            </label>
          </>
        )}

        {(value.mode === 'daily' || value.mode === 'weekdays' || value.mode === 'weekly' || value.mode === 'monthly') && (
          <>
            <label className="space-y-2">
              <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
                {t('schedules.builder.hour', '小时')}
              </span>
              <input
                type="number"
                min={0}
                max={23}
                value={value.hour}
                onChange={(event) => onChange(updateNumberField(value, 'hour', event.target.value))}
                className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              />
            </label>
            <label className="space-y-2">
              <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
                {t('schedules.builder.minute', '分钟')}
              </span>
              <input
                type="number"
                min={0}
                max={59}
                value={value.minute}
                onChange={(event) => onChange(updateNumberField(value, 'minute', event.target.value))}
                className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              />
            </label>
          </>
        )}

        {value.mode === 'monthly' && (
          <label className="space-y-2">
            <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
              {t('schedules.builder.dayOfMonth', '每月日期')}
            </span>
            <input
              type="number"
              min={1}
              max={31}
              value={value.dayOfMonth}
              onChange={(event) => onChange(updateNumberField(value, 'dayOfMonth', event.target.value))}
              className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
            />
          </label>
        )}
      </div>

      {value.mode === 'weekly' && (
        <div className="space-y-2">
          <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
            {t('schedules.builder.weekdaysLabel', '星期')}
          </span>
          <div className="flex flex-wrap gap-2">
            {WEEKDAY_OPTIONS.map((option) => {
              const active = value.daysOfWeek.includes(option.value);
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => toggleWeekday(option.value)}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                    active
                      ? 'bg-emerald-500 text-white'
                      : 'border border-zinc-200 bg-white text-zinc-600 hover:border-emerald-300 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300'
                  }`}
                >
                  {weekdayLabels[option.value] || option.label}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
