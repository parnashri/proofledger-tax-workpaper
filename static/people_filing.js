'use strict';
(function(){
const routeNames={'clients':'People & client portal','filing-control':'Filing control','firm-portfolio':'Firm portfolio'};
for (const [name,label,glyph] of [['clients','People & client portal','♧'],['filing-control','Filing control','⇧'],['firm-portfolio','Firm portfolio','▦']]){
 if(document.querySelector(`#nav button[data-route="${name}"]`))continue;
 const b=document.createElement('button');b.dataset.route=name;b.innerHTML=`<span>${glyph}</span> ${label}`;
 document.querySelector('#nav').append(b);
}
let cache={},pending={},lastFetch={},freshToken=null;
// Source-view logs are written by the authenticated server, not trusted browser state.
if(typeof recordUnmasked==='function'){
 const offlineLog=recordUnmasked;
 recordUnmasked=function(docId){
   if(window.proofServer){apiRequest('/api/workflow/doc-view?document_id='+encodeURIComponent(docId)).catch(err=>console.warn('Sensitive view log error:',err.message));return;}
   return offlineLog(docId);
 };
}
const money=x=>typeof x==='number'?usd(x):esc(x);
function allowed(){return !!window.proofServer && !!window.proofUser;}
async function req(url,method='GET',value){return apiRequest(url,{method,...(value?{body:JSON.stringify(value)}:{})});}
function status(s){return `<span class="pill ${s?'resolved':'warning'}">${s?'COMPLETE':'OPEN'}</span>`;}
function noticeText(){return '<div class="notice warn"><strong>Case-study boundary:</strong> independent client acknowledgments, IRS responses and firm cases here are synthetic exercises. No legally valid e-signature, live IRS/FTB transmission, or production account system is provided.</div>';}
function people(){const obj=cache['clients'];let html=hero('REQUIREMENT 5 · PEOPLE','Clients, collaboration & approvals','Issue one-use invitations; clients respond under separate identities. Approvals are bound to the reviewed workpaper and reopen after material changes.')+noticeText();
 if(!obj)return html+'<div class="loading">Loading people and approvals from the shared server…</div>';
 const ps=['cu-01','cu-02'].map(id=>({id,name:id==='cu-01'?'Ngozi Okafor':'Erik Lindqvist',approval:obj.approvals.find(a=>a.client_id===id)}));
 html+=`<div class="metrics"><div class="metric"><small>Current client approvals</small><div class="value">${obj.approvals.filter(a=>a.current).length}/2</div></div><div class="metric"><small>Outstanding client answers</small><div class="value">${obj.questions.filter(q=>!q.answer).length}</div></div><div class="metric"><small>Review fingerprint</small><div class="value" style="font-size:17px">${esc(obj.fingerprint)}</div></div></div>`;
 html+=panel('Client identities and workpaper-bound approval',`<div class="panel-body">${ps.map(p=>`<div class="check-row"><div><strong>${esc(p.name)}</strong><div class="hint">${p.approval?`${esc(p.approval.decision)} · ${date(p.approval.at)} · fingerprint ${esc(p.approval.fingerprint)}`:'No response yet'}${p.approval&&!p.approval.current?' · Previous approval is not current':''}</div></div><div>${status(p.approval?.current)} <button class="btn ghost" data-workflow="invite" data-person="${p.id}" ${role()!=='partner'?'disabled':''}>Issue secure demo invite</button></div></div>`).join('')}<div id="workflowInviteOutput"></div><p class="hint">Invite links are valid once and expire in 72 hours. Only the partner can issue them; client responses never pass through the staff-role selector.</p></div>`);
 html+=panel('Ask a client (question becomes durable evidence)',`<div class="panel-body"><form id="workflowQuestion" class="form-grid"><div><label class="field-label">Recipient</label><select name="person"><option value="cu-01">Ngozi Okafor</option><option value="cu-02">Erik Lindqvist</option></select></div><div class="span2"><label class="field-label">Question</label><textarea name="question" required minlength="8" placeholder="What can only the client confirm? Include document references."></textarea></div><div class="span2"><button class="btn primary" ${['preparer','reviewer','partner'].includes(role())?'':'disabled'}>Send to client portal</button></div></form>${obj.questions.map(q=>`<div class="note-item"><strong>${esc(q.client_name)} · ${esc(q.id)}</strong><small>${date(q.created_at)} · ${esc(q.asked_by)}</small><p>${esc(q.question)}</p>${q.answer?`<div class="callout"><strong>Client answered:</strong> ${esc(q.answer)} · ${date(q.answered_at)}</div>`:'<p class="hint">Awaiting client answer</p>'}</div>`).join('')||'<p class="hint">No client questions yet.</p>'}</div>`);
 html+=panel('In-app notifications and review activity',`<div class="panel-body">${(obj.staff_notifications||[]).slice(0,20).map(n=>`<div class="note-item"><strong>${esc(n.title)}</strong> ${n.read_at?status(true):status(false)}<small>${date(n.at)}</small><p>${esc(n.body)}</p>${n.read_at?'':`<button class="btn ghost" data-workflow="notification-read" data-id="${esc(n.id)}">Mark read</button>`}</div>`).join('')||'<p class="hint">No updates for this reviewer.</p>'}</div>`);
 html+=panel('Invitation ledger',`<div class="panel-body">${obj.invitations.slice(0,25).map(i=>`<div class="bar-item"><span>${esc(i.client_id)} · issued by ${esc(i.created_by)} · ${date(i.created_at)}</span>${status(!!i.redeemed_at)}</div>`).join('')||'<p class="hint">No invitations issued yet.</p>'}</div>`);
 return html;
}
function filing(){const data=cache['filing-control'];let html=hero('REQUIREMENT 6 · FILING AND AFTER','Server-controlled filing lifecycle','Independent client approvals, stage gates, exact supplied agency-response fixtures, frozen filing checkpoints, amendments, notice cases and evidence exports.')+noticeText();
 if(!data)return html+'<div class="loading">Loading filing workflow…</div>';
 const flow=data.filing,can=role()==='partner',canDraft=['preparer','reviewer','partner'].includes(role());
 html+=`<div class="metrics"><div class="metric"><small>Lifecycle</small><div class="value" style="font-size:18px">${esc(flow.status.replaceAll('_',' '))}</div></div><div class="metric"><small>Client approvals</small><div class="value">${data.approvals.filter(a=>a.current).length}/2</div></div><div class="metric"><small>Federal</small><div class="value" style="font-size:18px">${esc(flow.jurisdictions.federal||'pending')}</div></div><div class="metric"><small>California</small><div class="value" style="font-size:18px">${esc(flow.jurisdictions.california||'pending')}</div></div></div>`;
 html+=panel('Filing readiness and state machine',`<div class="panel-body">${data.ready?'<div class="notice">Independent review, both CPA sign-offs and both client approvals are current.</div>':`<div class="notice warn"><strong>Blocking:</strong> ${esc(data.blocker)}</div>`}<div class="toolbar"><button class="btn ghost" data-workflow="filing:extension" ${!can||!!flow.frozen?'disabled':''}>Record historical extension</button><button class="btn primary" data-workflow="filing:prepare" ${!can||!!flow.frozen?'disabled':''}>Prepare filing fixture</button><button class="btn primary" data-workflow="filing:freeze" ${!can||!!flow.frozen?'disabled':''}>Freeze accepted return</button></div><p class="hint">The server rejects preparation until all required review areas, critical exceptions, sign-offs and **two independently logged-in clients' acknowledgments** are complete.</p></div>`);
 html+=panel('Scripted IRS / FTB response handling',`<div class="panel-body"><div class="toolbar"><select id="workflowEfileChoice">${window.data?.tax_agency_records.efile.map((r,i)=>`<option value="${i}">${esc(r.jurisdiction)} · ${esc(r.status)} · ${date(r.date)} (${esc(r.submission_id)})</option>`).join('')||''}</select><button class="btn primary" data-workflow="filing:agency_response" ${!can||!!flow.frozen?'disabled':''}>Import selected fixture</button></div><div class="toolbar"><input id="workflowRejectWhy" placeholder="How was rejection corrected? Cite D71 or other evidence" style="min-width:360px;flex:1"><button class="btn ghost" data-workflow="filing:clear_rejection" ${!can||!!flow.frozen?'disabled':''}>Document rejection correction</button></div>${flow.events.slice().reverse().slice(0,20).map(e=>`<div class="note-item"><strong>${esc(e.action)} ${e.jurisdiction?('· '+esc(e.jurisdiction)):''}</strong><small>${date(e.at)} · ${esc(e.actor)}</small>${e.status?`<p>${esc(e.status)} · ${esc(e.submission_id)}</p>`:''}${e.fix?`<p>${esc(e.fix)}</p>`:''}</div>`).join('')||'<p class="hint">No filing events yet.</p>'}</div>`);
 html+=panel('Immutable checkpoint & distinct amendment branch',`<div class="panel-body">${flow.frozen?`<div class="callout"><strong>Frozen:</strong> ${date(flow.frozen.at)} · prepared fingerprint ${esc(flow.frozen.fingerprint.slice(0,14))}<p>Original return cannot be edited; each amendment has its own change ledger.</p></div>`:'<p class="hint">Freeze becomes available only after both jurisdiction fixtures are accepted.</p>'}<div class="toolbar"><input id="workflowAmendWhy" placeholder="Reason for amendment" style="flex:1"><button class="btn ghost" data-workflow="filing:start_amendment" ${!can||!flow.frozen?'disabled':''}>Start amendment</button><button class="btn ghost" data-workflow="copy-export" ${!flow.frozen?'disabled':''}>Client copy (JSON)</button></div>${flow.amendments.map(a=>`<div class="note-item"><strong>${esc(a.id)} · ${esc(a.status)}</strong><p>${esc(a.reason)}</p><div class="toolbar"><input data-am-line="${esc(a.id)}" placeholder="Return line (e.g., SchC.1)"><input type="number" data-am-delta="${esc(a.id)}" placeholder="Adjustment"><input data-am-source="${esc(a.id)}" placeholder="Evidence D##"><button class="btn ghost" data-workflow="amend-add" data-id="${esc(a.id)}" ${canDraft?'':'disabled'}>Add amended change</button></div>${a.changes.map(c=>`<p class="hint">${esc(c.line)} · ${money(c.delta)} · ${esc(c.reason)} · ${esc(c.source)}</p>`).join('')}</div>`).join('')}</div>`);
 html+=panel('IRS notice response and evidence bundle',`<div class="panel-body"><div class="toolbar"><button class="btn ghost" data-workflow="filing:open_notice" ${!can||!flow.frozen?'disabled':''}>Open supplied 2028 Letter 566 case</button></div>${flow.notices.map(n=>`<div class="note-item"><strong>${esc(n.notice_id)} · ${esc(n.status)}</strong><small>Response due ${esc(n.due||'TBD')}</small><textarea data-notice-answer="${esc(n.id)}" placeholder="Describe the response, issues examined, and how they were verified"></textarea><input data-notice-evidence="${esc(n.id)}" placeholder="Sources: D14, D15, D21, D72"><div class="toolbar"><button class="btn primary" data-workflow="notice-answer" data-id="${esc(n.id)}" ${canDraft?'':'disabled'}>Save response</button><button class="btn ghost" data-workflow="notice-export" data-id="${esc(n.id)}">Evidence bundle (JSON)</button><button class="btn ghost" data-workflow="notice-close" data-id="${esc(n.id)}" ${can&&n.responses.length?'':'disabled'}>Close notice</button></div><p class="hint">${n.responses.length} recorded response(s). No correspondence sent.</p></div>`).join('')||'<p class="hint">No notice case opened.</p>'}</div>`);
 return html;
}
function portfolio(){let d=cache['firm-portfolio'];let html=hero('REQUIREMENT 7 · FIRM','Firm portfolio and administrative controls','Cross-engagement status, assignment and budget search, audit logs and administrator-controlled case registry. Only the supplied 2025 case contains real (fictional) tax packet data.')+noticeText();
 if(!d)return html+'<div class="loading">Loading firm portfolio…</div>';
 let cases=d.cases,admin=role()==='firm_administrator',needle=(document.querySelector('#workflowFirmSearch')?.value||'').toLowerCase();
 html+=`<div class="metrics"><div class="metric"><small>Engagements in registry</small><div class="value">${cases.length}</div></div><div class="metric"><small>Actual packet workpapers</small><div class="value">${cases.filter(c=>c.source==='packet').length}</div></div><div class="metric"><small>Registry-only demo shells</small><div class="value">${cases.filter(c=>c.source!=='packet').length}</div></div></div>`;
 html+=panel('Searchable cross-engagement portfolio',`<div class="panel-body"><input id="workflowFirmSearch" placeholder="Search case, client, owner, status, or year" value="${esc(needle)}" style="width:100%"><div id="workflowFirmRows">${cases.filter(c=>`${c.case_id} ${c.client_label} ${c.owner} ${c.status} ${c.tax_year}`.toLowerCase().includes(needle)).map(c=>`<div class="check-row"><div><strong>${esc(c.case_id)} · ${esc(c.client_label)}</strong><div class="hint">${esc(c.tax_year)} · ${esc(c.owner)} · due ${esc(c.due)} · ${esc(c.source==='packet'?'Complete supplied tax packet':'New workspace (tax return not included)')}</div><div class="hint">Budget ${esc(c.hours_budget)}h · Logged ${esc(c.hours_logged)}h · ${esc(c.task_count)} open tasks · ${esc(c.document_count)} source documents</div></div><div>${severity(c.status==='filed'?'resolved':'info')}<div class="hint">${esc(c.status)}</div>${admin&&c.source!=='packet'?`<select data-workflow-status="${esc(c.case_id)}"><option value="">Change status…</option>${['intake','in_review','waiting_client','ready_to_file','filed','closed'].map(v=>`<option value="${v}">${v}</option>`).join('')}</select><button class="btn ghost" data-workflow="case-status" data-id="${esc(c.case_id)}">Save</button>`:''}</div></div>`).join('')||'<p class="hint">No matching engagements</p>'}</div></div>`);
 html+=panel('Add an engagement',`<div class="panel-body"><p class="hint">New engagements start without imported tax-return data. Staff can add tasks, notes and supporting evidence.</p><form id="workflowNewCase" class="form-grid"><div><label class="field-label">Client label</label><input name="client_label" required minlength="3" placeholder="Training example only"></div><div><label class="field-label">Tax year</label><input name="tax_year" type="number" required value="2025"></div><div><label class="field-label">Assigned owner</label><select name="owner"><option value="st-01">Priya Raman</option><option value="st-02">Daniel Ortiz</option><option value="st-03">Helen Strand</option><option value="st-04">Marcus Bell</option></select></div><div><label class="field-label">Due date</label><input type="date" name="due"></div><div><label class="field-label">Hours budget</label><input type="number" name="hours_budget" min="0.1" max="1000" value="10" step="0.1"></div><div><button class="btn primary" ${admin?'':'disabled'}>Create registry case</button></div></form></div>`);
 html+=panel('Server-owned firm audit trail',`<div class="panel-body">${d.audit.slice(0,35).map(a=>`<div class="note-item"><strong>${esc(a.action)}</strong><small>${date(a.at)} · ${esc(a.actor)}</small><p>${esc(JSON.stringify(a.details))}</p></div>`).join('')||'<p class="hint">No firm actions yet.</p>'}</div>`);
 return html;
}
function page(){if(!allowed())return hero('SERVER REQUIRED','Start the shared Python server','Run python3 server.py --port 8081. Browser-only preview cannot provide independent client identities, controlled filing or a firm-wide database.');return route==='clients'?people():route==='filing-control'?filing():portfolio();}
async function load(force=false){const r=route;if(!routeNames[r]||!allowed())return;
 if(pending[r])return;
 if(!force&&cache[r]&&Date.now()-(lastFetch[r]||0)<4500)return;
 const urls={'clients':'/api/workflow/people','filing-control':'/api/workflow/filing','firm-portfolio':'/api/workflow/firm'};
 pending[r]=true;
 try{cache[r]=await req(urls[r]);lastFetch[r]=Date.now();if(route===r)document.querySelector('#content').innerHTML=page();}
 catch(e){if(route===r)toast('Workflow fetch failed: '+e.message);}
 finally{pending[r]=false;}
}
const prevRender=render;
render=function(){if(routeNames[route]){document.querySelector('#content').innerHTML=page();load();return;}prevRender();};
const prevView=viewPage;
viewPage=function(name){prevView(name);if(routeNames[name]){document.querySelector('#sectionTitle').textContent=routeNames[name];load(true);}};
async function send(url,args){try{const result=await req(url,'POST',args);toast('Saved to shared server.');await load(true);return result;}catch(err){toast('Blocked: '+err.message);return null;}}
function download(name,value){const blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1200);}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-workflow]');if(!b)return;e.preventDefault();const act=b.dataset.workflow,tid=b.dataset.id;
 if(act==='invite'){
  const r=await send('/api/workflow/invites',{client_id:b.dataset.person});if(r){freshToken=r;let out=document.querySelector('#workflowInviteOutput');if(out){out.innerHTML=`<div class="notice"><strong>One-time invitation for ${esc(r.client_name)}:</strong><p><input id="workflowInviteLink" readonly value="${esc(location.origin+r.path)}" style="width:100%"></p><button class="btn primary" data-workflow="copy-invite">Copy link</button><p class="hint">This is the only time the full invitation token is shown. Never include real client data.</p></div>`;}}
 }else if(act==='notification-read'){await send('/api/workflow/notifications/read',{notification_id:tid});}
 else if(act==='copy-invite'){const el=document.querySelector('#workflowInviteLink');if(el){el.select();try{await navigator.clipboard.writeText(el.value);toast('Link copied')}catch{toast('Select and copy the link')}}}
 else if(act.startsWith('filing:')){
  let action=act.split(':')[1],obj={action};
  if(action==='agency_response')obj.index=Number(document.querySelector('#workflowEfileChoice')?.value||0);
  if(action==='clear_rejection'){obj.fix=document.querySelector('#workflowRejectWhy').value;obj.evidence='D71 / corrected dependent identity';}
  if(action==='start_amendment')obj.reason=document.querySelector('#workflowAmendWhy').value;
  if(action==='open_notice')obj.notice_id='N-2025-L566';
  await send('/api/workflow/filing/action',obj);
 }else if(act==='amend-add'){
  const id=tid,line=document.querySelector(`[data-am-line="${id}"]`)?.value,delta=Number(document.querySelector(`[data-am-delta="${id}"]`)?.value),source=document.querySelector(`[data-am-source="${id}"]`)?.value;
  let reason=prompt('Explain what changed and why.');if(reason===null)return;
  await send('/api/workflow/filing/action',{action:'amendment_change',amendment_id:id,line,delta,source,reason});
 }else if(act==='notice-answer'||act==='notice-close'){
  const action=act==='notice-answer'?'notice_response':'close_notice';const answer=document.querySelector(`[data-notice-answer="${tid}"]`)?.value,evidence=document.querySelector(`[data-notice-evidence="${tid}"]`)?.value;
  await send('/api/workflow/filing/action',{action,case_id:tid,answer,evidence});
 }else if(act==='notice-export'||act==='copy-export'){
  try{let x=await req(act==='copy-export'?'/api/workflow/client-copy':'/api/workflow/notice-bundle?case_id='+encodeURIComponent(tid));download(act==='copy-export'?'client-copy-synthetic.json':'notice-response-evidence.json',x);}catch(err){toast('Export blocked: '+err.message);}
 }else if(act==='case-status'){
  await send('/api/workflow/firm/update',{case_id:tid,status:document.querySelector(`[data-workflow-status="${tid}"]`).value});
 }
});
document.addEventListener('submit',async e=>{
 if(!['workflowQuestion','workflowNewCase'].includes(e.target.id))return;e.preventDefault();const o=Object.fromEntries(new FormData(e.target));if(e.target.id==='workflowQuestion')await send('/api/workflow/questions',{client_id:o.person,question:o.question});
 else await send('/api/workflow/firm/create',{client_label:o.client_label,tax_year:Number(o.tax_year),owner:o.owner,due:o.due,hours_budget:Number(o.hours_budget)});
});
document.addEventListener('input',e=>{
 if(e.target.id==='workflowFirmSearch'&&cache['firm-portfolio']){let needle=e.target.value.toLowerCase(),cases=cache['firm-portfolio'].cases,container=document.querySelector('#workflowFirmRows');if(container)container.querySelectorAll('.check-row').forEach(row=>row.style.display=row.textContent.toLowerCase().includes(needle)?'':'none');}
});
})();
