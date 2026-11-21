'use strict';
const S = {
  tools: [], cats: {}, wordlists: [], sel: null, filter: '',
  runId: null, next: 0, polling: false,
  target: '', hist: [], chefFrame: null, lines: [], dropped: 0, worddir: '', idle: 0,
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
  t.fields.forEach((f, i) => {
    if (!f.tgt) return;
    const inp = $('formWrap').querySelector('[data-idx="' + i + '"]');
    if (!inp || inp.type === 'checkbox') return;
    const auto = inp.dataset.auto === '1';
    if (!auto && inp.value !== '') return;      // 用户手填过就不动
    if (!S.target) { inp.value = ''; inp.dataset.auto = ''; return; }
    const ph = f.ph || '{{TARGET}}';
    if (ph.includes('{{TARGET}}')) inp.value = ph.replaceAll('{{TARGET}}', S.target);
    else {
      try { inp.value = new URL(S.target.includes('//') ? S.target : '//' + S.target).hostname; }
      catch { inp.value = S.target; }
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
function subst(s) {
  if (!S.target) return s;
  return String(s).replaceAll('{{TARGET}}', S.target);
}
function quote(a) { return /[^\w@%+=:,./\u4e00-\u9fa5-]/.test(a) ? "'" + a.replaceAll("'", "'\\''") + "'" : a; }
function preview() {
  const t = S.tools.find(x => x.id === S.sel);
  if (!t || t.view === 'iframe') return;
  const vals = values();
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

/* ───────────── 运行 ───────────── */
async function run() {
  if (S.polling && !confirm('当前任务还在跑：开新任务会丢掉它的实时视图（日志仍会保存）。继续？')) return;
  const t = S.tools.find(x => x.id === S.sel);
  if (!t || t.view === 'iframe') return;
  const body = { tool: S.sel, values: values(), extra: ($('extra') ? $('extra').value : ''), target: S.target, cwd: $('cwd').value.trim() };
  $('out').innerHTML = ''; $('stat').textContent = '';
  S.lines = []; S.dropped = 0; S.idle = 0;
  try {
    const r = await api('/api/run', { method: 'POST', body: JSON.stringify(body) });
    S.runId = r.id; S.next = 0; S.polling = true;
    $('cmdline').textContent = r.cmdline; $('cmdline').dataset.cmd = r.cmdline;
    $('stopBtn').disabled = false; $('runBtn').disabled = true;
    $('running').classList.remove('hidden');
    poll();
  } catch (e) {
    appendLine('✗ ' + e.message, true);
  }
}

async function poll() {
  if (!S.runId) return;
  try {
    const r = await api('/api/poll?id=' + S.runId + '&from=' + S.next);
    S.next = r.next;
    appendLines(r.lines);
    // 长时间没新输出就退避（sqlmap/nuclei 会静默很久），有输出立刻恢复快轮询
    S.idle = r.lines.length ? 0 : (S.idle || 0) + 1;
    $('stat').textContent = `${r.status} · ${r.elapsed}s`;
    if (r.status === 'running') { setTimeout(poll, S.idle > 8 ? 1200 : 280); return; }
    finish(r.status, r.rc, r.elapsed);
  } catch (e) {
    appendLine('✗ 轮询失败: ' + e.message, true);
    finish('error', null, 0);
  }
}

function finish(status, rc, elapsed) {
  S.polling = false; $('runBtn').disabled = false; $('stopBtn').disabled = true;
  $('running').classList.add('hidden');
  $('stat').textContent = `${status}${rc != null ? ' (rc=' + rc + ')' : ''} · ${elapsed}s`;
}

const OUT_KEEP = 4000;   // 页面里最多保留多少行（超出只丢了渲染，不影响磁盘日志）

function appendLines(arr) {
  if (!arr || !arr.length) return;
  for (const l of arr) S.lines.push(l);
  if (S.lines.length > OUT_KEEP) {
    S.dropped += S.lines.length - OUT_KEEP;
    S.lines = S.lines.slice(-OUT_KEEP);
  }
  const pre = $('out');
  pre.textContent = (S.dropped ? `… 前面 ${S.dropped} 行未显示（完整日志见导出文件）…\n` : '') + S.lines.join('\n');
  if ($('follow').checked) $('outwrap').scrollTop = $('outwrap').scrollHeight;
}

function appendLine(text) { appendLines([text]); }

async function stop() {
  if (!S.runId) return;
  try { await api('/api/stop', { method: 'POST', body: JSON.stringify({ id: S.runId }) }); } catch (e) { appendLine('✗ ' + e.message, true); }
}

async function exportLog() {
  if (!S.runId) return appendLine('✗ 先跑一次再导出', true);
  try {
    const r = await api('/api/export', { method: 'POST', body: JSON.stringify({ id: S.runId }) });
    appendLine('✓ 已保存: ' + r.path);
  } catch (e) { appendLine('✗ ' + e.message, true); }
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
    row.onclick = async () => {
      try {
        const r = await api('/api/replay?id=' + h.id);
        $('out').innerHTML = '';
        appendLines(r.lines);
        $('cmdline').textContent = h.cmdline || ''; $('cmdline').dataset.cmd = h.cmdline || '';
        $('history').classList.add('hidden');
      } catch (e) { appendLine('✗ ' + e.message, true); }
    };
    list.appendChild(row);
  });
}

init().catch(e => { document.body.innerHTML = '<pre style="padding:20px;color:#f66">加载失败: ' + e.message + '</pre>'; });
