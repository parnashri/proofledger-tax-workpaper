/* Authenticated, revision-checked SQLite collaboration bridge; static fallback for preview. */
'use strict';
window.proofServer=false;
window.proofUser=null;
let sharedRevision=0, writeWanted=0, sentSeq=0, writing=false, lastSharedState=null, pendingWrite=null;
const deepClone=(x)=>JSON.parse(JSON.stringify(x));
async function apiRequest(path,opts={}){
 const r=await fetch(path,{...opts,credentials:'same-origin',headers:{'Content-Type':'application/json',...(opts.headers||{})}});
 const json=await r.json().catch(()=>({error:`HTTP ${r.status}`}));
 if(!r.ok){const err=new Error(json.error||'Request failed');err.status=r.status;err.payload=json;throw err;}return json;
}
window.ensureDemoSession=async function(){
 let r;try{r=await fetch('/api/session',{credentials:'same-origin'});}catch{return;}
 if(r.status===404 || r.headers.get('content-type')?.includes('text/html'))return;
 window.proofServer=true;
 if(r.ok){const res=await r.json();window.proofUser=res.staff;return;}
 if(r.status!==401)throw Error('Server session unavailable');
 // The case study explicitly requests role switching. Demo identities share a local
 // passphrase; the actual actor is fixed by an HttpOnly session on the server.
 return new Promise((resolve)=>{
   const cover=document.createElement('div');cover.id='proofLoginCover';cover.innerHTML=`<div class="proof-login-box"><div class="section-label">PROOFLEDGER · SHARED WORKPAPER</div><h1>Open the 2025 engagement</h1><p>Choose a demonstration staff identity. The server issues a session and enforces that role on every saved change.</p><form id="proofLoginForm"><label class="field-label">Staff identity</label><select id="proofLoginStaff"><option value="st-01">Priya Raman · Preparer</option><option value="st-02">Daniel Ortiz · Reviewer</option><option value="st-03">Helen Strand · Partner</option><option value="st-04">Marcus Bell · Preparer (masked records)</option><option value="st-05">Jo Kimura · Firm administrator</option><option value="st-06">Sam Adeyemi · Quality reviewer</option></select><label class="field-label">Staff password (shared demo passphrase only in demo mode)</label><input id="proofLoginPassword" type="password" autocomplete="off" required/><label class="field-label">Authenticator code (only for MFA accounts)</label><input id="proofLoginOtp" type="text" autocomplete="one-time-code" inputmode="numeric" pattern="[0-9]{6}" placeholder="Optional six digits"/><button type="submit" class="btn primary" style="width:100%">Open shared workpaper</button><p class="small-label" id="proofLoginError" role="alert"></p></form><p class="hint">Synthetic case data only. This demonstration authentication is not production SSO or MFA.</p></div>`;
   document.body.appendChild(cover);
   cover.querySelector('form').addEventListener('submit',async(e)=>{
     e.preventDefault();const btn=cover.querySelector('button');btn.disabled=true;
     try{const x=await apiRequest('/api/login',{method:'POST',body:JSON.stringify({staff_id:cover.querySelector('#proofLoginStaff').value,password:cover.querySelector('#proofLoginPassword').value,otp:cover.querySelector('#proofLoginOtp').value})});window.proofUser=x.staff;cover.remove();resolve();}
     catch(err){cover.querySelector('#proofLoginError').textContent=err.message;btn.disabled=false;}
   });
 });
};
window.loadSharedState=async function(){
 if(!window.proofServer)return;
 const x=await apiRequest('/api/workpaper');sharedRevision=x.revision;lastSharedState=deepClone(x.state);
 // Use the server record; never upload stale browser-local data on login.
 const clone=deepClone(x.state);state={...blankState(),...clone};
 if(typeof ensureEnhancedState==='function')ensureEnhancedState();
 const dot=document.querySelector('.status-dot');if(dot)dot.innerHTML='<span></span> Live shared workspace · SQLite';
 const desc=document.querySelector('.sidebar-bottom p');if(desc)desc.textContent='Shared workpaper, server-enforced roles, revision conflicts and audit. Synthetic data only.';
 localStorage.setItem(KEY,JSON.stringify(state));
};
window.queueSharedSave=function(s){
 if(!window.proofServer)return;
 writeWanted++;pendingWrite=deepClone(s);
 if(!writing)setTimeout(flushWrites,60);
};
async function flushWrites(){
 if(writing||!pendingWrite)return;
 writing=true;
 while(pendingWrite){
  const send=pendingWrite,seq=writeWanted;pendingWrite=null;
  try{
    const x=await apiRequest('/api/workpaper',{method:'POST',body:JSON.stringify({revision:sharedRevision,state:send})});
    sharedRevision=x.revision;lastSharedState=deepClone(x.state);
    if(seq===writeWanted){state={...blankState(),...x.state};if(typeof ensureEnhancedState==='function')ensureEnhancedState();localStorage.setItem(KEY,JSON.stringify(state));}
  }catch(err){
    if(err.status===409){sharedRevision=err.payload.revision;state={...blankState(),...err.payload.state};lastSharedState=deepClone(err.payload.state);if(typeof ensureEnhancedState==='function')ensureEnhancedState();localStorage.setItem(KEY,JSON.stringify(state));if(typeof render==='function')render();if(typeof toast==='function')toast('Another reviewer saved first. Your conflicting edit was not applied; review latest state.');}
    else {state={...blankState(),...(lastSharedState||{})};if(typeof ensureEnhancedState==='function')ensureEnhancedState();if(typeof render==='function')render();if(typeof toast==='function')toast('Server rejected save: '+err.message);}
    pendingWrite=null;writeWanted=seq;
    break;
  }
 }
 writing=false;
}
window.changeActingStaff=async function(id){
 if(!window.proofServer)return;
 if(!confirm('Switching demonstration identities signs in as a different staff member. Any pending changes must be saved first. Continue?')){document.querySelector('#staffSelect').value=activeStaff;return;}
 if(writing||pendingWrite){alert('Current review changes are still saving. Try switching again.');document.querySelector('#staffSelect').value=activeStaff;return;}
 const pass=prompt('Password for selected staff identity:','');if(pass===null){document.querySelector('#staffSelect').value=activeStaff;return;}
 try{await apiRequest('/api/login',{method:'POST',body:JSON.stringify({staff_id:id,password:pass,otp:prompt('Six-digit authenticator code if enabled (or leave blank):','')||''})});location.reload();}catch(err){document.querySelector('#staffSelect').value=activeStaff;alert(err.message);}
};
// Receive peers' saved changes. Refuse to overwrite in-flight edits.
async function pollShared(){
 if(!window.proofServer||!window.proofUser||writing||pendingWrite||typeof state==='undefined'||!state)return;
 try{const x=await apiRequest('/api/workpaper');if(x.revision===sharedRevision)return;
   sharedRevision=x.revision;lastSharedState=deepClone(x.state);state={...blankState(),...x.state};if(typeof ensureEnhancedState==='function')ensureEnhancedState();localStorage.setItem(KEY,JSON.stringify(state));if(typeof render==='function')render();
   if(typeof toast==='function')toast('Shared workpaper updated from a colleague.');
 }catch(err){/* temporary network errors never overwrite working data */}
}
setInterval(pollShared,2400);
