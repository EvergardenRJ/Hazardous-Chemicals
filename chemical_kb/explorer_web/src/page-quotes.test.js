import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { LANGUAGES, PAGE_KEYS, QUOTES } from './page-quotes-data.js';
import { QUOTE_STORAGE_KEY, candidatesFor, pickQuote } from './page-quotes.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const pages = {
  quiz: ['QuizWorkspace.jsx'],
  ask: ['Panels.jsx'],
  wiki: ['WikiWorkspace.jsx'],
  chemical: ['ChemicalWorkspace.jsx'],
  graph: ['GraphWorkspace.jsx'],
  insights: ['DashboardWorkspace.jsx'],
  analysis: ['DashboardWorkspace.jsx'],
  data: ['DashboardWorkspace.jsx'],
  news: ['NewsWorkspace.jsx'],
  review: ['Panels.jsx'],
};

class MemoryStorage {
  constructor() { this.map = new Map(); }
  getItem(key) { return this.map.has(key) ? this.map.get(key) : null; }
  setItem(key, value) { this.map.set(key, String(value)); }
}

test('the quote catalogue is complete and traceable', () => {
  assert.ok(QUOTES.length >= 100, `expected at least 100 quotes, got ${QUOTES.length}`);
  assert.deepEqual(new Set(PAGE_KEYS), new Set(Object.keys(pages)));

  const ids = new Set();
  const texts = new Set();
  for (const quote of QUOTES) {
    assert.ok(quote.id && !ids.has(quote.id), `duplicate or empty id: ${quote.id}`);
    ids.add(quote.id);
    assert.ok(quote.original && !texts.has(quote.original), `duplicate or empty original: ${quote.id}`);
    texts.add(quote.original);
    assert.ok(quote.author && quote.work, `missing author/work: ${quote.id}`);
    assert.ok(quote.source.startsWith('https://'), `source must be https: ${quote.id}`);
    assert.ok(quote.sourceLabel, `missing source label: ${quote.id}`);
    assert.ok(LANGUAGES[quote.lang], `unknown language: ${quote.id}`);
    assert.ok(quote.pages.length > 0, `no page assignment: ${quote.id}`);
    assert.ok(quote.pages.every(page => PAGE_KEYS.includes(page)), `unknown page: ${quote.id}`);
    assert.ok(new Set(quote.pages).size === quote.pages.length, `duplicate page: ${quote.id}`);
    assert.ok(quote.original.length <= 240, `original too long: ${quote.id}`);
    if (quote.lang !== 'zh') {
      assert.ok(quote.translation.trim().length >= 4, `missing Chinese translation: ${quote.id}`);
      assert.ok(quote.translation.length <= 260, `translation too long: ${quote.id}`);
    }
  }

  assert.deepEqual(new Set(QUOTES.map(quote => quote.lang)), new Set(Object.keys(LANGUAGES)));
  for (const page of PAGE_KEYS) {
    assert.ok(candidatesFor(page).length >= 10, `${page} has only ${candidatesFor(page).length} candidates`);
  }
});

test('a page entry draws one quote and every candidate can be reached', () => {
  for (const page of PAGE_KEYS) {
    const pool = candidatesFor(page);
    for (let index = 0; index < pool.length; index++) {
      const storage = new MemoryStorage();
      const random = () => (index + 0.5) / pool.length;
      const quote = pickQuote(page, { storage, random });
      assert.equal(quote.id, pool[index].id, `${page} could not draw candidate ${index}`);
    }
  }
});

test('consecutive entries change the quote, while storage failures stay safe', () => {
  const storage = new MemoryStorage();
  let previous = '';
  for (const page of PAGE_KEYS) {
    previous = '';
    for (let round = 0; round < 4; round++) {
      const quote = pickQuote(page, { storage, random: () => 0 });
      assert.ok(quote, `${page} returned no quote`);
      if (previous && candidatesFor(page).length > 1) assert.notEqual(quote.id, previous, `${page} repeated the last quote`);
      previous = quote.id;
    }
  }

  const broken = { getItem() { throw new Error('storage disabled'); }, setItem() { throw new Error('storage disabled'); } };
  assert.ok(pickQuote('data', { storage: broken, random: () => 0 }));
  const invalid = { getItem() { return '{not-json'; }, setItem() {} };
  assert.ok(pickQuote('data', { storage: invalid, random: () => 0 }));
  assert.equal(pickQuote('not-a-page', { storage: invalid, random: () => 0 }), null);
  assert.equal(JSON.parse(storage.getItem(QUOTE_STORAGE_KEY)).review.last, previous);
});

test('every functional page renders the quote in its existing header area', () => {
  for (const [page, files] of Object.entries(pages)) {
    for (const file of files) {
      const source = fs.readFileSync(path.join(here, file), 'utf8');
      assert.match(source, /PageQuote/, `${page} header is missing PageQuote in ${file}`);
    }
  }
  assert.match(fs.readFileSync(path.join(here, 'DashboardWorkspace.jsx'), 'utf8'), /PageQuote[\s\S]*PageQuote/, 'insights/analysis and data need separate quote placements');
  assert.match(fs.readFileSync(path.join(here, 'app/AppShell.jsx'), 'utf8'), /PageQuoteProvider/, 'AppShell must provide the per-entry quote');
  assert.match(fs.readFileSync(path.join(here, 'app/AppShell.jsx'), 'utf8'), /<PageQuote\/>/, 'chemical topic start must show the quote');
  assert.ok(!fs.readFileSync(path.join(here, 'app/PortalHome.jsx'), 'utf8').includes('PageQuote'), 'overview must stay without a page quote');

  const oldIntros = [
    ['DashboardWorkspace.jsx', '上传文档、核对真实数据样例'],
    ['DashboardWorkspace.jsx', '资料结构、专题覆盖与可核实的知识关联'],
    ['QuizWorkspace.jsx', '认识危险，读懂资料，把每一道题学明白'],
    ['QuizWorkspace.jsx', '不是新 RAG 动态生成的事实结论'],
    ['NewsWorkspace.jsx', '沿时间浏览报道，逐条核对来源'],
    ['WikiWorkspace.jsx', '查找化学品、设备与安全专题，沿来源继续阅读'],
    ['GraphWorkspace.jsx', '选择实体或关系核对原文'],
    ['GraphWorkspace.jsx', '旧断言尚未标注生效日期'],
    ['app/PortalHome.jsx', '沿已审核的实体和关系探索知识'],
    ['app/PortalHome.jsx', '从已审核关系出发'],
    ['app/AppShell.jsx', '把 Wiki、标准原文、事故资料、问答与审核放在同一主题下'],
  ];
  for (const [file, text] of oldIntros) {
    assert.ok(!fs.readFileSync(path.join(here, file), 'utf8').includes(text), `${file} still contains the old intro: ${text}`);
  }

  const navigation = fs.readFileSync(path.join(here, 'app/WorkspaceNavigation.jsx'), 'utf8');
  assert.ok(navigation.includes('探索知识关联，追溯证据来源。'));
  assert.ok(navigation.includes('查看实体 ID、关系审核记录与来源'));
  const portal = fs.readFileSync(path.join(here, 'app/PortalHome.jsx'), 'utf8');
  assert.ok(portal.includes('浏览实体与关系，查看关联证据和来源'));
  assert.ok(portal.includes('沿实体关系查看原文证据与审核记录'));
  const graph = fs.readFileSync(path.join(here, 'GraphWorkspace.jsx'), 'utf8');
  assert.ok(graph.includes('KNOWLEDGE GRAPH / TRACEABLE EVIDENCE'));
  assert.ok(graph.includes('已通过审核的实体关系'));
  assert.ok(graph.includes('当前关系尚未标注生效日期'));
  assert.ok(fs.readFileSync(path.join(here, 'ChemicalWorkspace.jsx'), 'utf8').includes('当前有效的关系记录'));
  assert.ok(fs.readFileSync(path.join(here, 'app/KnowledgeSearch.jsx'), 'utf8').includes("group:'图谱与实体'"));
});

test('the quote is one complete line and the source entry does not repeat the original', () => {
  const component = fs.readFileSync(path.join(here, 'components/PageQuote.jsx'), 'utf8');
  assert.match(component, /<details/);
  assert.match(component, /<summary>原文与出处<\/summary>/);
  assert.match(component, /quote\.text|quote\.original/);
  assert.match(component, /quote\.translation/);
  assert.match(component, /quote\.author/);
  assert.match(component, /quote\.work/);
  assert.match(component, /quote\.source/);
  assert.match(component, /quote\.sourceLabel/);
  assert.match(component, /lang=\{foreign \? quote\.lang : 'zh-Hant'\}/);
  assert.match(component, /lang="zh-CN"/);
  const details = component.slice(component.indexOf('<details'), component.indexOf('</details>') + '</details>'.length);
  assert.ok(!details.includes('quote.original'), 'details must not repeat the original');
  assert.ok(!details.includes('quote.translation'), 'details must not repeat the translation');
  const css = fs.readFileSync(path.join(here, 'components/page-quotes.css'), 'utf8');
  assert.match(css, /max-width:\s*820px/);
  assert.match(css, /white-space:\s*pre-line/);
  assert.match(css, /@media\s*\(max-width:\s*700px\)/);
  assert.match(css, /overflow-wrap:\s*anywhere/);
  assert.ok(!css.includes('-webkit-line-clamp'), 'the quote must not be truncated');
});

test('the provider only redraws on a top-level page change', () => {
  const component = fs.readFileSync(path.join(here, 'components/PageQuote.jsx'), 'utf8');
  assert.ok(component.includes('lastPage.current === page'));
  assert.ok(component.includes('}, [page]);'));
});
