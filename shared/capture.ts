/**
 * 快速捕捉解析器：「一句话 → 结构化记录」。
 *
 * 这里刻意先用规则实现，而不是直接调大模型，原因有三：
 *  1. 零延迟：敲完立刻看到「识别为 记账 ¥32 · 餐饮」，不用等网络；
 *  2. 零成本、可离线：一天几十条记录不会产生 token 账单；
 *  3. 可测试、可解释：规则命中不了的时候，你知道为什么，也好加规则。
 *
 * 大模型该做的是「规则兜不住的模糊语义」，那是 v0.3 的事（见 ai.ts 的 enrich 注释）。
 */
import type { Category, Kind } from './schema.ts';
import { nowISO } from './date.ts';

export interface CaptureResult {
  kind: Kind;
  content: string;
  tags: string[];
  amount: number | null;
  category: string | null;
  dueAt: string | null;
  status: 'open' | null;
  /** 0~1，低于 0.6 时前端会提示「识别可能不准，可手动改」 */
  confidence: number;
  /** 给用户看的一句话理由，做成识别结果旁边的小字 */
  note: string;
}

const PREFIXES: Array<{ re: RegExp; kind: Kind }> = [
  { re: /^(?:todo|todos|task|待办|任务|要做)\s*[:：]\s*/i, kind: 'todo' },
  { re: /^(?:支出|记账|花费|消费|花了)\s*[:：]\s*/, kind: 'expense' },
  { re: /^(?:日记|日志)\s*[:：]\s*/, kind: 'journal' },
  { re: /^(?:闪念|想法|念头|灵感)\s*[:：]\s*/, kind: 'thought' },
];

/** 越靠前的类别优先级越高：'买咖啡' 应该归餐饮而不是购物 */
const CATEGORY_KEYWORDS: Array<[Category, string[]]> = [
  ['餐饮', ['吃', '饭', '早餐', '早餐', '午餐', '午餐', '晚餐', '午饭', '晚饭', '夜宵', '宵夜', '咖啡', '奶茶', '外卖', '火锅', '烧烤', '面条', '米粉', '包子', '零食', '水果', '食堂', '饮料', '可乐', '啤酒', '聚餐', '下馆子']],
  ['交通', ['打车', '地铁', '公交', '高铁', '火车票', '机票', '加油', '停车', '滴滴', '单车', '油费', '过路费', '车票', '网约车', '高速']],
  ['住房', ['房租', '水电', '电费', '水费', '物业', '宽带', '燃气', '暖气', '装修']],
  ['医疗', ['医院', '看病', '药', '挂号', '体检', '牙', '诊所', '疫苗', '医保']],
  ['学习', ['书', '课程', '学费', '培训', '考试', '网课', '教材', '证书', '报班']],
  ['娱乐', ['电影', '游戏', '演出', '演唱会', 'ktv', '会员', '订阅', '剧本杀', '桌游', '旅游', '门票', '展览', '音乐会']],
  ['购物', ['买', '衣服', '裤子', '鞋', '外套', 't恤', '快递', '淘宝', '京东', '拼多多', '超市', '日用品', '洗发水', '纸巾', '家居', '耳机', '数码']],
];

const EXPENSE_VERBS = /(花了|付了|支付|消费|买了|充值|缴费|交了|打车|加油|吃了|喝了|点了|下单)/;
const TODO_WEAK = /(记得|别忘了|别忘|要记得|待办|截止|ddl|DDL|提醒我)/;

const WEEKDAY_MAP: Record<string, number> = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 日: 0, 天: 0 };

interface AmountHit {
  amount: number;
  /** 命中的写法，用于生成可读提示 */
  raw: string;
  /** 是否带货币符号/单位（带单位基本可以确定是钱） */
  explicit: boolean;
}

function toNumber(raw: string): number {
  return Number(raw.replace(/,/g, ''));
}

function findAmount(text: string): AmountHit | null {
  // 1.2万 / 1万5 这类口语写法
  const wan = text.match(/(\d+(?:\.\d{1,2})?)\s*万(?:元|块)?/);
  if (wan?.[1]) {
    return { amount: Math.round(toNumber(wan[1]) * 10000 * 100) / 100, raw: wan[0], explicit: true };
  }
  const symbols = text.match(/[¥￥$]\s*(\d[\d,]*(?:\.\d{1,2})?)/);
  if (symbols?.[1]) {
    return { amount: toNumber(symbols[1]), raw: symbols[0], explicit: true };
  }
  const units = text.match(/(\d[\d,]*(?:\.\d{1,2})?)\s*(?:元|块钱|块|人民币|rmb)/i);
  if (units?.[1]) {
    return { amount: toNumber(units[1]), raw: units[0], explicit: true };
  }
  const verbs = text.match(/(?:花了|付了|支付了?|消费了?|支出|充值了?)\s*(\d+(?:\.\d{1,2})?)/);
  if (verbs?.[1]) {
    return { amount: toNumber(verbs[1]), raw: verbs[0], explicit: true };
  }
  return null;
}

/** 兜底：句子里裸出现的数字。排除时间、数量、日期这些明显不是钱的。 */
function findLooseNumber(text: string): AmountHit | null {
  const re = /(\d+(?:\.\d{1,2})?)\s*(点|分|月|日|号|年|岁|个|次|公里|km|kg|斤|天|人|杯|层|楼|点(?:半)?)/g;
  const blocked = new Set<number>();
  for (const m of text.matchAll(re)) {
    if (m.index !== undefined) blocked.add(m.index);
  }
  const all = /(\d+(?:\.\d{1,2})?)/g;
  for (const m of text.matchAll(all)) {
    const idx = m.index ?? 0;
    if (blocked.has(idx)) continue;
    // 排除日期写法 11-09 / 2026.11
    const around = text.slice(Math.max(0, idx - 1), idx + m[0].length + 1);
    if (/[-/.]\s*\d/.test(around)) continue;
    if (m[1]) return { amount: toNumber(m[1]), raw: m[1], explicit: false };
  }
  return null;
}

function detectCategory(text: string): Category | null {
  const lower = text.toLowerCase();
  for (const [category, words] of CATEGORY_KEYWORDS) {
    if (words.some((w) => lower.includes(w.toLowerCase()))) return category;
  }
  return null;
}

function detectPrefix(text: string): { kind: Kind; rest: string } | null {
  for (const p of PREFIXES) {
    const m = text.match(p.re);
    if (m) return { kind: p.kind, rest: text.slice(m[0].length).trim() };
  }
  return null;
}

function extractTags(text: string): { tags: string[]; text: string } {
  const tags: string[] = [];
  const cleaned = text
    .replace(/(^|[\s，,。、])#([\p{L}\p{N}_-]{1,20})/gu, (_m, head: string, tag: string) => {
      tags.push(tag);
      return head;
    })
    .replace(/[ \t]{2,}/g, ' ')
    .trim();
  return { tags: [...new Set(tags)], text: cleaned };
}

/** 解析「明天 / 周三 / 11月20日 / 今晚」这类相对时间，返回本地时区的 ISO */
export function parseDueDate(text: string, now: Date = new Date()): { dueAt: string; matched: string } | null {
  const base = new Date(now);
  base.setHours(9, 0, 0, 0);

  const applyHour = (d: Date): Date => {
    const out = new Date(d);
    if (/(晚|夜|下午)/.test(text)) out.setHours(20, 0, 0, 0);
    else if (/中午/.test(text)) out.setHours(12, 0, 0, 0);
    else if (/(早|上午)/.test(text)) out.setHours(9, 0, 0, 0);
    else out.setHours(9, 0, 0, 0);
    return out;
  };

  const relative: Array<[RegExp, number]> = [
    [/大后天/, 3],
    [/后天/, 2],
    [/明天|明日|明早|明晚/, 1],
    [/今天|今日|今晚/, 0],
  ];
  for (const [re, delta] of relative) {
    const m = text.match(re);
    if (m) {
      const d = new Date(base);
      d.setDate(d.getDate() + delta);
      return { dueAt: applyHour(d).toISOString(), matched: m[0] };
    }
  }

  const week = text.match(/(下)?\s*(?:周|星期)([一二三四五六日天])/);
  if (week?.[2]) {
    const target = WEEKDAY_MAP[week[2]];
    if (target !== undefined) {
      const current = now.getDay();
      let delta = (target - current + 7) % 7;
      if (week[1]) delta += 7;
      const d = new Date(base);
      d.setDate(d.getDate() + delta);
      return { dueAt: applyHour(d).toISOString(), matched: week[0] };
    }
  }

  const md = text.match(/(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]/);
  if (md?.[1] && md[2]) {
    const month = Number(md[1]) - 1;
    const day = Number(md[2]);
    const d = new Date(now.getFullYear(), month, day, 9, 0, 0, 0);
    if (d.getTime() < new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()) {
      d.setFullYear(d.getFullYear() + 1);
    }
    return { dueAt: applyHour(d).toISOString(), matched: md[0] };
  }

  return null;
}

const KEEP_AS_JOURNAL = /(今天|昨天|最近|这周|感觉|觉得|因为|所以|后来|然后|其实|好像|突然|想起)/;

/**
 * 把一句话解析成一条结构化记录。
 * 纯函数，同样的输入永远得到同样的输出（时间基准 now 显式传入，方便测试）。
 */
export function parseCapture(raw: string, now: Date = new Date()): CaptureResult {
  let text = raw.trim();
  const prefix = detectPrefix(text);
  if (prefix) text = prefix.rest;

  const tagged = extractTags(text);
  text = tagged.text;
  const tags = tagged.tags;

  const amountHit = findAmount(text);
  const category = detectCategory(text);
  const expenseVerb = EXPENSE_VERBS.test(text);
  const bareNumber = amountHit ? null : findLooseNumber(text);

  // ── 判定类型 ───────────────────────────────────────
  let kind: Kind;
  let confidence = 0.6;
  const signals: string[] = [];

  /** 整句就是一个数字（「32」「¥45」）：最常见的极简记账写法 */
  const isBareAmount = /^[¥￥$]?\s*\d+(?:\.\d{1,2})?\s*(?:元|块|块钱)?$/.test(text);

  const looksLikeExpense = Boolean(
    amountHit || isBareAmount || (bareNumber && (expenseVerb || category) && text.length <= 30),
  );

  if (prefix) {
    kind = prefix.kind;
    confidence = 0.98;
    signals.push('显式标了类型');
  } else if (looksLikeExpense && (amountHit?.explicit || expenseVerb || category || isBareAmount)) {
    kind = 'expense';
    confidence = amountHit?.explicit ? 0.94 : isBareAmount ? 0.75 : 0.82;
    if (amountHit?.explicit) signals.push('带金额单位');
    if (expenseVerb) signals.push('支出动词');
    if (category) signals.push(`关键词「${category}」`);
  } else if (TODO_WEAK.test(text) || /^(要|得|该|必须)\s*\S/.test(text)) {
    kind = 'todo';
    confidence = TODO_WEAK.test(text) ? 0.8 : 0.66;
    signals.push('祈使/提醒语气');
  } else if (text.length >= 40 || KEEP_AS_JOURNAL.test(text)) {
    kind = 'journal';
    confidence = 0.68;
    signals.push(text.length >= 40 ? '篇幅较长' : '叙事语气');
  } else {
    kind = 'thought';
    confidence = 0.6;
    signals.push('短句');
  }

  // ── 字段落位 ───────────────────────────────────────
  const amount = kind === 'expense' ? (amountHit?.amount ?? bareNumber?.amount ?? null) : null;
  const finalCategory = kind === 'expense' ? (category ?? '其他') : null;

  let dueAt: string | null = null;
  let dueText = '';
  if (kind === 'todo') {
    const due = parseDueDate(text, now);
    if (due) {
      dueAt = due.dueAt;
      dueText = due.matched;
      confidence = Math.min(0.95, confidence + 0.1);
      signals.push(`时间「${due.matched}」`);
    }
  }

  const note =
    kind === 'expense'
      ? `记录为支出${amount !== null ? ` ¥${amount}` : '（未识别到金额）'}${finalCategory ? ` · ${finalCategory}` : ''}`
      : kind === 'todo'
        ? `记为待办${dueText ? `，截止「${dueText}」` : '，未识别截止时间'}`
        : kind === 'journal'
          ? '记为日记'
          : '记为闪念';

  return {
    kind,
    content: text || raw.trim(),
    tags,
    amount,
    category: finalCategory,
    dueAt,
    status: kind === 'todo' ? 'open' : null,
    confidence: Math.max(0.4, Math.min(0.99, confidence)),
    note,
  };
}

/** 给识别结果做一行摘要，直接显示在输入框下方 */
export function captureSummary(result: CaptureResult): string {
  const kindLabel = { journal: '日记', thought: '闪念', expense: '记账', todo: '待办', habit: '习惯', metric: '指标' }[
    result.kind
  ];
  const parts = [kindLabel];
  if (result.amount !== null) parts.push(`¥${result.amount}`);
  if (result.category && result.kind === 'expense') parts.push(result.category);
  if (result.dueAt) parts.push('有截止时间');
  if (result.tags.length) parts.push(result.tags.map((t) => `#${t}`).join(' '));
  return parts.join(' · ');
}
