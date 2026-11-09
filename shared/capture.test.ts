import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseCapture, parseDueDate } from './capture.ts';

const NOW = new Date('2026-11-09T15:30:00+08:00'); // 周一

test('带单位的金额 → 记账，并识别分类', () => {
  const r = parseCapture('午饭 32 元和同事', NOW);
  assert.equal(r.kind, 'expense');
  assert.equal(r.amount, 32);
  assert.equal(r.category, '餐饮');
  assert.ok(r.confidence > 0.9);
});

test('货币符号也能识别', () => {
  const r = parseCapture('打车 ¥48.5', NOW);
  assert.equal(r.kind, 'expense');
  assert.equal(r.amount, 48.5);
  assert.equal(r.category, '交通');
});

test('万 的口语写法', () => {
  const r = parseCapture('交房租 1.2万', NOW);
  assert.equal(r.kind, 'expense');
  assert.equal(r.amount, 12000);
  assert.equal(r.category, '住房');
});

test('只有数字和分类词也算记账', () => {
  const r = parseCapture('咖啡 25', NOW);
  assert.equal(r.kind, 'expense');
  assert.equal(r.amount, 25);
});

test('显式前缀拥有最高优先级', () => {
  const r = parseCapture('闪念：今天想到一个点子，关于记账 20 元的事', NOW);
  assert.equal(r.kind, 'thought');
  assert.equal(r.amount, null);
});

test('记得/别忘 这类语气 → 待办，并解析明天', () => {
  const r = parseCapture('记得明天交房租', NOW);
  assert.equal(r.kind, 'todo');
  assert.equal(r.status, 'open');
  assert.ok(r.dueAt, '应该解析出截止时间');
  assert.equal(new Date(r.dueAt as string).getDate(), 10);
});

test('日常感悟 → 闪念或日记，不会误判成记账', () => {
  const r = parseCapture('今天天气很好，突然觉得该慢一点', NOW);
  assert.notEqual(r.kind, 'expense');
  assert.equal(r.amount, null);
});

test('长文本判为日记', () => {
  const r = parseCapture(
    '今天下午开了三个会，脑子有点糊。回来的路上一直在想那个架构问题，后来在地铁上突然想通了：其实不需要同步层，服务端就是唯一真相。',
    NOW,
  );
  assert.equal(r.kind, 'journal');
});

test('#标签 会被抽出来并从正文里去掉', () => {
  const r = parseCapture('想到一个装修的点子 #装修 #灵感', NOW);
  assert.deepEqual(r.tags, ['装修', '灵感']);
  assert.equal(r.content.includes('#'), false);
});

test('日期写法：11月20日', () => {
  const due = parseDueDate('11月20日交房租', NOW);
  assert.ok(due);
  assert.equal(new Date(due.dueAt).getMonth(), 10);
  assert.equal(new Date(due.dueAt).getDate(), 20);
});

test('日期写法：周三 / 下周三', () => {
  const thisWeek = parseDueDate('周三开会', NOW);
  assert.ok(thisWeek);
  assert.equal(new Date(thisWeek.dueAt).getDay(), 3);

  const nextWeek = parseDueDate('下周三开会', NOW);
  assert.ok(nextWeek);
  assert.equal(new Date(nextWeek.dueAt).getDay(), 3);
  assert.ok(new Date(nextWeek.dueAt).getTime() > new Date(thisWeek.dueAt).getTime());
});

test('「3点」不会被当成金额', () => {
  const r = parseCapture('今天 3点 开会', NOW);
  assert.notEqual(r.kind, 'expense');
  assert.equal(r.amount, null);
});

test('空内容或纯数字的兜底', () => {
  const r = parseCapture('32', NOW);
  assert.equal(r.kind, 'expense');
  assert.equal(r.amount, 32);
});
