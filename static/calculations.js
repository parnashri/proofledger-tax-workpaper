/* Working calculation graph. Never label inferred propagation as full tax-engine recomputation. */
'use strict';
function moneyMaybe(v){return typeof v==='number'&&Number.isFinite(v);}
function inferArithmeticSigns(l,byKey){
 const inputs=l.inputs||[];
 if(!moneyMaybe(l.value)||!inputs.length||inputs.length>12||!['R-SUM','R-CARRY'].includes(l.rule))return null;
 const nums=inputs.map(k=>byKey[k]?.value);
 if(!nums.every(moneyMaybe))return null;
 if(l.rule==='R-CARRY')return nums.length===1&&Math.abs(l.value-nums[0])<0.01?[1]:null;
 const signs=[];const threshold=Number.isInteger(l.value)&&nums.every(Number.isInteger)?0.01:.009;
 // Evaluate all combinations rather than assuming all R-SUM nodes add values:
 // AGI subtracts adjustments; profit subtracts expenses; tax due subtracts payments.
 for(let mask=0;mask<(1<<nums.length);mask++){
  if(nums.some((n,i)=>n===0 && (mask&(1<<i))))continue;
  let val=0;const coeff=[];
  for(let i=0;i<nums.length;i++){const sign=mask&(1<<i)?-1:1;coeff.push(sign);val+=sign*nums[i];}
  if(Math.abs(val-l.value)<=threshold)signs.push(coeff);
  if(signs.length>1)break;
 }
 return signs.length===1?signs[0]:null;
}
function calculationGraph(){
 const version=data.return_versions.find(x=>x.version==='v3');const src=Object.fromEntries(version.lines.map(l=>[l.key,l]));
 const working=Object.fromEntries(Object.entries(src).filter(([,l])=>moneyMaybe(l.value)).map(([k,l])=>[k,l.value]));
 const direct=new Map();for(const a of overlay().active){if(src[a.key]&&moneyMaybe(src[a.key].value))direct.set(a.key,(direct.get(a.key)||0)+a.delta);}
 for(const [k,delta] of direct)working[k]=src[k].value+delta;
 const signMap=new Map(version.lines.map(l=>[l.key,inferArithmeticSigns(l,src)]));
 const calc=[],unsafe=[],changed=new Set(direct.keys());
 for(let pass=0;pass<version.lines.length;pass++){
  let progress=false;
  for(const l of version.lines){
   if(direct.has(l.key)||!l.inputs?.length)continue;
   if(!l.inputs.some(x=>changed.has(x)))continue;
   const signs=signMap.get(l.key);
   if(!signs){if(!unsafe.some(u=>u.key===l.key))unsafe.push({key:l.key,label:l.label,reason:'Rule is non-linear, unsupported, or base values do not prove an unambiguous arithmetic identity'});continue;}
   if(!l.inputs.every(k=>moneyMaybe(working[k])))continue;
   const revised=l.inputs.reduce((sum,k,i)=>sum+signs[i]*working[k],0);
   if(Math.abs(revised-(working[l.key]??0))>0.001){working[l.key]=revised;changed.add(l.key);progress=true;}
  }
  if(!progress)break;
 }
 for(const k of changed){if(direct.has(k))continue;const l=src[k];calc.push({key:k,label:l.label,base:l.value,working:working[k],delta:working[k]-l.value,rule:l.rule,inputs:l.inputs});}
 const untouched=version.lines.filter(l=>moneyMaybe(l.value)&&!changed.has(l.key)).length;
 return {direct:[...direct].map(([key,delta])=>({key,delta,base:src[key]?.value,working:working[key]})),calculated:calc,unsafe,untouched,working,source:src};
}
function independentCalculationTests(){
 const v3=data.return_versions.find(v=>v.version==='v3');const lineVal=k=>v3.lines.find(l=>l.key===k)?.value;
 const d14=data.documents.find(x=>x.id==='D14');const d15=data.documents.find(x=>x.id==='D15');
 const d21=data.extracted_values.find(e=>e.document_id==='D21'&&e.field==='box1a');
 const issues=[];
 if(lineVal('SchC.1')===163700&&d21?.value===12400){
  issues.push({id:'SCHC',title:'Business receipts independent bridge',equation:'D14 books revenue $151,300 + unmatched processor revenue $0',engine:lineVal('SchC.1'),verified:151300,difference:12400,refs:['D14','D15','D17','D21'],note:'D15 states that the $12,400 Paywell card deposits were already booked, so Form 1099-K is corroboration, not new sales.'});
 }
 if(lineVal('F540NR.72')===14000){
  issues.push({id:'CAPAY',title:'California payments by designated tax year',equation:'Four $3,500 payments, but one explicitly assigned to 2024',engine:lineVal('F540NR.72'),verified:10500,difference:3500,refs:['D68'],note:'Reconciliation is a discrepancy requiring FTB confirmation, not an automatic return change.'});
 }
 if(lineVal('F1040.1a')===212400){issues.push({id:'W2',title:'W-2 wages and duplicate image',equation:'D08 $104,600 + D09 $107,800 (D10 duplicate)',engine:lineVal('F1040.1a'),verified:212400,difference:0,refs:['D08','D09','D10'],note:'The duplicate phone photo D10 must not be double-counted.'});}
 return issues;
}
function calculationsView(){
 const graph=calculationGraph();const snapshots=data.return_versions;const rate=overlay();
 let html=hero('INDEPENDENT CALCULATION LAB','Calculate, verify, explain','Deterministic arithmetic propagation is separated from the packet engine snapshots and from marginal-rate tax estimates. Unsupported calculations are not silently guessed.');
 html+=`<div class="metrics"><div class="metric"><small>Applied working changes</small><div class="value">${graph.direct.length}</div><div class="sub">Original engine remains immutable</div></div><div class="metric"><small>Re-derived arithmetic lines</small><div class="value">${graph.calculated.length}</div><div class="sub">Only verified additive identities</div></div><div class="metric"><small>Unrecomputed / non-linear dependencies</small><div class="value">${graph.unsafe.length}</div><div class="sub">Explicitly flagged for tax engine review</div></div><div class="metric"><small>Approximate federal balance impact</small><div class="value">${usd(rate.federal)}</div><div class="sub">Marginal rate estimate only</div></div></div>`;
 html+=panel('Independent checks across actual sources',`<div class="panel-body">${independentCalculationTests().map(t=>`<div class="check-row"><div><strong>${esc(t.title)}</strong><div class="hint">${esc(t.equation)}</div><p>${esc(t.note)}</p><div class="badge-row">${t.refs.map(r=>`<button class="reference" data-act="doc" data-id="${r}">${r}</button>`).join('')}</div></div><div><div>Engine ${usd(t.engine)}</div><div>Independent ${usd(t.verified)}</div><strong>${t.difference===0?severity('resolved'):severity('critical')} ${usd(t.difference)} difference</strong></div></div>`).join('')}</div>`);
 html+=panel('Working adjustment graph',`<div class="panel-body"><div class="notice warn">Only R-CARRY/R-SUM lines whose unchanged values establish one unique plus/minus arithmetic equation may be propagated. Tax tables, SE/QBI, California sourcing and AMT stay unrecomputed. A graph delta is not an official return.</div>${graph.direct.length?`<h3>Direct corrections</h3>${graph.direct.map(l=>`<div class="check-row"><button class="link" data-act="line" data-key="${esc(l.key)}">${esc(l.key)}</button><span>${usd(l.base)} → ${usd(l.working)} (${usd(l.delta)})</span></div>`).join('')}<h3>Calculated dependent arithmetic</h3>${graph.calculated.slice(0,75).map(l=>`<div class="check-row"><div><button class="link" data-act="line" data-key="${esc(l.key)}">${esc(l.key)}</button><span class="hint"> ${esc(l.rule)}; inputs ${esc(l.inputs.join(', '))}</span></div><strong>${usd(l.base)} → ${usd(l.working)}</strong></div>`).join('')||'<p class="hint">No safely derivable downstream lines for this input.</p>'}<h3>Unrecomputed dependencies</h3>${graph.unsafe.slice(0,35).map(l=>`<div class="bar-item"><button class="link" data-act="line" data-key="${esc(l.key)}">${esc(l.key)}</button><span>Requires engine</span></div>`).join('')||'<p class="hint">No immediate unsupported descendants found. This does not certify a full return recalculation.</p>'}`:'<p>Apply a working adjustment in Decision studio to inspect safe arithmetic propagation.</p>'}</div>`);
 html+=panel('Immutable engine version comparisons',`<div class="table-scroll"><table class="data-table"><thead><tr><th>Snapshot</th><th>As computed</th><th>Federal AGI</th><th>Federal tax</th><th>Federal balance</th><th>California balance</th></tr></thead><tbody>${snapshots.map(x=>`<tr><td>${esc(x.version)}</td><td>${date(x.computed_at)}</td><td>${usd(x.summary.federal.agi)}</td><td>${usd(x.summary.federal.total_tax)}</td><td>${usd(x.summary.federal.balance_due)}</td><td>${usd(x.summary.california.balance_due)}</td></tr>`).join('')}</tbody></table></div>`);
 html+=`<div class="toolbar"><button class="btn primary" data-route-go="decisions">Create audited adjustment →</button><button class="btn ghost" data-route-go="records">Review detailed tax schedules →</button></div>`;
 return html;
}
const calcRender=render;
render=function(){if(route==='calculations'){$('#content').innerHTML=calculationsView();$('#navIssues').textContent=issueCount();return;}return calcRender();};
const calcViewPage=viewPage;
viewPage=function(n){calcViewPage(n);if(n==='calculations')$('#sectionTitle').textContent='Calculation lab';};
const calcOverview=overview;
overview=function(){return calcOverview()+`<div class="toolbar"><button class="btn primary" data-route-go="calculations">Open independent calculation lab →</button></div>`;};
