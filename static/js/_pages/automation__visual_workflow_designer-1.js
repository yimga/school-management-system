(function(){
  var pageDataEl=document.getElementById("page-data-automation__visual_workflow_designer-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function(){
  var inner = document.getElementById("wf-inner");
  var svg = document.getElementById("wf-edge-layer");
  var nodes = [];
  var edges = [];
  var connectFrom = null;
  var csrftoken = document.cookie.match(/csrftoken=([^;]+)/);
  csrftoken = csrftoken ? csrftoken[1] : "";

  function tok(name, fallback){
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    } catch (_e) { return fallback; }
  }

  function uid(){ return "n-" + Math.random().toString(36).slice(2,10); }

  function nodeCenter(n){
    var x = (n.position && typeof n.position.x === "number") ? n.position.x : 20;
    var y = (n.position && typeof n.position.y === "number") ? n.position.y : 20;
    return { x: x + 48, y: y + 16 };
  }

  function redrawEdges(){
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var w = inner.parentElement.clientWidth || 800;
    var h = inner.clientHeight || 480;
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    var byId = {};
    nodes.forEach(function(n){ byId[n.id] = n; });
    edges.forEach(function(e){
      var a = byId[e.from], b = byId[e.to];
      if(!a || !b) return;
      var p1 = nodeCenter(a), p2 = nodeCenter(b);
      var line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", p1.x); line.setAttribute("y1", p1.y);
      line.setAttribute("x2", p2.x); line.setAttribute("y2", p2.y);
      line.setAttribute("stroke", tok("--color-base-500", "#6c757d"));
      line.setAttribute("stroke-width", "2");
      svg.appendChild(line);
    });
  }

  function redraw(){
    inner.querySelectorAll(".workflow-node-card").forEach(function(el){ el.remove(); });
    nodes.forEach(function(n){
      var el = document.createElement("button");
      el.type = "button";
      el.className = "workflow-node-card position-absolute btn btn-light border shadow-sm btn-sm text-start";
      el.style.left = (n.position.x||20)+"px";
      el.style.top = (n.position.y||20)+"px";
      el.style.minWidth = "96px";
      el.dataset.kind = n.kind;
      el.dataset.id = n.id;
      el.setAttribute("aria-label", n.kind + " " + n.id);
      el.textContent = n.kind + " · " + n.id.slice(0,8);
      el.addEventListener("click", function(ev){
        ev.preventDefault(); ev.stopPropagation();
        if(!connectFrom){ connectFrom = n.id; el.classList.add("border-primary"); return;}
        if(connectFrom !== n.id){
          edges.push({from: connectFrom, to: n.id});
          inner.querySelectorAll(".workflow-node-card").forEach(function(x){ x.classList.remove("border-primary"); });
          connectFrom = null;
        } else { connectFrom = null; el.classList.remove("border-primary"); }
        redraw();
      });
      inner.appendChild(el);
    });
    document.getElementById("wf-dsl").textContent = JSON.stringify({nodes:nodes,edges:edges}, null, 2);
    redrawEdges();
  }

  function defaultConfig(kind){
    if(kind === "action") return {action: {type: "notify", params: {channel: "log", body: "Hello ${student_id}"}}};
    if(kind === "condition") return {condition: {field: "school_id", op: "eq", value: ((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["var_school_pk"])}};
    if(kind === "delay") return {seconds: 1};
    return {};
  }

  function pushNode(kind, x, y){
    var id = uid();
    nodes.push({id:id, kind:kind, config: defaultConfig(kind), position:{x:x,y:y}});
    if(kind==="trigger" && nodes.filter(function(z){return z.kind==="trigger"}).length>1){
      alert(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["trans_only_one_trigger_recommended_remove_extras"]));
    }
    redraw();
  }

  document.getElementById("wf-palette")?.addEventListener("dragstart", function(ev){
    var k = ev.target.getAttribute("data-kind");
    if(k) ev.dataTransfer.setData("kind", k);
  });
  inner.addEventListener("dragover", function(ev){ ev.preventDefault(); });
  inner.addEventListener("drop", function(ev){
    ev.preventDefault();
    var kind = ev.dataTransfer.getData("kind");
    if(!kind) return;
    var rect = inner.getBoundingClientRect();
    var x = ev.clientX - rect.left - 40;
    var y = ev.clientY - rect.top - 20;
    pushNode(kind, x, y);
  });

  document.getElementById("wf-add-node")?.addEventListener("click", function(){
    var kind = document.getElementById("wf-add-kind")?.value;
    var x = parseInt(document.getElementById("wf-add-x")?.value, 10) || 0;
    var y = parseInt(document.getElementById("wf-add-y")?.value, 10) || 0;
    pushNode(kind, x, y);
  });

  function postJson(url, body){
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type":"application/json","X-CSRFToken": csrftoken},
      body: JSON.stringify(body)
    }).then(function(r){ return r.json().then(function(j){ return { okHttp: r.ok, status: r.status, j: j }; }); });
  }

  document.getElementById("wf-save")?.addEventListener("click", function(){
    var payload = {
      workflow_id: document.getElementById("wf-id")?.value || null,
      name: document.getElementById("wf-name")?.value || "Flow",
      trigger_event: document.getElementById("wf-trigger")?.value,
      nodes: nodes,
      edges: edges
    };
    postJson(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["var_save_graph_url"]), payload).then(function(r){
      var j = r.j;
      if(j.workflow_id){ document.getElementById("wf-id").value = j.workflow_id; }
      document.getElementById("wf-dsl").textContent = JSON.stringify(j.compiled || j, null, 2);
      if(!j.ok && j.error){ alert(j.error); }
    }).catch(function(e){ alert(e); });
  });

  document.getElementById("wf-validate")?.addEventListener("click", function(){
    var wid = document.getElementById("wf-id")?.value;
    if(!wid){ alert(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["trans_save_the_graph_first_workflow_id_required"])); return; }
    postJson(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["var_validate_graph_url"]), {workflow_id: parseInt(wid,10)}).then(function(r){
      document.getElementById("wf-validate-out").textContent = JSON.stringify(r.j, null, 2);
    });
  });

  document.getElementById("wf-publish")?.addEventListener("click", function(){
    var wid = document.getElementById("wf-id")?.value;
    if(!wid){ alert(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["trans_save_the_graph_first_workflow_id_required_2"])); return; }
    if(!confirm(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["trans_confirm_publish"]))){ return; }
    postJson(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["var_publish_url"]), {workflow_id: parseInt(wid,10)}).then(function(r){
      var j = r.j;
      if(!r.okHttp && j.validation_errors){
        document.getElementById("wf-validate-out").textContent = JSON.stringify(j.validation_errors, null, 2);
        alert(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["trans_publish_blocked_invalid_graph"]));
        return;
      }
      alert(j.ok ? ((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["trans_published"]) : (j.error || JSON.stringify(j)));
    }).catch(function(e){ alert(e); });
  });

  document.getElementById("wf-rollback")?.addEventListener("click", function(){
    var wid = document.getElementById("wf-id")?.value;
    if(!wid){ return; }
    if(!confirm(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["trans_confirm_rollback"]))){ return; }
    postJson(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["var_rollback_url"]), {workflow_id: parseInt(wid,10)}).then(function(r){
      var j = r.j;
      alert(j.ok ? ((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["trans_moved_to_draft"]) : (j.error || JSON.stringify(j)));
    }).catch(function(e){ alert(e); });
  });

  document.getElementById("wf-sim")?.addEventListener("click", function(){
    var wid = document.getElementById("wf-id")?.value;
    if(!wid){ alert(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["trans_save_first_or_enter_workflow_id"])); return; }
    postJson(((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["var_simulate_url"]), {
      workflow_id: parseInt(wid,10),
      sample_payload: {school_id: ((window.__RMC_PAGE_DATA__["automation__visual_workflow_designer-1"] || {})["var_school_pk_2"]), student_id: 1}
    }).then(function(r){
      document.getElementById("wf-sim-out").textContent = JSON.stringify(r.j, null, 2);
    });
  });

  pushNode("trigger", 40, 40);
  redraw();
})();
})();
