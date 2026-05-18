(function(){
  var pageDataEl=document.getElementById("page-data-siteconfig__school_automation_builder-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["siteconfig__school_automation_builder-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  const inner = document.getElementById('workflow-canvas-inner');
  const svg = document.getElementById('workflow-edge-svg');
  const wrap = document.getElementById('workflow-canvas-wrap');
  const wfJson = document.getElementById('wf-json');
  const graphState = { nodes: [], edges: [] };
  let nodeSeq = 0;
  let lastCanvasNodeId = null;
  let connectMode = false;
  let connectFromId = null;

  function tok(name, fallback) {
    try {
      const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    } catch (_e) { return fallback; }
  }

  function syncJsonFromGraph() {
    const trig = document.getElementById('wf-trigger')?.value;
    let conditions = [];
    let actions = [];
    try {
      const parsed = JSON.parse(wfJson.value || '{}');
      if (Array.isArray(parsed.conditions)) conditions = parsed.conditions;
      if (Array.isArray(parsed.actions)) actions = parsed.actions;
    } catch (e) {}
    graphState.nodes.forEach(function(n) {
      if (n.kind === 'condition') {
        conditions.push({ field: 'score', op: 'gte', value: 0 });
      }
      if (n.kind === 'action') {
        actions.push({ type: n.actionType || 'notify', params: { channel: 'log', body: 'Automation' } });
      }
    });
    wfJson.value = JSON.stringify({
      conditions: conditions,
      actions: actions,
      graph: graphState
    }, null, 2);
    document.getElementById('wf-output').textContent = 'trigger: ' + trig + ', nodes: ' + graphState.nodes.length + ', edges: ' + graphState.edges.length;
  }

  function nodeCenterEl(el) {
    const r = el.getBoundingClientRect();
    const br = inner.getBoundingClientRect();
    return {
      x: r.left - br.left + r.width / 2,
      y: r.top - br.top + r.height / 2
    };
  }

  function ensureArrowDefs() {
    if (svg.querySelector('defs')) return;
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.setAttribute('id', 'arrowhead');
    marker.setAttribute('markerWidth', '6');
    marker.setAttribute('markerHeight', '6');
    marker.setAttribute('refX', '5');
    marker.setAttribute('refY', '3');
    marker.setAttribute('orient', 'auto');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M0,0 L0,6 L6,3 z');
    path.setAttribute('fill', tok('--color-base-500', '#6c757d'));
    marker.appendChild(path);
    defs.appendChild(marker);
    svg.appendChild(defs);
  }

  function drawEdges() {
    svg.querySelectorAll('line').forEach(function(l) { l.remove(); });
    ensureArrowDefs();
    const br = inner.getBoundingClientRect();
    svg.setAttribute('width', Math.max(br.width, 10));
    svg.setAttribute('height', Math.max(br.height, 10));
    graphState.edges.forEach(function(e) {
      const fromEl = inner.querySelector('[data-node-id="' + e.from + '"]');
      const toEl = inner.querySelector('[data-node-id="' + e.to + '"]');
      if (!fromEl || !toEl) return;
      const a = nodeCenterEl(fromEl);
      const b = nodeCenterEl(toEl);
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', a.x);
      line.setAttribute('y1', a.y);
      line.setAttribute('x2', b.x);
      line.setAttribute('y2', b.y);
      line.setAttribute('stroke', tok('--color-base-500', '#6c757d'));
      line.setAttribute('stroke-width', '2');
      line.setAttribute('marker-end', 'url(#arrowhead)');
      svg.appendChild(line);
    });
  }

  inner.addEventListener('dragover', function(e) { e.preventDefault(); });
  inner.addEventListener('drop', function(e) {
    e.preventDefault();
    const kind = e.dataTransfer.getData('kind');
    const nodeType = e.dataTransfer.getData('node-type');
    if (!kind) return;
    const placeholder = inner.querySelector('.canvas-placeholder');
    if (placeholder) placeholder.remove();
    nodeSeq += 1;
    const id = 'n' + nodeSeq;
    const rect = inner.getBoundingClientRect();
    let left = e.clientX - rect.left - 60;
    let top = e.clientY - rect.top - 18;
    left = Math.max(8, Math.min(left, rect.width - 130));
    top = Math.max(8, Math.min(top, rect.height - 40));

    const el = document.createElement('div');
    el.className = 'workflow-node-card';
    el.style.left = left + 'px';
    el.style.top = top + 'px';
    el.dataset.nodeId = id;
    el.dataset.kind = kind;
    el.textContent = (kind === 'trigger' ? 'Tr: ' : kind === 'condition' ? 'If: ' : 'Do: ') + (nodeType || '');
    inner.appendChild(el);
    graphState.nodes.push({ id: id, kind: kind, actionType: nodeType, x: left, y: top });

    if (document.getElementById('auto-chain')?.checked && lastCanvasNodeId) {
      graphState.edges.push({ from: lastCanvasNodeId, to: id });
    }
    lastCanvasNodeId = id;

    el.addEventListener('click', function(ev) {
      ev.stopPropagation();
      if (!connectMode) return;
      if (!connectFromId) {
        connectFromId = id;
        el.classList.add('selected');
      } else if (connectFromId !== id) {
        graphState.edges.push({ from: connectFromId, to: id });
        inner.querySelectorAll('.workflow-node-card.selected').forEach(function(x) { x.classList.remove('selected'); });
        connectFromId = null;
        syncJsonFromGraph();
        drawEdges();
      }
    });

    syncJsonFromGraph();
    drawEdges();
  });

  inner.addEventListener('click', function() {
    if (connectMode && connectFromId) {
      inner.querySelectorAll('.workflow-node-card.selected').forEach(function(x) { x.classList.remove('selected'); });
      connectFromId = null;
    }
  });

  document.querySelectorAll('.palette-node').forEach(function(p) {
    p.addEventListener('dragstart', function(e) {
      e.dataTransfer.setData('kind', p.getAttribute('data-kind'));
      e.dataTransfer.setData('node-type', p.getAttribute('data-node-type') || '');
    });
  });

  document.getElementById('btn-connect-mode')?.addEventListener('click', function() {
    connectMode = !connectMode;
    this.textContent = connectMode ? ((window.__RMC_PAGE_DATA__["siteconfig__school_automation_builder-1"] || {})["trans_connect_mode_on"]) : ((window.__RMC_PAGE_DATA__["siteconfig__school_automation_builder-1"] || {})["trans_connect_mode_off"]);
    connectFromId = null;
    inner.querySelectorAll('.workflow-node-card.selected').forEach(function(x) { x.classList.remove('selected'); });
  });

  document.getElementById('btn-redraw-edges')?.addEventListener('click', drawEdges);
  window.addEventListener('resize', drawEdges);

  document.getElementById('wf-trigger')?.addEventListener('change', syncJsonFromGraph);

  function csrf() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  async function postJson(url, body) {
    const r = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf()
      },
      credentials: 'same-origin',
      body: JSON.stringify(body)
    });
    return r.json();
  }

  let lastSavedWorkflowId = null;
  document.getElementById('btn-save')?.addEventListener('click', async function() {
    let extra = {};
    try { extra = JSON.parse(wfJson.value || '{}'); } catch (e) { alert('Invalid JSON'); return; }
    const name = document.getElementById('wf-name')?.value || 'Untitled';
    const trigger = document.getElementById('wf-trigger')?.value;
    const body = Object.assign({
      name: name,
      trigger: trigger,
      status: 'draft',
      conditions: extra.conditions || [],
      actions: extra.actions || [],
      graph: extra.graph || graphState
    }, lastSavedWorkflowId ? { id: lastSavedWorkflowId } : {});
    const out = await postJson(((window.__RMC_PAGE_DATA__["siteconfig__school_automation_builder-1"] || {})["url_siteconfig_school_automation_save_api"]), body);
    if (out.id) { lastSavedWorkflowId = out.id; }
    document.getElementById('wf-output').textContent = JSON.stringify(out, null, 2);
  });

  document.getElementById('btn-publish')?.addEventListener('click', async function() {
    if (!lastSavedWorkflowId) { alert('Save draft first'); return; }
    const out = await postJson(((window.__RMC_PAGE_DATA__["siteconfig__school_automation_builder-1"] || {})["url_siteconfig_school_automation_publish_api"]), { id: lastSavedWorkflowId });
    document.getElementById('wf-output').textContent = JSON.stringify(out, null, 2);
  });

  document.getElementById('btn-simulate')?.addEventListener('click', async function() {
    let dsl = {};
    try {
      const extra = JSON.parse(wfJson.value || '{}');
      dsl = {
        trigger: document.getElementById('wf-trigger')?.value,
        conditions: extra.conditions || [],
        actions: extra.actions || []
      };
    } catch (e) { alert('Invalid JSON'); return; }
    const out = await postJson(((window.__RMC_PAGE_DATA__["siteconfig__school_automation_builder-1"] || {})["url_siteconfig_school_automation_simulate_api"]), {
      dsl: dsl,
      context: { score: 10, student_id: 1 }
    });
    document.getElementById('wf-output').textContent = JSON.stringify(out, null, 2);
  });

  document.getElementById('btn-load-logs')?.addEventListener('click', async function() {
    let url = ((window.__RMC_PAGE_DATA__["siteconfig__school_automation_builder-1"] || {})["url_siteconfig_school_automation_execution_logs_api"]);
    if (lastSavedWorkflowId) url += '?workflow_id=' + lastSavedWorkflowId;
    const r = await fetch(url, { credentials: 'same-origin' });
    const data = await r.json();
    const sel = document.getElementById('exec-log-pick');
    sel.innerHTML = '';
    (data.logs || []).forEach(function(lg) {
      const opt = document.createElement('option');
      opt.value = lg.id;
      opt.textContent = '#' + lg.id + ' ' + lg.run_status + (lg.has_action_errors ? ' ERR' : '');
      sel.appendChild(opt);
    });
    document.getElementById('wf-output').textContent = JSON.stringify(data, null, 2);
  });

  document.getElementById('btn-retry-log')?.addEventListener('click', async function() {
    const sel = document.getElementById('exec-log-pick');
    const logId = sel.value;
    if (!logId) { alert('Load logs and pick an entry'); return; }
    const out = await postJson(((window.__RMC_PAGE_DATA__["siteconfig__school_automation_builder-1"] || {})["url_siteconfig_school_automation_retry_api"]), {
      execution_log_id: parseInt(logId, 10),
      context: {}
    });
    document.getElementById('wf-output').textContent = JSON.stringify(out, null, 2);
  });

  wfJson.value = JSON.stringify({ conditions: [], actions: [], graph: { nodes: [], edges: [] } }, null, 2);
})();
})();
