/* Carryforward export and explicit scenario-based 2026 safe-harbor planning. */
'use strict';
const planEnhanced=ensureEnhancedState;
ensureEnhancedState=function(){planEnhanced();state.plan2026||={};};
function roundCents(n){return Math.round(n*100)/100;}
function safeHarborEstimate(anticipated,prior){return roundCents(Math.min(Math.max(0,anticipated)*0.90,prior*1.10));}
function planView(){
 const p=state.plan2026||{},tax2025=data.return_versions.find(v=>v.version==='v3').summary;
 const fed=Number(p.federalProjectedTax??tax2025.federal.total_tax),ca=Number(p.californiaProjectedTax??tax2025.california.total_tax);
 const f=safeHarborEstimate(fed,tax2025.federal.total_tax),c=safeHarborEstimate(ca,tax2025.california.total_tax);
 const ref=data.planning_reference_2026;
 let html=hero('AFTER FILING / CARRYOVER / PLANNING','Next-year continuity','Preserve the filed story, historical basis, unresolved exceptions and asset rollforwards; use the supplied 2026 reference rules to plan illustrative estimates.');
 html+=panel('Illustrative estimated payment planner',`<div class="panel-body"><div class="notice warn">These are hypothetical 2026 estimated-payment targets, not computed taxes or payment instructions. Actual 2026 income, credits and state sourcing are unknown. An extension does not extend time to pay.</div><form id="planForm" class="form-grid"><div><label class="field-label">Assumed 2026 federal total tax ($)</label><input type="number" id="planFed" min="0" step="1" value="${Number.isFinite(fed)?fed:0}" required></div><div><label class="field-label">Assumed 2026 CA total tax ($)</label><input type="number" id="planCa" min="0" step="1" value="${Number.isFinite(ca)?ca:0}" required></div><div class="span2"><label class="field-label">Planning note and important limitations</label><textarea id="planNote" rows="2" placeholder="Anticipated California-source rental, income, credits, AMT carryforward…">${esc(p.note||'')}</textarea></div><div class="span2"><button class="btn primary">Save assumptions with attribution</button></div></form><div class="two-col"><div class="callout"><small>Federal target · lesser of 90% forecast / 110% prior</small><div class="outcome">${usd(f)}</div><p>${esc(ref.federal_safe_harbor)}</p></div><div class="callout"><small>California target · lesser of 90% forecast / 110% prior</small><div class="outcome">${usd(c)}</div><p>${esc(ref.california_safe_harbor)}</p></div></div><h3>Suggested installments from supplied reference</h3><div class="two-col"><div>${ref.federal_estimate_due_dates.map(d=>`<div class="bar-item"><span>${esc(d)}</span><strong>${usd(roundCents(f/4))}</strong></div>`).join('')}</div><div>${ref.california_estimate_due_dates.map((d,i)=>`<div class="bar-item"><span>${esc(d)}</span><strong>${usd(roundCents(c*(ref.california_installment_percentages[i]||0)))}</strong></div>`).join('')}</div></div></div>`);
 html+=panel('Known next-year decisions',`<div class="panel-body">${ref.known_2026_changes_for_this_household.map(x=>`<div class="rule">${esc(x)}</div>`).join('')}<div class="toolbar"><button class="btn primary" data-act="export-carryforward">Export 2026 handoff bundle</button><button class="btn ghost" data-route-go="judgments">Open prior-year judgments →</button></div></div>`);
 return html;
}
const planRender=render;
render=function(){if(route==='planning'){$('#content').innerHTML=planView();$('#navIssues').textContent=issueCount();return;}return planRender();};
const planViewPage=viewPage;
viewPage=function(n){planViewPage(n);if(n==='planning')$('#sectionTitle').textContent='Next-year planning';};
const planSubmit=handleSubmit;
handleSubmit=function(e){if(e.target.id==='planForm'){
 e.preventDefault();if(!['preparer','reviewer','partner'].includes(role()))return toast('This role cannot edit tax projections.');
 const federalProjectedTax=Number($('#planFed').value),californiaProjectedTax=Number($('#planCa').value),note=$('#planNote').value.trim();
 if(!Number.isFinite(federalProjectedTax)||!Number.isFinite(californiaProjectedTax)||federalProjectedTax<0||californiaProjectedTax<0||note.length<12)return toast('Enter valid tax assumptions and a limitation note (12+ characters).');
 state.plan2026={federalProjectedTax,californiaProjectedTax,note,actor:activeStaff,by:user().name,at:new Date().toISOString()};audit('planning_assumptions_updated','2026',note);render();return;
 }return planSubmit(e);
};
const planClick=handleClick;
handleClick=function(e){const b=e.target.closest('[data-act]');if(b?.dataset.act==='export-carryforward'){
 const snap=data.return_versions.find(x=>x.version==='v3');
 exportPayload('ProofLedger_2026_handoff_DEMO.json',{notice:'Illustrative 2026 handoff, not an official tax return or rolled-forward tax engine result',client:data.packet,from_tax_year:2025,to_tax_year:2026,source_snapshot:'v3',filing_checkpoint:state.filing,carryovers_out:snap.carryovers_out,asset_register:snap.assets,prior_basis_history:data.prior_years.basis_records,judgment_decisions:state.taxReviews,source_document_index:data.documents.map(d=>({id:d.id,title:d.title,received_at:d.received_at})),review_issues:state.issueStatus,review_notes:state.notes,planning_reference:data.planning_reference_2026,assumptions:state.plan2026,audit:state.audit});return;
 }return planClick(e);
};
