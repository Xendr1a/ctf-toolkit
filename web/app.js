'use strict';
const S = {
  tools: [], cats: {}, wordlists: [], sel: null, filter: '',
  target: '', hist: [], chefFrame: null, worddir: '',
  runs: new Map(),   // run id -> 任务状态（插入序 = 标签序），每个任务独立轮询
  active: null,      // 当前显示的标签
};
const $ = (id) => document.getElementById(id);
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
const esc = (s) => String(s);

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { 'X-Requested-By': 'toolkit', 'Content-Type': 'application/json' }, ...opts });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
  return j;
}

/* ───────────── 初始化 ───────────── */
async function init() {
  const st = await api('/api/state');
  S.tools = st.tools; S.cats = st.categories; S.wordlists = st.wordlists; S.hist = st.history || [];
  S.worddir = st.wordlists_dir || '';
  $('title').textContent = st.app.title;
  $('cwd').value = st.workdir_default;
  renderNav();
  const first = S.tools.find(t => t.view !== 'iframe') || S.tools[0];
  selectTool(first.id);

  $('search').addEventListener('input', e => { S.filter = e.target.value.trim().toLowerCase(); renderNav(); });
  $('target').addEventListener('input', e => { S.target = e.target.value.trim(); applyTarget(); preview(); });
  $('extra').addEventListener('input', preview);
  $('runBtn').onclick = run;
  $('stopBtn').onclick = stop;
  $('copyBtn').onclick = () => copy($('cmdline').dataset.cmd || '');
  $('cmdline').onclick = () => copy($('cmdline').dataset.cmd || '');
  $('exportBtn').onclick = exportLog;
  $('histBtn').onclick = () => { renderHist(); $('history').classList.toggle('hidden'); };
  $('histClose').onclick = () => $('history').classList.add('hidden');
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run(); }
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); $('search').focus(); }
    if (e.key === 'Escape') $('history').classList.add('hidden');
  });
}

/* ───────────── 侧栏 ───────────── */
function renderNav() {
  const nav = $('nav'); nav.innerHTML = '';
  for (const [cid, label] of Object.entries(S.cats)) {
    const items = S.tools.filter(t => t.category === cid &&
      (!S.filter || (t.name + t.desc + t.id).toLowerCase().includes(S.filter)));
    if (!items.length) continue;
    nav.appendChild(el('div', 'cat', label));
    for (const t of items) {
      const row = el('div', 'tool' + (S.sel === t.id ? ' active' : ''));
      row.appendChild(el('span', 'ic', t.icon));
      row.appendChild(el('span', 'nm', t.name));
      row.dataset.id = t.id;
      row.onclick = () => selectTool(t.id);
      nav.appendChild(row);
    }
  }
}

/* ───────────── 表单 ───────────── */
function selectTool(id) {
  S.sel = id;
  const t = S.tools.find(x => x.id === id);
  renderNav();
  $('tName').textContent = t.name;
  $('tDesc').textContent = t.desc || '';
  const wrap = $('formWrap');
  wrap.innerHTML = '';

  if (t.view === 'iframe') {
    $('runbar').classList.add('hidden'); $('cmdline').classList.add('hidden');
    $('outwrap').classList.add('hidden'); $('extraWrap').classList.add('hidden');
    $('tabs').classList.add('hidden');
    if (!S.chefFrame) { S.chefFrame = el('iframe', 'chef'); }
    S.chefFrame.src = t.url;
    wrap.appendChild(S.chefFrame);
    wrap.style.cssText = '';
    wrap.className = 'chef-mode';
    if (t.notes) wrap.appendChild(el('div', 'notes', t.notes));
    return;
  }
  $('runbar').classList.remove('hidden'); $('cmdline').classList.remove('hidden');
  $('outwrap').classList.remove('hidden'); $('extraWrap').classList.remove('hidden');
  $('tabs').classList.toggle('hidden', S.runs.size === 0);
  $('extra').value = '';
  wrap.className = '';
  wrap.style.cssText = '';

  if (t.fields.length) {
    const grid = el('div', 'grid');
    t.fields.forEach((f, i) => grid.appendChild(fieldEl(t, f, i)));
    wrap.appendChild(grid);
  }
  if (t.presets && t.presets.length) {
    const ps = el('div', 'presets');
    t.presets.forEach(p => {
      const c = el('button', 'chip', p.label);
      c.type = 'button';
      c.onclick = () => applyPreset(t, p);
      ps.appendChild(c);
    });
    wrap.appendChild(ps);
  }
  if (t.notes) wrap.appendChild(el('div', 'notes', t.notes));
  applyTarget();
  preview();
}

function applyPreset(t, p) {
  // 先重置表单到默认值，再按 set（键可用字段序号 / flag / 标签）填
  t.fields.forEach((f, i) => {
    const inp = $('formWrap').querySelector('[data-idx="' + i + '"]');
    if (!inp) return;
    if (inp.type === 'checkbox') inp.checked = !!f.default;
    else inp.value = f.default || '';
    inp.dataset.auto = '';
  });
  Object.entries(p.set || {}).forEach(([k, v]) => {
    let idx = /^\d+$/.test(k) ? parseInt(k, 10) : t.fields.findIndex(f => f.flag === k);
    if (idx < 0) idx = t.fields.findIndex(f => f.label === k);
    if (idx < 0) return;
    const inp = $('formWrap').querySelector('[data-idx="' + idx + '"]');
    if (!inp) return;
    if (inp.type === 'checkbox') inp.checked = ['1', 'true', 'on'].includes(String(v));
    else inp.value = v;
    inp.dataset.auto = '0';
  });
  $('extra').value = p.args || '';
  applyTarget();
  preview();
}

function applyTarget() {
  const t = S.tools.find(x => x.id === S.sel);
  if (!t || t.view === 'iframe') return;
  const tgs = targetsList();
  t.fields.forEach((f, i) => {
    if (!f.tgt) return;
    const inp = $('formWrap').querySelector('[data-idx="' + i + '"]');
    if (!inp || inp.type === 'checkbox') return;
    if (tgs.length !== 1) {                 // 0 个或多个目标：清空，交给后端按目标逐个填
      inp.value = ''; inp.dataset.auto = '';
      return;
    }
    const auto = inp.dataset.auto === '1';
    if (!auto && inp.value !== '') return;  // 用户手填过就不动
    const tg = tgs[0];
    const ph = f.ph || '{{TARGET}}';
    if (ph.includes('{{TARGET}}')) inp.value = ph.replaceAll('{{TARGET}}', tg);
    else {
      try { inp.value = new URL(tg.includes('//') ? tg : '//' + tg).hostname; }
      catch { inp.value = tg; }
    }
    inp.dataset.auto = '1';
  });
}

function fieldEl(tool, f, i) {
  const d = el('div', 'fld' + (f.kind === 'textarea' ? ' wide' : ''));
  const lab = el('label');
  if (f.flag) lab.appendChild(el('span', 'fl', f.flag));
  lab.appendChild(el('span', '', f.label + (f.req ? ' *' : '')));
  d.appendChild(lab);

  let input;
  if (f.kind === 'bool') {
    const box = el('label', 'chk');
    input = el('input'); input.type = 'checkbox'; input.checked = !!f.default;
    input.dataset.idx = i;
    box.appendChild(input);
    box.appendChild(el('span', '', (f.flag ? f.flag + '  ' : '') + f.label));
    d.innerHTML = ''; d.appendChild(box);
    input.addEventListener('change', preview);
    return d;
  }
  if (f.kind === 'textarea') {
    input = el('textarea'); input.rows = f.repeat ? 3 : 2;
  } else if (f.kind === 'select') {
    input = el('select');
    (f.options || []).forEach(o => {
      const op = el('option', '', o === '' ? '—' : o);
      op.value = o; input.appendChild(op);
    });
  } else if (f.kind === 'combo') {
    input = el('input');
    const dl = el('datalist'); dl.id = 'dl_' + tool.id + '_' + i;
    (S.wordlists || []).forEach(w => { const o = el('option'); o.value = w.path; o.label = w.label; dl.appendChild(o); });
    d.appendChild(dl); input.setAttribute('list', dl.id);
  } else {
    input = el('input');
    if (f.kind === 'number') input.type = 'text';
  }
  input.placeholder = f.ph || '';
  input.value = f.default || '';
  input.dataset.idx = i;
  input.addEventListener('input', (e) => { if (e.isTrusted) input.dataset.auto = '0'; preview(); });
  input.addEventListener('change', preview);
  d.appendChild(input);
  if (f.hint) d.appendChild(el('span', 'hint', f.hint));
  return d;
}

function values() {
  const t = S.tools.find(x => x.id === S.sel);
  const out = [];
  for (let i = 0; i < t.fields.length; i++) {
    const e = $('formWrap').querySelector('[data-idx="' + i + '"]');
    if (!e) { out.push(''); continue; }
    if (e.type === 'checkbox') out.push(e.checked ? '1' : '');
    else out.push(e.value);
  }
  return out;
}

/* 与后端 build() 等价的本地预览 */
function targetsList() {
  return [...new Set((S.target || '').split(/[\n,]+/).map(s => s.trim()).filter(Boolean))];
}
function subst(s) {
  const tg = targetsList()[0];          // 多目标时预览只看第一个
  if (!tg) return s;
  return String(s).replaceAll('{{TARGET}}', tg);
}
function quote(a) { return /[^\w@%+=:,./\u4e00-\u9fa5-]/.test(a) ? "'" + a.replaceAll("'", "'\\''") + "'" : a; }
function preview() {
  const t = S.tools.find(x => x.id === S.sel);
  if (!t || t.view === 'iframe') return;
  const vals = values();
  const first = targetsList()[0] || '';
  // tgt 字段在多目标时是空的，本地预览按第一个目标补齐，和后端 tgt_value 一致
  t.fields.forEach((f, i) => {
    if (!f.tgt || !first || (vals[i] || '').trim()) return;
    const ph = f.ph || '{{TARGET}}';
    if (ph.includes('{{TARGET}}')) vals[i] = ph.replaceAll('{{TARGET}}', first);
    else {
      try { vals[i] = new URL(first.includes('//') ? first : '//' + first).hostname; }
      catch { vals[i] = first; }
    }
  });
  const args = [];
  t.fields.forEach((f, i) => {
    const raw = vals[i] ?? '';
    if (f.kind === 'bool') { if (raw === '1' && f.flag) args.push(f.flag); return; }
    const v = subst(raw).replace(/\n$/, '');
    if (!v.trim()) return;
    if (f.repeat) {
      v.split('\n').map(x => x.trim()).filter(Boolean).forEach(x => { f.flag ? args.push(f.flag, x) : args.push(x); });
      return;
    }
    f.flag ? args.push(f.flag, v) : args.push(v);
  });
  const extra = ($('extra') && $('extra').value || '').trim();
  if (extra) args.push(...splitArgs(subst(extra)));

  const wd = S.worddir;
  const fix = (a) => (wd && a.startsWith('wordlists/')) ? wd + '/' + a.slice('wordlists/'.length) : a;
  let cmd;
  if (t.mode === 'shell') cmd = (t.cmd || []).concat([args.map(fix).join(' ')]).map(quote).join(' ');
  else cmd = (t.cmd || []).concat(args.map(fix)).map(quote).join(' ');
  $('cmdline').textContent = cmd;
  $('cmdline').dataset.cmd = cmd;
}
function splitArgs(s) {
  const out = []; const re = /"([^"]*)"|'([^']*)'|(\S+)/g; let m;
  while ((m = re.exec(s))) out.push(m[1] ?? m[2] ?? m[3]);
  return out;
}

/* ───────────── 运行（多任务标签，各自独立轮询/缓冲） ───────────── */
const OUT_KEEP = 4000;   // 每个任务在页面里最多保留多少行（超出只丢渲染，不影响磁盘日志）
const MAX_TABS = 12;     // 标签软上限：超出先关最旧的已结束标签；全在跑就暂超，不强杀
const view = { id: null, rendered: 0, dropped: 0 };   // <pre> 当前渲染的是哪个 run、已渲染几行

const activeRun = () => S.runs.get(S.active) || null;
const isChef = () => { const t = S.tools.find(x => x.id === S.sel); return !!t && t.view === 'iframe'; };

async function run() {
  const t = S.tools.find(x => x.id === S.sel);
  if (!t || t.view === 'iframe') return;
  const tgs = targetsList();
  const targets = tgs.length ? tgs : [''];   // 没填目标也允许空跑一次
  const cwd = $('cwd').value.trim();
  const extra = $('extra') ? $('extra').value : '';
  const vals = values();                       // tgt 字段在多目标时为空，由后端按每个目标填
  $('runBtn').disabled = true;
  let started = 0;
  for (const tg of targets) {
    try {
      const resp = await api('/api/run', { method: 'POST', body: JSON.stringify({ tool: S.sel, values: vals, extra, target: tg, cwd }) });
      const r = { id: resp.id, toolId: t.id, icon: t.icon || '🧰', name: t.name, cmdline: resp.cmdline,
                  lines: [], dropped: 0, next: 0, idle: 0, status: 'running', rc: null, elapsed: 0, replay: false };
      addTab(r);
      poll(r);
      started++;
    } catch (e) {
      $('stat').textContent = '✗ ' + (tg ? tg + '：' : '') + e.message;
    }
  }
  $('runBtn').disabled = false;
  if (started > 1) $('stat').textContent = `已启动 ${started} 个任务`;
}

function addTab(r) {
  S.runs.set(r.id, r);
  if (S.runs.size > MAX_TABS) {
    for (const [id, old] of S.runs) {
      if (old.status !== 'running') { S.runs.delete(id); break; }
    }
  }
  activate(r.id);
}

function activate(id) {
  const r = S.runs.get(id);
  if (!r) return;
  S.active = id;
  $('cmdline').textContent = r.cmdline; $('cmdline').dataset.cmd = r.cmdline;
  renderOut(r);
  syncRunbar(r);
  renderTabs();
}

function renderTabs() {
  const bar = $('tabs');
  bar.innerHTML = '';
  bar.classList.toggle('hidden', S.runs.size === 0 || isChef());
  for (const r of S.runs.values()) {
    const tab = el('div', 'tab' + (r.id === S.active ? ' active' : ''));
    tab.title = r.cmdline;
    tab.appendChild(el('span', 'tdot ' + r.status));
    tab.appendChild(el('span', 'tname', r.icon + ' ' + r.name));
    tab.appendChild(el('span', 'tid', '#' + r.id.slice(0, 4)));
    const x = el('button', 'tx', '×');
    x.title = r.status === 'running' ? '停止并关闭' : '关闭';
    x.onclick = (e) => { e.stopPropagation(); closeTab(r.id); };
    tab.appendChild(x);
    tab.onclick = () => activate(r.id);
    bar.appendChild(tab);
  }
  updatePill();
}

function closeTab(id) {
  const r = S.runs.get(id);
  if (!r) return;
  if (r.status === 'running') {
    api('/api/stop', { method: 'POST', body: JSON.stringify({ id }) }).catch(() => {});
  }
  S.runs.delete(id);   // poll 循环发现标签没了会自行退出
  if (S.active === id) {
    const last = [...S.runs.keys()].pop();
    if (last) activate(last);
    else {
      S.active = null;
      $('out').textContent = ''; $('stat').textContent = ''; $('stopBtn').disabled = true;
      view.id = null; view.rendered = 0; view.dropped = 0;
      preview();
    }
  }
  renderTabs();
}

async function poll(r) {
  if (!S.runs.has(r.id)) return;
  try {
    const p = await api('/api/poll?id=' + r.id + '&from=' + r.next);
    if (!S.runs.has(r.id)) return;
    r.next = p.next;
    pushLines(r, p.lines);
    // 长时间没新输出就退避（sqlmap/nuclei 会静默很久），有输出立刻恢复快轮询
    r.idle = p.lines.length ? 0 : r.idle + 1;
    r.status = p.status; r.rc = p.rc; r.elapsed = p.elapsed;
    if (p.status === 'running') {
      if (r.id === S.active) $('stat').textContent = `${p.status} · ${p.elapsed}s`;
      setTimeout(() => poll(r), r.idle > 8 ? 1200 : 280);
      return;
    }
    finish(r);
  } catch (e) {
    if (!S.runs.has(r.id)) return;
    pushLines(r, ['✗ 轮询失败: ' + e.message]);
    r.status = 'error';
    finish(r);
  }
}

function finish(r) {
  renderTabs();
  if (r.id === S.active) syncRunbar(r);
}

function syncRunbar(r) {
  $('stopBtn').disabled = !(r && r.status === 'running');
  $('stat').textContent = r ? `${r.status}${r.rc != null ? ' (rc=' + r.rc + ')' : ''} · ${r.elapsed}s` : '';
}

function updatePill() {
  const n = [...S.runs.values()].filter(r => r.status === 'running').length;
  $('running').textContent = `● ${n} 运行中`;
  $('running').classList.toggle('hidden', n === 0);
}

function pushLines(r, arr) {
  if (!arr || !arr.length) return;
  const before = r.dropped;
  for (const l of arr) r.lines.push(l);
  if (r.lines.length > OUT_KEEP) {
    r.dropped += r.lines.length - OUT_KEEP;
    r.lines = r.lines.slice(-OUT_KEEP);
  }
  if (r.id !== S.active) return;
  if (r.dropped !== before) renderOut(r);   // 开头被裁剪，整段重画（note 也变了）
  else appendOut(r);
}

function renderOut(r) {
  const pre = $('out');
  const note = r.dropped ? `… 前面 ${r.dropped} 行未显示（完整日志见导出文件）…\n` : '';
  pre.replaceChildren(document.createTextNode(note + r.lines.join('\n')));
  view.id = r.id; view.rendered = r.lines.length; view.dropped = r.dropped;
  if ($('follow').checked) $('outwrap').scrollTop = $('outwrap').scrollHeight;
}

/* 只在尾部追加新行，不重写整段，避免大输出下每 280ms 全量重绘导致卡顿 */
function appendOut(r) {
  if (view.id !== r.id) return renderOut(r);   // 切换过标签等异常情况，退回全量
  const pre = $('out');
  const fresh = r.lines.slice(view.rendered);
  if (!fresh.length) return;
  pre.appendChild(document.createTextNode((view.rendered ? '\n' : '') + fresh.join('\n')));
  view.rendered = r.lines.length;
  if ($('follow').checked) $('outwrap').scrollTop = $('outwrap').scrollHeight;
}

async function stop() {
  const r = activeRun();
  if (!r || r.status !== 'running') return;
  try { await api('/api/stop', { method: 'POST', body: JSON.stringify({ id: r.id }) }); }
  catch (e) { pushLines(r, ['✗ ' + e.message]); }
}

async function exportLog() {
  const r = activeRun();
  if (!r) { $('stat').textContent = '✗ 先跑一次再导出'; return; }
  try {
    const resp = await api('/api/export', { method: 'POST', body: JSON.stringify({ id: r.id }) });
    pushLines(r, ['✓ 已保存: ' + resp.path]);
  } catch (e) { pushLines(r, ['✗ ' + e.message]); }
}

function copy(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    const s = $('stat'); const old = s.textContent; s.textContent = '已复制到剪贴板';
    setTimeout(() => { s.textContent = old; }, 1200);
  });
}

/* ───────────── 历史 ───────────── */
function renderHist() {
  const list = $('histList'); list.innerHTML = '';
  if (!S.hist.length) { list.appendChild(el('div', 'muted', '（还没有历史记录）')); return; }
  [...S.hist].reverse().forEach(h => {
    const row = el('div', 'hrow');
    const ts = new Date(h.started * 1000).toLocaleString();
    row.appendChild(el('div', 't', `${h.title || h.tool_id} · ${h.status}${h.rc != null ? ' (rc=' + h.rc + ')' : ''}`));
    row.appendChild(el('div', 's', ts + '  ' + (h.cmdline || '')));
    row.onclick = () => openReplay(h);
    list.appendChild(row);
  });
}

/* 回放也开成标签：不冲掉正在跑的实时视图；同一 id 已有标签就直接切过去 */
async function openReplay(h) {
  if (S.runs.has(h.id)) { activate(h.id); $('history').classList.add('hidden'); return; }
  try {
    const p = await api('/api/replay?id=' + h.id);
    let lines = p.lines, dropped = 0;
    if (lines.length > OUT_KEEP) { dropped = lines.length - OUT_KEEP; lines = lines.slice(-OUT_KEEP); }
    const t = S.tools.find(x => x.id === h.tool_id) || {};
    addTab({ id: h.id, toolId: h.tool_id, icon: t.icon || '🕘', name: h.title || t.name || h.tool_id,
             cmdline: h.cmdline || '', lines, dropped, next: p.next, idle: 0,
             status: 'done', rc: h.rc ?? null, elapsed: h.elapsed || 0, replay: true });
    $('history').classList.add('hidden');
  } catch (e) { $('stat').textContent = '✗ ' + e.message; }
}

init().catch(e => { document.body.innerHTML = '<pre style="padding:20px;color:#f66">加载失败: ' + e.message + '</pre>'; });
