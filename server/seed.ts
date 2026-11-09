/**
 * 演示数据。跑 `npm run seed` 灌入一批真实语感的记录，方便先看到界面长什么样。
 * 默认只在库为空时写入；加 --force 会强制追加。
 */
import { db } from './db.ts';
import { createEntry } from './repo.ts';
import { parseCapture } from '../shared/capture.ts';
import { nowISO } from '../shared/date.ts';

interface SeedItem {
  /** 几天前 */
  daysAgo: number;
  hour: number;
  minute?: number;
  text: string;
}

const ITEMS: SeedItem[] = [
  { daysAgo: 0, hour: 8, minute: 20, text: '早上跑了 3 公里，风有点凉，但跑完脑子很清醒' },
  { daysAgo: 0, hour: 9, minute: 5, text: '记得今天下午把方案发出去' },
  { daysAgo: 0, hour: 12, minute: 30, text: '午饭 28 元 食堂' },
  { daysAgo: 0, hour: 14, minute: 10, text: '突然想到一个点子，LifeOS 不该有四个模块，应该是一条流 #产品' },
  { daysAgo: 0, hour: 16, minute: 45, text: '打车 32' },
  { daysAgo: 0, hour: 21, minute: 15, text: '今天开了三个会，脑子有点糊。回来的路上一直在想那个架构问题，后来在地铁上突然想通了：其实不需要同步层，服务端就是唯一真相。' },
  { daysAgo: 1, hour: 9, minute: 0, text: 'todo: 预约牙医' },
  { daysAgo: 1, hour: 10, minute: 30, text: '咖啡 22' },
  { daysAgo: 1, hour: 13, minute: 0, text: '午饭 35 元 和同事' },
  { daysAgo: 1, hour: 19, minute: 40, text: '买书 89 元《系统之美》，翻了前两章就停不下来' },
  { daysAgo: 1, hour: 22, minute: 0, text: '感觉最近睡眠不太好，可能是因为睡前看手机太久' },
  { daysAgo: 2, hour: 8, minute: 45, text: '地铁 6' },
  { daysAgo: 2, hour: 12, minute: 15, text: '午饭 26 元 面馆' },
  { daysAgo: 2, hour: 20, minute: 30, text: '晚饭 68 元 和同事聚餐 #社交' },
  { daysAgo: 2, hour: 23, minute: 10, text: '在想要不要换掉现在这套技术栈，重写成本太高，但维护成本也高 #技术' },
  { daysAgo: 3, hour: 10, minute: 20, text: '记得周五前把预算表整理好' },
  { daysAgo: 3, hour: 15, minute: 45, text: '奶茶 18' },
  { daysAgo: 3, hour: 19, minute: 0, text: '电影票 70，看了一半就困了' },
  { daysAgo: 4, hour: 11, minute: 30, text: '交房租 4200' },
  { daysAgo: 4, hour: 18, minute: 20, text: '这个月的电费 260，比上个月多了不少' },
  { daysAgo: 5, hour: 9, minute: 40, text: '想到一个产品点子：把待办和日记合在一起，做完的事自动变成回顾 #产品 #灵感' },
  { daysAgo: 5, hour: 21, minute: 0, text: '给爸妈打电话了吗？' },
];

const force = process.argv.includes('--force');
const existing = db.prepare('SELECT COUNT(*) AS n FROM entries').get() as { n: number };

if (existing.n > 0 && !force) {
  console.log(`库里已有 ${existing.n} 条记录，跳过。想强制追加请加 --force`);
  process.exit(0);
}

const now = new Date();
let created = 0;

for (const item of ITEMS) {
  const at = new Date(now);
  at.setDate(at.getDate() - item.daysAgo);
  at.setHours(item.hour, item.minute ?? 0, 0, 0);

  const parsed = parseCapture(item.text, at);
  createEntry({
    kind: parsed.kind,
    content: parsed.content,
    occurredAt: at.toISOString(),
    amount: parsed.amount,
    currency: 'CNY',
    category: parsed.category,
    status: parsed.status,
    dueAt: parsed.dueAt,
    tags: parsed.tags,
    meta: { seeded: true, captureNote: parsed.note },
    source: 'import',
  });
  created += 1;
}

console.log(`已写入 ${created} 条演示记录。`);
process.exit(0);
