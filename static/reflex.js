(() => {
  'use strict';
  const STEPS = [
    ['Resolved incident', 'The starting evidence: what failed, where, and when.', 'DataHub OSS'],
    ['Human-confirmed root cause', 'An operator validates the explanation before Reflex learns from it.', 'Reflex'],
    ['Structured lesson', 'The approved explanation becomes a reusable failure pattern.', 'Reflex'],
    ['Preventive control', 'The lesson is compiled into a deterministic executable check.', 'Reflex'],
    ['Similar assets & signals', 'DataHub relationships identify where the same weakness may exist.', 'Reflex'],
    ['Historical backtest', 'The control is tested against normal and incident runs.', 'Reflex-owned execution'],
    ['Publication approval', 'A second human decision is required before coverage is published.', 'Reflex'],
    ['DataHub publication', 'Coverage, provenance and supported metadata are written back.', 'DataHub OSS'],
    ['Future incident detection', 'The proof: an analogous failure is detected on another asset.', 'Reflex'],
  ];
  let selectedScenario = 'duplicate_rows';
  let state = null;
  let busy = false;
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const ownerBadge = (owner) => owner.includes('DataHub') ? '<span class="badge badge-datahub">DATAHUB OSS</span>' : '<span class="badge badge-reflex">REFLEX</span>';
  const statusFor = (step, current, complete, error) => error && step === current ? ['Blocked','is-blocked'] : complete || step < current ? ['Done','is-done'] : step === current ? ['In progress','is-active'] : [current ? 'Next' : 'Waiting',''];
  const stateMessage = (step, current, data) => {
    if (step === 1) return data?.incident_title ? `<strong>${esc(data.incident_title)}</strong><br><code>${esc(data.incident_urn)}</code>` : 'Start an analysis to load incident evidence.';
    if (step === 2) {
      if (!data?.root_cause) return 'Waiting for the incident evidence.';
      const approval = data.root_cause_approval_state || (current >= 3 ? 'approved' : 'pending');
      const action = approval === 'pending' && !data.is_complete ? '<div class="step-actions"><button class="button primary" data-approval="approved" type="button">Approve root cause</button><button class="button quiet" data-approval="rejected" type="button">Reject</button></div>' : '';
      return `<strong>Proposed cause:</strong> ${esc(data.root_cause)}<br><span>${esc(approval.toUpperCase())}</span>${action}`;
    }
    if (step === 3) return data?.lesson_id ? `<strong>${esc(data.lesson_title)}</strong><br>Pattern: <code>${esc(data.failure_pattern)}</code>` : 'This appears after the root cause is approved.';
    if (step === 4) return data?.control_id ? `<strong>${esc(data.control_type)}</strong><br><code>${esc(data.control_id)}</code>` : 'The control is created from the approved lesson.';
    if (step === 5) {
      if (current < 5 || !data?.incident_title) return 'Similar assets are evaluated after the control is defined.';
      return data.similar_assets?.length ? data.similar_assets.map((asset) => `<div><strong>${esc(asset.asset_urn || asset.asset_name)}</strong> <span>score ${esc(asset.score)}</span></div>`).join('') : 'No candidates matched the current signals.';
    }
    if (step === 6) {
      if (current < 6 || !data?.incident_title) return 'Backtest starts after similar assets are selected.';
      return data.backtest_snapshots ? `<div class="metric-line"><strong>${esc(data.backtest_snapshots)}</strong> snapshots · <strong>${esc(Math.round((data.backtest_precision || 0) * 100))}%</strong> precision · <strong>${esc(Math.round((data.backtest_recall || 0) * 100))}%</strong> recall</div>` : 'Backtest results are not available.';
    }
    if (step === 7) {
      if (current < 7 || !data?.backtest_snapshots) return 'Publication approval unlocks after a successful backtest.';
      const approval = data.approval_state || 'pending';
      const action = approval === 'pending' && !data.is_complete ? '<div class="step-actions"><button class="button primary" data-approval="approved" type="button">Approve publication</button><button class="button quiet" data-approval="rejected" type="button">Reject</button></div>' : '';
      return `<strong>${esc(approval.toUpperCase())}</strong>${action}`;
    }
    if (step === 8) return current < 8 || data?.approval_state !== 'approved' ? 'Publication follows explicit approval.' : data.publication_count ? `<strong>${esc(data.publication_count)} assets</strong> published to DataHub.` : 'Metadata and control results remain Reflex-owned because OSS assertion execution is unavailable.';
    if (step === 9) return current < 9 || !data?.is_complete ? 'This proof appears after publication.' : `<strong>${esc(data.detection_assets_checked || 0)} assets</strong> checked for an analogous violation.`;
    return '';
  };
  const renderSummary = (data) => {
    const target = $('#summary');
    if (!data?.incident_title) { target.innerHTML = '<div class="summary-empty"><span class="summary-icon" aria-hidden="true">✦</span><strong>Your run summary will appear here.</strong><p>Start an analysis to inspect evidence, backtest results and approval state.</p></div>'; return; }
    const backtest = data.backtest_snapshots ? `<div class="stat"><span>Backtest</span><strong>${esc(data.backtest_snapshots)} snapshots</strong></div><div class="stat"><span>Recall</span><strong>${esc(Math.round((data.backtest_recall || 0) * 100))}%</strong></div>` : '<div class="stat"><span>Backtest</span><strong>Pending</strong></div>';
    target.innerHTML = `<div class="summary-callout"><span class="summary-icon" aria-hidden="true">✦</span><span><strong>${esc(data.incident_title)}</strong><small>Reflex is compiling reusable protection.</small></span></div><div class="stat"><span>Root cause</span><strong>${data.root_cause_approval_state === 'approved' ? 'Confirmed' : 'Needs review'}</strong></div>${backtest}<div class="stat"><span>Publication</span><strong>${esc(data.approval_state || 'Pending')}</strong></div><div class="stat"><span>Future coverage</span><strong>${data.detection_assets_checked !== undefined ? esc(data.detection_assets_checked + ' assets checked') : 'Not published'}</strong></div>`;
  };
  const render = (data) => {
    state = data || {};
    const current = state.current_step || 0;
    $('#progress-label').textContent = state.is_complete ? 'Complete' : current ? `Step ${current} of 9` : 'Not started';
    $('#connection-status').textContent = state.error ? 'Action required' : state.is_complete ? 'Run complete' : current ? 'Analysis in progress' : 'Ready';
    $('#mode-label').textContent = String(state.mode_label || 'Synthetic mode').toLowerCase().includes('live') ? 'Live DataHub' : 'Synthetic mode';
    $('#workflow').innerHTML = STEPS.map(([title, intro, owner], index) => { const step = index + 1; const [status, cls] = statusFor(step, current, state.is_complete, state.error); return `<article class="step ${cls}"><div class="step-head"><span class="step-number">${step}</span><strong class="step-title">${title} ${ownerBadge(owner)}</strong><span class="step-status">${status}</span></div><span class="step-intro">${intro}</span><div class="step-body">${stateMessage(step, current, state)}</div></article>`; }).join('');
    $('#toast').hidden = !state.error; $('#toast').textContent = state.error ? `Action needed: ${state.error}` : ''; renderSummary(state);
  };
  const request = async (url, options = {}) => { const response = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options}); const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || payload.error || 'Request failed'); return payload; };
  const setBusy = (value) => { busy = value; $('#start-button').disabled = value; $('#reset-button').disabled = value; $('#start-button').innerHTML = value ? '<span aria-hidden="true">◌</span> Starting analysis…' : '<span aria-hidden="true">▶</span> Start analysis'; };
  const refresh = async () => render(await request('/api/state'));
  document.querySelectorAll('[data-scenario]').forEach((button) => button.addEventListener('click', () => { selectedScenario = button.dataset.scenario; document.querySelectorAll('[data-scenario]').forEach((card) => { const active = card.dataset.scenario === selectedScenario; card.classList.toggle('is-selected', active); card.setAttribute('aria-checked', String(active)); }); }));
  $('#start-button').addEventListener('click', async () => { if (busy) return; setBusy(true); try { render({current_step:1, incident_title:'Loading incident evidence…'}); render(await request('/api/run', {method:'POST', body:JSON.stringify({scenario:selectedScenario})})); } catch (error) { render({...state, error:error.message}); } finally { setBusy(false); } });
  $('#reset-button').addEventListener('click', async () => { if (busy) return; try { render(await request('/api/reset', {method:'POST'})); await refresh(); } catch (error) { render({...state, error:error.message}); } });
  $('#workflow').addEventListener('click', async (event) => { const button = event.target.closest('[data-approval]'); if (!button || !state) return; button.disabled = true; try { await request('/api/approve', {method:'POST', body:JSON.stringify({decision:button.dataset.approval, approver:'demo-user', notes:'Decision recorded in Reflex workspace.'})}); await refresh(); } catch (error) { render({...state, error:error.message}); } finally { button.disabled = false; } });
  refresh().catch((error) => render({current_step:0, error:error.message}));
})();
