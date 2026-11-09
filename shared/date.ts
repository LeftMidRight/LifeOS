/**
 * 日期与展示格式工具。
 *
 * 存储层统一用 UTC（ISO 8601，以 Z 结尾），原因很实际：
 * SQLite 里时间就是 TEXT，按字符串比较大小 —— 只有所有记录都用同一个时区表示，
 * 字典序才等于时间序。带 +08:00 的记录和 Z 结尾的记录混在一起会排错。
 *
 * 展示层则永远按设备本地时区渲染，所以「今天」对用户永远是对的。
 */

export function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

export function nowISO(): string {
  return new Date().toISOString();
}

export function toDate(input: string | Date): Date {
  return typeof input === 'string' ? new Date(input) : input;
}

/** 本地日期键：2026-11-09 */
export function toDayKey(input: string | Date): string {
  const d = toDate(input);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

/** 本地月份键：2026-11 */
export function toMonthKey(input: string | Date): string {
  const d = toDate(input);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`;
}

export function startOfDay(input: Date): Date {
  const d = new Date(input);
  d.setHours(0, 0, 0, 0);
  return d;
}

export function addDays(input: Date, n: number): Date {
  const d = new Date(input);
  d.setDate(d.getDate() + n);
  return d;
}

export function addMonths(input: Date, n: number): Date {
  return new Date(input.getFullYear(), input.getMonth() + n, 1);
}

export function formatClock(input: string | Date): string {
  const d = toDate(input);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

export function formatMoney(n: number, currency = 'CNY'): string {
  const symbol = currency === 'CNY' ? '¥' : currency === 'USD' ? '$' : `${currency} `;
  const fixed = Math.abs(n % 1) < 1e-9 ? 0 : 2;
  return `${symbol}${n.toLocaleString('zh-CN', { minimumFractionDigits: fixed, maximumFractionDigits: fixed })}`;
}

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

export function weekdayName(input: string | Date): string {
  return WEEKDAYS[toDate(input).getDay()] ?? '';
}

/** 今天 / 昨天 / 11月9日 周日 */
export function humanDay(input: string | Date): string {
  const d = toDate(input);
  const now = new Date();
  const diff = Math.round((startOfDay(now).getTime() - startOfDay(d).getTime()) / 86_400_000);
  if (diff === 0) return '今天';
  if (diff === 1) return '昨天';
  if (diff === 2) return '前天';
  const isThisYear = d.getFullYear() === now.getFullYear();
  return `${isThisYear ? '' : `${d.getFullYear()}年`}${d.getMonth() + 1}月${d.getDate()}日 ${weekdayName(d)}`;
}

/** 「刚刚 / 12 分钟前 / 15:39」 */
export function relativeTime(input: string | Date): string {
  const d = toDate(input);
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60_000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin} 分钟前`;
  if (toDayKey(d) === toDayKey(new Date())) return formatClock(d);
  return humanDay(d);
}

/** 某个月的 [起, 止) 区间（UTC ISO，可直接与库里的 occurred_at 比较） */
export function monthRange(monthKey: string): { from: string; to: string } {
  const [y, m] = monthKey.split('-').map(Number);
  const start = new Date(y ?? 1970, (m ?? 1) - 1, 1, 0, 0, 0, 0);
  const end = new Date(y ?? 1970, m ?? 1, 1, 0, 0, 0, 0);
  return { from: start.toISOString(), to: end.toISOString() };
}

/** 某一天的 [起, 止) 区间 */
export function dayRange(dayKey: string): { from: string; to: string } {
  const [y, m, d] = dayKey.split('-').map(Number);
  const start = new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1, 0, 0, 0, 0);
  return { from: start.toISOString(), to: addDays(start, 1).toISOString() };
}

/** 本周（周一起算）到今天结束的区间 */
export function weekRange(now: Date = new Date()): { from: string; to: string } {
  const day = now.getDay(); // 0 = 周日
  const mondayOffset = day === 0 ? -6 : 1 - day;
  const start = startOfDay(addDays(now, mondayOffset));
  const end = addDays(startOfDay(now), 1);
  return { from: start.toISOString(), to: end.toISOString() };
}
