/* Structured judgment, penalty and due-diligence records for ten case-specific topics. */
'use strict';
const taxTopics=[
 ['stock-comp-amt','Stock options, ISO exercise and AMT','D12 · Form 6251','Clarify exercise and California Schedule P / AMT not computed by packet engine.'],
 ['s-corp-basis','S corporation basis and distributions','D39,D40 · Form 7203','2023 basis gap prevents unconditional reliance on stock basis conclusions.'],
 ['crypto-basis','Digital assets and missing transferred lot basis','D34,D35','Request acquisition history for lot with transferred-in zero basis.'],
 ['state-residency','California/Texas residency and wage sourcing','D09,D73','Review residence dates and work-location allocation; do not trust W-2 state box alone.'],
 ['foreign-reporting','Foreign deposit account, FATCA and FBAR','D01,D06 · Form 8938','Separate ownership of outside FinCEN Form 114 from income-tax reporting.'],
 ['asset-elections','Equipment deduction elections and California conformity','D22 · Form 4562','Capture section 179/bonus election, life, asset and state differences.'],
 ['ira-rollover','Backdoor Roth and Form 8606 IRA basis','D06 · Form 8606','Reconcile nondeductible basis against prior records and Form 5498.'],
 ['dependent-diligence','Dependent SSN, education and credits','D71 · Form 8867','Resolve conflicting dependent SSN and maintain required diligence evidence.'],
 ['payments-penalties','Federal/CA payments, extension and penalties','D68 · Form 2210','Separate tax year for CA estimated payments and capture penalty/exposure decision.'],
 ['charitable-substantiation','Noncash donations and contemporaneous proof','D64 · Form 8283','Inspect low-confidence receipt and fair-market-value substantiation.']
];
function taxJudgmentView(){
 const done=taxTopics.filter(([k])=>['reviewed','not_applicable'].includes(state.taxReviews?.[k]?.status)).length;
 const unresolved=taxTopics.filter(([k])=>state.taxReviews?.[k]?.status==='open').length;
 return hero('DUE DILIGENCE / ELECTIONS / PENALTIES','Structured judgment ledger','Decisions remain linked to evidence and to the human who accepted the treatment. The ledger does not invent missing tax authority or unsupported figures.')+`<div class="metrics"><div class="metric"><small>Reviewed / not applicable</small><div class="value">${done} / ${taxTopics.length}</div></div><div class="metric"><small>Needs further evidence</small><div class="value">${unresolved}</div></div></div>`+
 panel('Review each material tax judgment',`<div class="panel-body"><p class="hint">Use a reason and identify the authority or calculation being relied upon. “Needs follow-up” is deliberately blocking. For real returns an accountable CPA must decide each entry.</p>${taxTopics.map(([id,title,refs,scope])=>{const entry=state.taxReviews?.[id];return `<div class="tax-review"><div class="check-row"><div><strong>${esc(title)}</strong><div class="hint">${esc(refs)}</div><p>${esc(scope)}</p>${entry?`<small>Last assessment: ${esc(entry.by)} · ${date(entry.at)}</small><p>${esc(entry.reason)}</p>`:''}</div><div>${severity(entry?.status==='reviewed'?'resolved':entry?.status==='not_applicable'?'info':entry?.status==='open'?'critical':'warning')}</div></div><form class="form-grid" data-tax-judgment="${id}"><div><label class="field-label">Disposition</label><select name="status"><option value="open">Needs follow-up</option><option value="reviewed" ${entry?.status==='reviewed'?'selected':''}>Reviewed / evidenced</option><option value="not_applicable" ${entry?.status==='not_applicable'?'selected':''}>Considered / not applicable</option></select></div><div><label class="field-label">Source reference(s)</label><input name="refs" required value="${esc(entry?.refs||refs)}"></div><div class="span2"><label class="field-label">Authority, computation or reliance limitation</label><input name="authority" required value="${esc(entry?.authority||'')}" placeholder="Form/instruction, reviewer memo, or unresolved missing information"></div><div class="span2"><label class="field-label">Decision rationale, result and next action</label><textarea name="reason" rows="2" required placeholder="Explain actual verification, limitations and next action">${esc(entry?.reason||'')}</textarea></div><div class="span2"><button class="btn primary">Save accountable assessment</button></div></form></div>`}).join('')}</div>`);
}
const judgmentState=ensureEnhancedState;
ensureEnhancedState=function(){judgmentState();if(!state.taxReviews)state.taxReviews={};};
const judgmentRender=render;
render=function(){if(route==='judgments'){$('#content').innerHTML=taxJudgmentView();$('#navIssues').textContent=issueCount();return;}return judgmentRender();};
const judgmentViewPage=viewPage;
viewPage=function(n){judgmentViewPage(n);if(n==='judgments')$('#sectionTitle').textContent='Judgment ledger';};
const judgmentBlockers=blockers;
blockers=function(){return judgmentBlockers()+taxTopics.filter(([id])=>!['reviewed','not_applicable'].includes(state.taxReviews?.[id]?.status)).length;};
const judgmentSubmit=handleSubmit;
handleSubmit=function(e){const form=e.target;
 if(form.dataset.taxJudgment){e.preventDefault();if(!modifyGuard())return;
  const id=form.dataset.taxJudgment,fields=new FormData(form),reason=(fields.get('reason')||'').trim(),authority=(fields.get('authority')||'').trim(),refs=(fields.get('refs')||'').trim(),status=fields.get('status');
  if(reason.length<15||authority.length<5||refs.length<3)return toast('Document the decision, authority and source references.');
  if(!['reviewed','not_applicable','open'].includes(status))return toast('Invalid disposition');
  state.taxReviews[id]={status,reason,authority,refs,actor:activeStaff,by:user().name,at:new Date().toISOString()};
  audit('judgment_assessed',id,reason,{authority,refs,status});invalidate('Structured tax judgment changed');render();toast('Judgment and source evidence saved.');return;
 }
 return judgmentSubmit(e);
};
const judgmentOverview=overview;
overview=function(){const n=taxTopics.filter(([id])=>!['reviewed','not_applicable'].includes(state.taxReviews?.[id]?.status)).length;return judgmentOverview()+panel('Judgment and election due diligence',`<div class="panel-body"><div class="check-row"><div><strong>${n} material tax judgments still need an evidence-backed decision</strong><div class="hint">Includes AMT, S corp basis, cryptocurrency, state allocation, international reporting, deductions and penalties.</div></div><button class="btn primary" data-route-go="judgments">Review judgments →</button></div></div>`);};
