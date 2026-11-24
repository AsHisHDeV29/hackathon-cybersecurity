const $ = id => document.getElementById(id);
const savedTheme = localStorage.getItem('netra-theme');
const preferredTheme = savedTheme || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('netra-theme', theme);
  const toggle = $('theme-toggle');
  if (toggle) {
    toggle.querySelector('.theme-icon').textContent = theme === 'dark' ? '☀' : '☾';
    toggle.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
  }
}
applyTheme(preferredTheme);
$('theme-toggle').addEventListener('click', () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {flagged:'Potential flag', unclear:'Needs human review', no_flags:'No flags detected'};
const reviewReasons = {unsupported_language:'Local language · manual review',language_uncertain:'Language or meaning unclear',model_unavailable:'Llama unavailable · manual review',ambiguous_context:'More context needed',suspected_trade:'Potential illegal trade'};
let authenticated = false, messages = [], filter = 'all', selectedId = null, page = 'submit';
const samples = {routine:'Hi team, the project meeting is at 10 tomorrow. Thanks!', flagged:'Bank accounts and ATM cards available for rent. DM @sample_seller for price.', unclear:'Same stuff as last time. Two packs ready, ping me for details.',hinglish:'Bhai ATM card aur bank khata kiraye pe milega, interested ho toh DM karo @sample_seller',regional:'நாளை காலை சந்திக்கலாம்'};
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.error || 'Request failed'); error.status = response.status; throw error; }
  return result;
}
function badge(verdict) { return `<span class="badge ${escapeHTML(verdict)}">${escapeHTML(labels[verdict] || verdict)}</span>`; }
function chips(items) { return `<div class="chips">${items.map(item => `<span class="chip">${escapeHTML(item)}</span>`).join('')}</div>`; }
function details(analysis) {
  return `<p>${escapeHTML(analysis.reason)}</p>${analysis.language ? `<div class="evidence-label">LANGUAGE & ROUTING</div>${chips([analysis.language, ...(analysis.review_reason ? [reviewReasons[analysis.review_reason] || analysis.review_reason] : [])])}` : ''}${analysis.categories.length ? `<div class="evidence-label">MONITORED CATEGORIES</div>${chips(analysis.categories)}` : ''}${analysis.evidence.length ? `<div class="evidence-label">SIGNALS IN ORIGINAL TEXT</div>${chips(analysis.evidence)}` : ''}<div class="evidence-label">EXTRACTED IDENTIFIERS</div>${analysis.identifiers.length ? chips(analysis.identifiers.map(x => `${x.type}: ${x.value}`)) : '<span class="small muted">No identifiers found.</span>'}`;
}
function syncAuth() { $('login-panel').hidden = authenticated; $('dashboard').hidden = !authenticated; $('logout').hidden = !authenticated; if (!authenticated) $('queue-badge').hidden = true; }
function navigate() {
  page = location.hash === '#authority' ? 'authority' : 'submit';
  $('submit-page').hidden = page !== 'submit'; $('authority-page').hidden = page !== 'authority';
  $('page-name').textContent = page === 'submit' ? 'Message screening' : 'Authority portal';
  document.querySelectorAll('[data-page]').forEach(x => x.classList.toggle('active', x.dataset.page === page));
  if (page === 'authority' && authenticated) loadQueue();
}
document.querySelectorAll('[data-page]').forEach(x => x.addEventListener('click', () => { location.hash = x.dataset.page; }));
window.addEventListener('hashchange', navigate);
$('message').addEventListener('input', () => { $('char-count').textContent = `${$('message').value.length.toLocaleString()} / 5,000`; });
function updateSubmitLabel() { $('analyze-button').innerHTML = $('language-hint').value === 'other' ? 'Send for manual review <span>↗</span>' : 'Screen message <span>↗</span>'; }
$('language-hint').addEventListener('change', updateSubmitLabel);
document.querySelectorAll('[data-sample]').forEach(x => x.addEventListener('click', () => { $('message').value = samples[x.dataset.sample]; $('message').dispatchEvent(new Event('input')); $('source').value = 'Synthetic demo message'; $('language-hint').value = x.dataset.sample === 'hinglish' ? 'hinglish' : 'auto'; updateSubmitLabel(); }));
$('message-form').addEventListener('submit', async event => {
  event.preventDefault(); $('submit-error').textContent = ''; $('analyze-button').disabled = true; $('analyze-button').textContent = 'Screening…';
  $('result').innerHTML = '<div class="empty-result loading"><div class="scan-icon">⌕</div><h3>Looking at the context…</h3><p>Checking signals and routing the assessment.</p></div>';
  try {
    const item = await api('/api/analyze', {text:$('message').value, source:$('source').value, language_hint:$('language-hint').value});
    const a = item.analysis;
    $('result').innerHTML = `<div class="assessment">${badge(a.verdict)}<h3>${a.verdict === 'flagged' ? 'A signal worth reviewing.' : a.verdict === 'unclear' ? 'A human should take a look.' : 'No monitored signals found.'}</h3>${details(a)}<div class="route-box">${a.verdict === 'no_flags' ? '✓ Saved as screened. No authority review was triggered.' : '↗ Sent to the authority portal for human review.'}</div><div class="result-meta">REFERENCE ${escapeHTML(item.id)}<br>${escapeHTML(a.engine)} · ${new Date(item.created_at).toLocaleString()}<br>This assessment does not establish wrongdoing.</div></div>`;
    if (authenticated) await loadQueue();
  } catch (error) { $('submit-error').textContent = error.message; $('result').innerHTML = '<div class="empty-result"><h3>Screening did not complete.</h3><p>Please retry when the server is available.</p></div>'; }
  finally { $('analyze-button').disabled = false; updateSubmitLabel(); }
});
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); $('login-error').textContent = '';
  try { await api('/api/login', {password:$('password').value}); $('password').value = ''; authenticated = true; syncAuth(); await loadQueue(); }
  catch (error) { $('login-error').textContent = error.message; }
});
$('logout').addEventListener('click', async () => { try { await api('/api/logout', {}); authenticated = false; messages = []; $('queue').innerHTML = ''; syncAuth(); } catch (e) { $('dashboard-error').textContent = e.message; } });
function renderQueue() {
  const leads = messages.filter(x => x.analysis.verdict !== 'no_flags');
  $('stat-pending').textContent = leads.filter(x => x.status === 'pending').length;
  $('stat-flagged').textContent = leads.filter(x => x.analysis.verdict === 'flagged').length;
  $('stat-unclear').textContent = leads.filter(x => x.analysis.verdict === 'unclear').length;
  $('stat-reviewed').textContent = leads.filter(x => ['dismissed','escalated'].includes(x.status)).length;
  const pending = leads.filter(x => x.status === 'pending').length;
  $('queue-badge').hidden = !pending; $('queue-badge').textContent = pending;
  const query = $('search').value.toLowerCase();
  const rows = leads.filter(x => (filter === 'all' || (filter === 'language' ? ['unsupported_language','language_uncertain'].includes(x.analysis.review_reason) : filter === 'reviewed' ? ['dismissed','escalated'].includes(x.status) : x.analysis.verdict === filter)) && `${x.text} ${x.source} ${x.id} ${x.analysis.language || ''} ${x.analysis.identifiers.map(i => i.value).join(' ')}`.toLowerCase().includes(query));
  $('result-count').textContent = rows.length;
  $('queue').innerHTML = rows.length ? rows.map(x => `<div class="queue-row"><div class="queue-text"><p>${escapeHTML(x.text)}</p><small>${escapeHTML(x.source)} · ${new Date(x.created_at).toLocaleString()} · ${escapeHTML(x.id)}</small>${x.analysis.review_reason ? `<span class="review-routing">${escapeHTML(reviewReasons[x.analysis.review_reason] || x.analysis.review_reason)}</span>` : ''}</div><div>${badge(x.analysis.verdict)}</div><span class="status-label">${escapeHTML(x.status)}</span><button class="secondary" data-review="${escapeHTML(x.id)}">Review ↗</button></div>`).join('') : '<div class="queue-empty">No messages in this view.<br>Submit a flagged or ambiguous message to create a review lead.</div>';
}
async function loadQueue() {
  try { const result = await api('/api/messages'); messages = result.messages; $('dashboard-error').textContent = ''; renderQueue(); }
  catch (error) { if (error.status === 401) { authenticated = false; messages = []; $('queue').innerHTML = ''; $('review-dialog').close(); syncAuth(); } else $('dashboard-error').textContent = error.message; }
}
$('refresh').addEventListener('click', loadQueue);
$('search').addEventListener('input', renderQueue);
document.querySelectorAll('[data-filter]').forEach(x => x.addEventListener('click', () => { filter = x.dataset.filter; document.querySelectorAll('[data-filter]').forEach(t => t.classList.toggle('active', t === x)); renderQueue(); }));
$('queue').addEventListener('click', event => {
  const button = event.target.closest('[data-review]'); if (!button) return;
  const item = messages.find(x => x.id === button.dataset.review); if (!item) return;
  selectedId = item.id;
  $('review-content').innerHTML = `<h2>Message ${escapeHTML(item.id)}</h2><div class="dialog-meta">${escapeHTML(item.source)}<br>${new Date(item.created_at).toLocaleString()} · ${escapeHTML(item.analysis.engine)}${item.updated_at ? `<br>Last reviewed: ${new Date(item.updated_at).toLocaleString()}` : ''}</div>${badge(item.analysis.verdict)}<div class="evidence-label">ORIGINAL MESSAGE</div><div class="original-text">${escapeHTML(item.text)}</div>${details(item.analysis)}`;
  $('review-status').value = item.status; $('review-note').value = item.note; $('review-error').textContent = ''; $('review-dialog').showModal();
});
$('close-dialog').addEventListener('click', () => $('review-dialog').close());
$('review-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try { await api('/api/review', {id:selectedId, status:$('review-status').value, note:$('review-note').value}); $('review-dialog').close(); await loadQueue(); }
  catch (error) { $('review-error').textContent = error.message; }
  finally { button.disabled = false; }
});
async function start() {
  navigate();
  try { const health = await api('/api/health'); authenticated = health.authenticated; $('connection').textContent = health.model_ready ? 'Llama ready' : health.model_status === 'rules_only' ? 'Rule-based demo' : 'Llama offline · manual review'; $('connection').parentElement.classList.toggle('offline', !health.model_ready); $('engine-label').textContent = `${health.engine} · ${health.model_ready ? 'Ready' : 'Not ready for AI screening'}`; syncAuth(); if (authenticated) await loadQueue(); }
  catch { $('connection').textContent = 'Server unavailable'; $('engine-label').textContent = 'Screening engine unavailable'; }
}
setInterval(() => { if (authenticated && page === 'authority') loadQueue(); }, 15000);
start();
