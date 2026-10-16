'use strict';
(function(){
const nav=document.querySelector('#nav');
for(const [name,title,glyph] of [['engagement-workspace','Engagement workspace','▤'],['access-audit','Access & audit receipt','♜']]){
 if(!nav.querySelector(`[data-route="${name}"]`)){
  const b=document.createElement('button');b.dataset.route=name;b.innerHTML=`<span>${glyph}</span> ${title}`;nav.appendChild(b);
 }
}
const money=(n)=>new Intl.NumberFormat('en-US',{minimumFractionDigits:1,maximumFractionDigits:1}).format(n||0);
let allCases=[],cid='CL-20417',detail=null,auth=null,invites=[];
const req=async(path,method='GET',data)=>apiRequest(path,{method,...(data?{body:JSON.stringify(data)}:{})});
const safe=(x)=>esc(String(x??''));
function dl(name,data,mime='application/json'){
 const a=document.createElement('a'),blob=new Blob([data],{type:mime}),url=URL.createObjectURL(blob);
 a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
}
function workspace(){
 const top=hero('REQUIREMENTS 5 & 7 · CASE WORKSPACE','Multi-engagement review workspace','A second engagement can now hold real assigned staff, tasks, review decisions, time, case notes and encrypted supporting evidence. These records are not invented tax calculations.');
 if(!window.proofServer)return top+'<p>Start the Python backend to use real firm workspaces.</p>';
 let out=top+`<div class="notice warn">Cases other than CL-20417 have no tax engine data. File uploads require PROOFLEDGER_EVIDENCE_KEY; files are encrypted in SQLite and access-logged.</div>`;
 out+=`<div class="toolbar"><label>Engagement <select id="workspaceCasePicker">${allCases.map(c=>`<option value="${safe(c.case_id)}" ${cid===c.case_id?'selected':''}>${safe(c.client_label)} · ${safe(c.case_id)} · ${c.tax_year}</option>`).join('')}</select></label><button data-workspace="refresh" class="btn ghost">Refresh</button></div>`;
 if(!detail)return out+'<div class="loading">Loading authorized engagement records…</div>';
 const c=detail.case;
 out+=`<div class="metrics"><div class="metric"><small>Status</small><div class="value" style="font-size:18px">${safe(c.status)}</div></div><div class="metric"><small>Actual hours</small><div class="value">${money(detail.hours_logged)}</div></div><div class="metric"><small>Budget remaining</small><div class="value">${money(detail.budget_remaining)}</div></div><div class="metric"><small>Evidence items</small><div class="value">${detail.evidence.length}</div></div></div>`;
 const admin=['partner','firm_administrator'].includes(window.proofUser?.role);
 out+=panel('Case team and permissions',`<div class="panel-body"><p class="hint">Owner: ${safe(c.owner)}. Assigned staff receive engagement-specific read or edit permissions; the partner and firm administrator have management visibility.</p>${detail.members.map(m=>`<div class="bar-item"><strong>${safe(m.staff_id)}</strong> ${safe(m.access)}</div>`).join('')||'<p class="hint">No additional team members assigned.</p>'}${admin?`<form id="workspaceMember" class="toolbar"><select name="staff_id">${[['st-01','Priya — preparer'],['st-02','Daniel — reviewer'],['st-03','Helen — partner'],['st-04','Marcus — preparer'],['st-05','Jo — administrator'],['st-06','Sam — quality reviewer']].map(x=>`<option value="${x[0]}">${x[1]}</option>`).join('')}</select><select name="access"><option value="viewer">Viewer</option><option value="editor">Editor</option><option value="remove">Remove access</option></select><button class="btn primary">Update access</button></form>`:''}</div>`);
 out+=panel('Assignments, work performed, and review decisions',`<div class="panel-body">${detail.read_only?'<p class="notice warn">This role has read-only access.</p>':`<form id="workspaceNewRecord" class="form-grid"><div><label class="field-label">Record type</label><select name="kind"><option value="task">Task</option><option value="review">Review</option><option value="decision">Decision</option><option value="note">Note</option><option value="time">Time entry</option></select></div><div><label class="field-label">Title</label><input name="title" required minlength="3" placeholder="Confirm brokerage basis"></div><div class="span2"><label class="field-label">Evidence / explanation</label><textarea name="body" placeholder="Supporting document, decision and next step"></textarea></div><div><label class="field-label">Owner</label><select name="owner">${['st-01','st-02','st-03','st-04'].map(id=>`<option value="${id}">${id}</option>`).join('')}</select></div><div><label class="field-label">Deadline</label><input name="deadline" type="date"></div><div><label class="field-label">Hours (only time entry)</label><input name="hours" type="number" min="0" max="24" step="0.25" value="0"></div><div><button class="btn primary">Save record</button></div></form>`}${detail.records.map(r=>`<div class="note-item"><strong>${safe(r.title)}</strong><small>${safe(r.kind)} · ${safe(r.created_by)} · ${safe(r.created_at.slice(0,10))} · version ${r.revision}</small><p>${safe(r.body)}</p><div class="toolbar"><span class="pill">${safe(r.status)} ${r.kind==='time'?'· '+money(r.hours)+'h':''}</span>${!detail.read_only&&r.kind!=='time'?`<select data-workspace-status="${safe(r.id)}"><option value="open" ${r.status==='open'?'selected':''}>Open</option><option value="in_progress" ${r.status==='in_progress'?'selected':''}>In progress</option><option value="blocked" ${r.status==='blocked'?'selected':''}>Blocked</option><option value="resolved" ${r.status==='resolved'?'selected':''}>Resolved</option><option value="done" ${r.status==='done'?'selected':''}>Done</option></select><button data-workspace="record-status" data-id="${safe(r.id)}" data-revision="${r.revision}" class="btn ghost">Update</button>`:''}</div></div>`).join('')||'<p class="hint">No engagement activity recorded yet.</p>'}</div>`);
 out+=panel('Encrypted evidence (1 MB per file)',`<div class="panel-body">${detail.read_only?'':`<form id="workspaceUpload" class="toolbar"><input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.txt,.json" required><button class="btn primary">Encrypt and attach</button></form>`}${detail.evidence.map(e=>`<div class="check-row"><div><strong>${safe(e.filename)}</strong><div class="hint">${safe(e.mimetype)} · ${e.byte_len} bytes · SHA-256 ${safe(e.sha256.slice(0,18))}…</div></div><button class="btn ghost" data-workspace="evidence-get" data-id="${safe(e.id)}">Open evidence</button></div>`).join('')||'<p class="hint">No evidence has been added yet.</p>'}<p class="hint">These records are saved in SQLite. Opening evidence requires clearance and is logged.</p></div>`);
 return out;
}
function securityPage(){
 let out=hero('REQUIREMENTS 5 & 6 · ACCESS / FILING','Review identity & authorization receipt','Inspect named staff access, client invitation revocation and the server-generated filing checkpoint receipt.');
 if(!auth)return out+'<div class="loading">Loading access information…</div>';
 out+=panel('Staff account controls',`<div class="panel-body"><div class="metrics"><div class="metric"><small>Login mode</small><div class="value" style="font-size:16px">${auth.strict_auth?'Individual only':'Demo permitted'}</div></div><div class="metric"><small>Own login</small><div class="value" style="font-size:16px">${auth.individual_credentials?'Provisioned':'Shared demo'}</div></div><div class="metric"><small>MFA enabled</small><div class="value" style="font-size:18px">${auth.mfa_enabled?'Yes':'No'}</div></div></div><p class="hint">Staff-specific passwords and optional time-based verification codes are provisioned using the command-line utility; credentials are never shown in the workpaper. In strict mode, the shared demo passphrase is disabled.</p></div>`);
 out+=panel('Independent client invitations',`<div class="panel-body">${invites.map(i=>`<div class="check-row"><div><strong>${safe(i.client_id)}</strong><p class="hint">Issued ${safe(i.created_at)} · ${i.revoked_at?'REVOKED':i.redeemed_at?'Redeemed':'Outstanding'}</p></div><button class="btn ghost" data-workspace="revoke-invite" data-id="${safe(i.id)}" ${window.proofUser?.role!=='partner'||i.revoked_at?'disabled':''}>Revoke access</button></div>`).join('')||'<p class="hint">No client invitations issued.</p>'}<p class="hint">Revocation invalidates all portal sessions for the invited client. Existing approvals remain in the audit record but can become stale when reviewed tax data changes.</p></div>`);
 out+=panel('Auditable filing authorization receipt',`<div class="panel-body"><p class="hint">A SHA-256 digest binds reviewer sign-offs, both client acknowledgments, the reviewed workpaper fingerprint and recorded agency fixtures. The receipt is explicitly NOT an official Form 8879 or legally certified signature.</p><button class="btn primary" data-workspace="receipt">Download authorization audit receipt</button></div>`);
 return out;
}
async function loadWorkspace(){
 try{
  const firm=await req('/api/workflow/firm');allCases=firm.cases;
  if(!allCases.some(x=>x.case_id===cid))cid=allCases[0]?.case_id||'';
  detail=await req('/api/workspace/detail?case_id='+encodeURIComponent(cid));
 }catch(e){detail=null;toast('Workspace not available: '+e.message);}
 if(route==='engagement-workspace')document.querySelector('#content').innerHTML=workspace();
}
async function loadSecurity(){
 try{auth=await req('/api/workspace/security');invites=(await req('/api/workflow/people')).invitations;}
 catch(e){toast('Security information unavailable: '+e.message);}
 if(route==='access-audit')document.querySelector('#content').innerHTML=securityPage();
}
const oldRender=render;
render=function(){if(route==='engagement-workspace'){document.querySelector('#content').innerHTML=workspace();return;}if(route==='access-audit'){document.querySelector('#content').innerHTML=securityPage();return;}oldRender();};
const oldView=viewPage;
viewPage=function(name){oldView(name);if(name==='engagement-workspace'){document.querySelector('#sectionTitle').textContent='Engagement workspace';loadWorkspace();}if(name==='access-audit'){document.querySelector('#sectionTitle').textContent='Access & audit';loadSecurity();}};
async function save(path,data){try{await req(path,'POST',data);toast('Saved to shared server');await loadWorkspace();}catch(e){toast('Blocked: '+e.message);}}
document.addEventListener('change',e=>{if(e.target.id==='workspaceCasePicker'){cid=e.target.value;detail=null;loadWorkspace();}});
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-workspace]');if(!b)return;
 e.preventDefault();const action=b.dataset.workspace;
 if(action==='refresh'){await loadWorkspace();return;}
 if(action==='record-status'){await save('/api/workspace/case/status',{case_id:cid,id:b.dataset.id,revision:Number(b.dataset.revision),status:document.querySelector(`[data-workspace-status="${b.dataset.id}"]`).value});return;}
 if(action==='revoke-invite'){if(!confirm('Revoke this client invitation and invalidate the client\'s active portal sessions?'))return;try{await req('/api/workspace/client/revoke','POST',{invite_id:b.dataset.id});toast('Client portal access revoked');await loadSecurity();}catch(e){toast(e.message)}return;}
 if(action==='receipt'){try{const json=await req('/api/workspace/filing/receipt');dl('proofledger-filing-audit-receipt.json',JSON.stringify(json,null,2));}catch(e){toast(e.message)}return;}
 if(action==='evidence-get'){
  try{const file=await req('/api/workspace/case/evidence?case_id='+encodeURIComponent(cid)+'&id='+encodeURIComponent(b.dataset.id));
   const bytes=Uint8Array.from(atob(file.base64),c=>c.charCodeAt(0));dl(file.filename,bytes,file.mimetype);
  }catch(e){toast('File access denied: '+e.message)}
 }
});
document.addEventListener('submit',async e=>{
 if(!['workspaceMember','workspaceNewRecord','workspaceUpload'].includes(e.target.id))return;e.preventDefault();
 const form=e.target;const values=Object.fromEntries(new FormData(form));
 if(form.id==='workspaceMember')await save('/api/workspace/case/member',{case_id:cid,...values});
 if(form.id==='workspaceNewRecord')await save('/api/workspace/case/record',{case_id:cid,...values,hours:Number(values.hours||0)});
 if(form.id==='workspaceUpload'){
  const file=values.file;if(!file||file.size>1_000_000){toast('Select a file smaller than 1 MB');return;}
  const mime=({'application/pdf':'application/pdf','image/png':'image/png','image/jpeg':'image/jpeg','text/plain':'text/plain','application/json':'application/json'})[file.type]||({'pdf':'application/pdf','png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','txt':'text/plain','json':'application/json'})[file.name.split('.').pop().toLowerCase()];
  if(!mime){toast('Unsupported file type');return;}
  const bytes=new Uint8Array(await file.arrayBuffer());let raw='';bytes.forEach(x=>raw+=String.fromCharCode(x));
  await save('/api/workspace/case/evidence',{case_id:cid,filename:file.name,mimetype:mime,base64:btoa(raw)});
 }
});
})();
