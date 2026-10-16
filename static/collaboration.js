/* Collaboration and reviewer inbox based on durable server revisions and real assignments. */
'use strict';
function reviewerInbox(){
 const current=activeStaff,entries=(state.tasks||[]).filter(t=>t.assignee===current&&t.status!=='done');
 const unanswered=(state.questions||[]).filter(q=>!q.answer);
 const changed=typeof updateChanges==='function'?updateChanges():[];
 const past=entries.filter(t=>t.due&&t.due<new Date().toISOString().slice(0,10));
 let out=hero('ASSIGNMENT INBOX / COLLABORATION','Your review inbox','Staff-specific assignments, reviewer changes and open client/colleague questions. In server mode, new records appear across browsers without refreshing.');
 out+=`<div class="metrics"><div class="metric"><small>Assigned to you</small><div class="value">${entries.length}</div></div><div class="metric"><small>Overdue tasks</small><div class="value">${past.length}</div></div><div class="metric"><small>Awaiting answer</small><div class="value">${unanswered.length}</div></div><div class="metric"><small>New colleague actions</small><div class="value">${changed.length}</div></div></div>`;
 out+=panel('My assignments',`<div class="panel-body">${entries.map(t=>`<div class="check-row"><div><strong>${esc(t.title)}</strong><div class="hint">Due ${esc(t.due)} · ${esc(t.area)} · created by ${esc(t.createdBy||'team')}</div></div><button class="btn ghost" data-act="task-done" data-id="${esc(t.id)}">Finish with evidence</button></div>`).join('')||'<div class="empty-message">No open assignments for this staff identity.</div>'}</div>`);
 out+=panel('Questions and response evidence',`<div class="panel-body">${unanswered.slice(-25).reverse().map(q=>`<div class="check-row"><div><strong>${esc(q.text)}</strong><div class="hint">To ${esc(q.to)} · created by ${esc(q.actor)} · ${date(q.at)}</div></div><button class="btn ghost" data-act="answer-question" data-id="${esc(q.id)}">Record response</button></div>`).join('')||'<div class="empty-message">No unanswered questions.</div>'}</div>`);
 out+=panel('Since your last acknowledgment',`<div class="panel-body"><div class="toolbar"><button class="btn primary" data-act="ack-change" ${changed.length?'':'disabled'}>Acknowledge reviewed changes</button><button class="btn ghost" data-route-go="review">Review desk →</button></div>${changed.slice(-35).reverse().map(a=>`<div class="note-item"><strong>${esc(a.type)} · ${esc(a.target)}</strong><small>${date(a.at)} · ${esc(a.actor)}</small><p>${esc(a.reason||'Server-authenticated change')}</p></div>`).join('')||'<div class="empty-message">No new colleague actions.</div>'}</div>`);
 return out;
}
const inboxRender=render;
render=function(){if(route==='inbox'){$('#content').innerHTML=reviewerInbox();$('#navIssues').textContent=issueCount();return;}return inboxRender();};
const inboxView=viewPage;
viewPage=function(n){inboxView(n);if(n==='inbox')$('#sectionTitle').textContent='Reviewer inbox';};
// For reviewers, a sign-off can only be trusted if the shared server accepts it.
const inboxOverview=overview;
overview=function(){const assigned=(state.tasks||[]).filter(x=>x.assignee===activeStaff&&x.status==='open');return inboxOverview()+panel('Shared team activity',`<div class="panel-body"><div class="check-row"><div><strong>${assigned.length} open assignments for ${esc(user().name)}</strong><div class="hint">${window.proofServer?'SQLite-backed shared engagement · conflict checked · enforced role identity':'Browser-only offline demonstration; run server.py for real shared sessions'}</div></div><button class="btn primary" data-route-go="inbox">Open my inbox →</button></div></div>`);};
