import { useMemo, useState } from 'react';
import type { Entry } from '../../../shared/schema.ts';
import { addMonths, formatMoney, humanDay, monthRange, toDayKey, toMonthKey } from '../../../shared/date.ts';
import EntryItem from './EntryItem.tsx';
import type { ViewProps } from './types.ts';
import { IconChevronLeft, IconChevronRight } from './Icons.tsx';

/** 记账视图：这里回答的唯一问题是「这个月钱去哪了」。 */
export default function LedgerView({ entries }: ViewProps) {
  const currentMonth = toMonthKey(new Date());
  const [monthKey, setMonthKey] = useState(currentMonth);

  const range = useMemo(() => monthRange(monthKey), [monthKey]);

  const monthEntries = useMemo(
    () => entries.filter((entry) => entry.occurredAt >= range.from && entry.occurredAt < range.to),
    [entries, range],
  );

  const expenses = monthEntries.filter((entry) => entry.kind === 'expense' && entry.amount !== null);
  const total = expenses.reduce((sum, entry) => sum + (entry.amount ?? 0), 0);

  const byCategory = useMemo(() => {
    const map = new Map<string, { total: number; count: number }>();
    for (const entry of expenses) {
      const key = entry.category ?? '其他';
      const current = map.get(key) ?? { total: 0, count: 0 };
      current.total += entry.amount ?? 0;
      current.count += 1;
      map.set(key, current);
    }
    return [...map.entries()].sort((a, b) => b[1].total - a[1].total);
  }, [expenses]);

  const maxCategory = byCategory[0]?.[1].total ?? 1;

  const daysElapsed = monthKey === currentMonth ? new Date().getDate() : new Date(
    Number(monthKey.slice(0, 4)),
    Number(monthKey.slice(5, 7)),
    0,
  ).getDate();

  const dailyAverage = daysElapsed > 0 ? total / daysElapsed : 0;

  const grouped = useMemo(() => {
    const map = new Map<string, Entry[]>();
    for (const entry of expenses) {
      const key = toDayKey(entry.occurredAt);
      const list = map.get(key);
      if (list) list.push(entry);
      else map.set(key, [entry]);
    }
    return [...map.entries()];
  }, [expenses]);

  function shiftMonth(direction: -1 | 1) {
    const year = Number(monthKey.slice(0, 4));
    const month = Number(monthKey.slice(5, 7));
    const next = toMonthKey(addMonths(new Date(year, month - 1, 1), direction));
    if (next > currentMonth) return;
    setMonthKey(next);
  }

  const [year, month] = monthKey.split('-');

  return (
    <div>
      <div className="month-switch">
        <button className="icon-btn" onClick={() => shiftMonth(-1)} aria-label="上个月">
          <IconChevronLeft size={17} />
        </button>
        <span className="month-label">
          {year} 年 {Number(month)} 月
        </span>
        <button
          className="icon-btn"
          onClick={() => shiftMonth(1)}
          aria-label="下个月"
          disabled={monthKey >= currentMonth}
          style={{ opacity: monthKey >= currentMonth ? 0.3 : 1 }}
        >
          <IconChevronRight size={17} />
        </button>
      </div>

      <div className="ledger-hero">
        <div className="big-number">{formatMoney(total)}</div>
        <div className="ledger-stats">
          <span>
            日均 <b>{formatMoney(Math.round(dailyAverage))}</b>
          </span>
          <span>
            笔数 <b>{expenses.length}</b>
          </span>
          <span>
            分类 <b>{byCategory.length}</b>
          </span>
        </div>
      </div>

      {expenses.length === 0 ? (
        <div className="empty" style={{ marginTop: 24 }}>
          这个月还没有记账。
          <br />
          在「捕捉」里写「午饭 32 元」就会自动归到这里。
        </div>
      ) : (
        <>
          <div className="bars">
            {byCategory.map(([category, value]) => (
              <div className="bar-row" key={category}>
                <span className="bar-label">{category}</span>
                <span className="bar-track">
                  <span className="bar-fill" style={{ width: `${Math.max(3, (value.total / maxCategory) * 100)}%` }} />
                </span>
                <span className="bar-value">{formatMoney(value.total)}</span>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 32 }}>
            {grouped.map(([day, list]) => (
              <section className="day-group" key={day}>
                <div className="day-head">
                  <h2 className="day-title">{humanDay(list[0]?.occurredAt ?? day)}</h2>
                  <span className="day-sum">{formatMoney(list.reduce((sum, e) => sum + (e.amount ?? 0), 0))}</span>
                </div>
                {list.map((entry) => (
                  <EntryItem key={entry.id} entry={entry} />
                ))}
              </section>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
