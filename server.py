#!/usr/bin/env python3
"""ProofLedger case-study server: shared SQLite workpaper, authenticated demo sessions,
server-side role enforcement, compare-and-swap revisions and audit records.
All tax/identity data in the supplied packet is synthetic. No IRS integration.
"""
import argparse
import copy
import hashlib
import hmac
import http.cookies
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from mimetypes import guess_type
import workflow as wf
import security as sec
import firm as firm_store

HERE = Path(__file__).resolve().parent
PACKET = json.loads((HERE / 'packet.json').read_text())
STAFF = {x['id']: x for x in PACKET['firm']['staff']}
DB = Path(os.getenv('PROOFLEDGER_DB', str(HERE / 'proofledger_shared.sqlite3')))
DEMO_PASSWORD = os.getenv('PROOFLEDGER_DEMO_PASSWORD', 'proofledger-demo')
STRICT_AUTH=os.getenv('PROOFLEDGER_STRICT_AUTH','0')=='1'
LOCK = threading.RLock()
NOW = lambda: datetime.now(timezone.utc).isoformat()
COVERAGE = ['engagement','identity','prior','wages','business','investments','rentals','passthrough','retirement','international','charitable','education','payments','california','carryovers','due-diligence','agency']
CRITICAL = ['CA-PAY-2024','SCHC-1099K-DUP','SSN-THEO','CA-RESIDENCY']
JUDGMENT_TOPICS=['stock-comp-amt','s-corp-basis','crypto-basis','state-residency','foreign-reporting','asset-elections','ira-rollover','dependent-diligence','payments-penalties','charitable-substantiation']
BASE_MUTABLE = {'issueStatus','verifications','documentChecks','notes','questions','decisions','annotations','attachments','tasks','lastSeen','checkpoints','coverage','docDisposition','batchHistory','timeEntries','adjustments','filingFlow','signoffs','filing','standardsOverride','viewLog','taxReviews','plan2026'}
STATE_DEFAULTS = {'issueStatus':{},'verifications':{},'documentChecks':{},'notes':[],'questions':[],'decisions':[],'signoffs':{},'filing':None,'annotations':[],'attachments':[],'tasks':[],'viewLog':[],'lastSeen':{},'version':'v3','audit':[],'adjustments':[],'coverage':{},'docDisposition':{},'filingFlow':{'events':[],'authorizations':[],'responses':[],'amendments':[],'noticeResponses':[]},'timeEntries':[],'checkpoints':{},'batchHistory':[],'standardsOverride':{},'taxReviews':{},'plan2026':{}}
CORE_EDITORS = {'preparer','reviewer','partner'}
NO_EDIT = {'quality_reviewer'}

def conn():
    c = sqlite3.connect(DB, timeout=15, isolation_level=None)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA busy_timeout=15000')
    c.execute('CREATE TABLE IF NOT EXISTS workpaper (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, state TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, staff_id TEXT NOT NULL, expires TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS event_log (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, staff_id TEXT NOT NULL, kind TEXT NOT NULL, details TEXT NOT NULL, revision INTEGER NOT NULL)')
    c.execute('INSERT OR IGNORE INTO workpaper VALUES (1,0,?)', (json.dumps(STATE_DEFAULTS),))
    wf.init(c)
    sec.init(c)
    firm_store.init(c)
    return c

def clean_packet(value):
    """Mask sensitive synthetic fields in the returned source for staff without clearance.
    The real packet is served only to authenticated users by this server.
    """
    if isinstance(value, list): return [clean_packet(v) for v in value]
    if isinstance(value, dict):
        return {k:('••••••••' if k in ('ssn','ip_pin','account','routing','ein','tin','efin','ero_pin','ptin') else clean_packet(v)) for k,v in value.items()}
    if isinstance(value, str):
        value = re.sub(r'\b666-\d{2}-\d{4}\b', '•••-••-••••', value)
        value = value.replace('4483019276','••••••9276').replace('990000017','•••••0017').replace('482915','••••••')
    return value

def check_gate(s):
    docs=s.get('documentChecks',{}); exclude=s.get('docDisposition',{}); cov=s.get('coverage',{})
    if any(d['id'] not in docs and d['id'] not in exclude for d in PACKET['documents']): return False, 'All source documents require verification or reasoned exclusion'
    if any(cov.get(a,{}).get('status')!='complete' for a in COVERAGE): return False, 'All 17 review areas require completion'
    if any(cov.get('outside-'+str(i),{}).get('status')!='complete' for i in range(len(PACKET['household']['related_returns']))): return False,'Outside returns require owner/status verification'
    if any(s.get('issueStatus',{}).get(x,{}).get('status')!='resolved' for x in CRITICAL):return False,'Critical independent exceptions are unresolved'
    if any(x.get('status')=='open' and x.get('blocking') for x in s.get('notes',[])):return False,'Blocking review notes remain open'
    judgments=s.get('taxReviews',{})
    if any(judgments.get(t,{}).get('status') not in ('reviewed','not_applicable') for t in JUDGMENT_TOPICS):return False,'All 10 structured diligence/penalty/election reviews must be documented'
    return True, ''

def validate_edit(old, proposed, staff):
    role=staff['role']; actor=staff['id']
    changed={k for k in BASE_MUTABLE if proposed.get(k) != old.get(k)}
    extra=set(proposed)-BASE_MUTABLE-{'audit','version'}
    if extra: raise ValueError('Unknown or unauthorized review fields: '+','.join(sorted(extra)))
    if role in NO_EDIT and changed-{'lastSeen','checkpoints','viewLog'}: raise PermissionError('Quality-review role is read-only')
    if role=='firm_administrator' and changed-{'standardsOverride','timeEntries','lastSeen','checkpoints','viewLog'}:raise PermissionError('Firm administrator cannot modify tax review data')
    if role not in CORE_EDITORS|{'firm_administrator','quality_reviewer'}:raise PermissionError('Unknown staff role')
    if 'standardsOverride' in changed and role!='firm_administrator':raise PermissionError('Only administrator can change standards')
    if 'adjustments' in changed and role!='preparer':raise PermissionError('Only preparer can change numeric tax adjustments')
    if 'filing' in changed and role!='partner':raise PermissionError('Only partner can record filing checkpoint')
    if 'signoffs' in changed:
        if role not in {'reviewer','partner','preparer'}:raise PermissionError('Unauthorized sign-off')
        before=old.get('signoffs') or {};after=proposed.get('signoffs') or {}
        newly=[k for k in after if after.get(k)!=before.get(k)]
        if newly:
            if len(newly)!=1 or newly[0]!=role or role not in {'reviewer','partner'}:raise PermissionError('Staff may only sign their own assigned level')
            ok,reason=check_gate(proposed)
            if not ok:raise PermissionError('Sign-off blocked: '+reason)
            if role=='partner' and not after.get('reviewer'):raise PermissionError('Reviewer approval required first')
            if after[role].get('actor') != actor:raise PermissionError('Invalid sign-off actor')
    if 'filingFlow' in changed:
        before=old.get('filingFlow') or {}; after=proposed.get('filingFlow') or {}
        if before.get('responses')!=after.get('responses') and role!='partner':raise PermissionError('Only partner can record e-file fixture responses')
        # Scripted acceptance is only permitted after independent gate and approval.
        if any(r.get('status')=='accepted' and r not in before.get('responses',[]) for r in after.get('responses',[])):
            ok,why=check_gate(proposed)
            if not ok or not proposed.get('signoffs',{}).get('reviewer') or not proposed.get('signoffs',{}).get('partner') or not after.get('authorizations'):raise PermissionError('Scripted acceptance blocked: '+(why or 'review sign-offs and client authorization required'))
        for response in after.get('responses',[]):
            if not any(response.get('submission_id')==r['submission_id'] and response.get('status')==r['status'] and response.get('jurisdiction')==r['jurisdiction'] for r in PACKET['tax_agency_records']['efile']): raise ValueError('Only packet scripted response records are permitted')
        if len(after.get('responses',[])) < len(before.get('responses',[])):raise PermissionError('Historical responses are append-only')
    if old.get('filing'):
        permitted={'filingFlow','tasks','timeEntries','viewLog','lastSeen','checkpoints','plan2026'}
        if changed-permitted:raise PermissionError('Filed return is frozen; create an amendment branch')
        if 'filingFlow' in changed:
            prev=old.get('filingFlow',{});cur=proposed.get('filingFlow',{})
            if any(prev.get(k)!=cur.get(k) for k in ('events','authorizations','responses')):raise PermissionError('Original filing flow is frozen')
    if 'filing' in changed and proposed.get('filing'):
        ok,reason=check_gate(proposed)
        if not ok:raise PermissionError('Filing checkpoint blocked: '+reason)
        if not (proposed.get('signoffs',{}).get('reviewer') and proposed.get('signoffs',{}).get('partner')):raise PermissionError('Both approvals required')
        flow=proposed.get('filingFlow',{})
        if not flow.get('authorizations'):raise PermissionError('Recorded client authorization required')
        if not all(any(r.get('jurisdiction')==j and r.get('status')=='accepted' for r in flow.get('responses',[])) for j in ('federal','california')):raise PermissionError('Both scripted jurisdiction acceptances required')
    # Never trust client-originated claims to another staff actor on newly added records.
    for field in ('adjustments','tasks','notes','timeEntries','attachments','decisions','questions'):
        if field in changed:
            before=old.get(field) or [];after=proposed.get(field) or []
            prior_ids={x.get('id') for x in before if isinstance(x,dict)}
            for x in after:
                if isinstance(x,dict) and x.get('id') not in prior_ids and x.get('actor') and x['actor']!=actor:raise PermissionError('Spoofed staff attribution in '+field)
    for field in ('documentChecks','verifications','coverage','docDisposition','issueStatus','taxReviews'):
        if field in changed:
            for k, val in (proposed.get(field) or {}).items():
                if (old.get(field) or {}).get(k)!=val and isinstance(val,dict) and val.get('actor') and val['actor'] != actor:raise PermissionError('Spoofed staff attribution in '+field)
    # Audit entries are appended by server, not accepted from client.
    return changed

class Handler(BaseHTTPRequestHandler):
    server_version='ProofLedger'
    def log_message(self, fmt, *args):pass
    def json_reply(self,status,obj):
        raw=json.dumps(obj, ensure_ascii=False, default=str).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(raw)
    def body(self):
        size=int(self.headers.get('Content-Length','0'))
        if size<1 or size>8*1024*1024:raise ValueError('Invalid request size')
        return json.loads(self.rfile.read(size))
    def session(self):
        cookie=http.cookies.SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except http.cookies.CookieError:return None
        if 'pl_session' not in cookie:return None
        tok=cookie['pl_session'].value
        with conn() as c:
            r=c.execute('SELECT staff_id,expires FROM sessions WHERE token_hash=?',(hashlib.sha256(tok.encode()).hexdigest(),)).fetchone()
        if r and r[1]>NOW():return STAFF.get(r[0])
        return None
    def client_session(self):
        cookie=http.cookies.SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except http.cookies.CookieError:return None
        if 'pl_client' not in cookie:return None
        hashed=hashlib.sha256(cookie['pl_client'].value.encode()).hexdigest()
        with conn() as c:
            r=c.execute('SELECT client_id,expires FROM client_sessions WHERE token_hash=?',(hashed,)).fetchone()
        return r[0] if r and r[1]>NOW() else None
    def client_require(self):
        client=self.client_session()
        if not client:self.json_reply(401,{'error':'Client invitation sign-in is required'})
        return client
    def send_client_cookie(self, token, expires=28800):
        raw=json.dumps({'ok':True}).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)))
        secure='; Secure' if self.headers.get('X-Forwarded-Proto')=='https' else ''
        self.send_header('Set-Cookie',f'pl_client={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={expires}{secure}')
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(raw)
    def workflow_get(self,path):
        if path=='/api/workflow/client/home':
            client=self.client_require()
            if client:
                with conn() as c:
                    _,st=wf.workpaper(c)
                    return self.json_reply(200,wf.client_home(c,client,st,PACKET,check_gate))
            return
        staff=self.require()
        if not staff:return
        with conn() as c:
            _,st=wf.workpaper(c)
            if path=='/api/workflow/people':
                result=wf.staff_people(c,st,PACKET)
                result['staff_notifications']=wf.get_notifications(c,staff['id'])
                return self.json_reply(200,result)
            if path=='/api/workflow/notifications':return self.json_reply(200,{'notifications':wf.get_notifications(c,staff['id'])})
            if path=='/api/workflow/doc-view':
                code=parse_qs(urlparse(self.path).query).get('document_id',[''])[0]
                if code not in {d['id'] for d in PACKET['documents']}:return self.json_reply(400,{'error':'Unknown document'})
                if not staff['sensitive_data_clearance']:return self.json_reply(403,{'error':'Clearance required for source document access'})
                c.execute('INSERT INTO workflow_audit(at,actor,action,details) VALUES (?,?,?,?)',(NOW(),staff['id'],'sensitive_document_opened',json.dumps({'document_id':code})))
                return self.json_reply(200,{'logged':True,'document_id':code})
            if path=='/api/workflow/client-copy':return self.json_reply(200,wf.client_copy(c,st,PACKET))
            if path=='/api/workflow/notice-bundle':
                code=parse_qs(urlparse(self.path).query).get('case_id',[''])[0]
                return self.json_reply(200,wf.notice_bundle(c,st,PACKET,code))
            if path=='/api/workflow/filing':
                ok,reason=wf.guard(c,st,PACKET,check_gate)
                return self.json_reply(200,{'filing':wf.get_filing(c),'approvals':wf.approvals(c,st,PACKET),'ready':ok,'blocker':reason})
            if path=='/api/workflow/firm':return self.json_reply(200,wf.firm_summary(c,st,PACKET))
        return self.json_reply(404,{'error':'Unknown workflow resource'})
    def workflow_post(self,path):
        obj=self.body()
        if path=='/api/workflow/client/redeem':
            with LOCK,conn() as c:
                c.execute('BEGIN IMMEDIATE')
                token=wf.redeem_invite(c,str(obj.get('client_id','')),str(obj.get('invite_code','')))
                c.execute('COMMIT')
            return self.send_client_cookie(token)
        if path.startswith('/api/workflow/client/'):
            client=self.client_require()
            if not client:return
            with LOCK,conn() as c:
                c.execute('BEGIN IMMEDIATE')
                _,st=wf.workpaper(c)
                if path=='/api/workflow/client/decision':
                    result=wf.client_decision(c,client,obj.get('decision'),str(obj.get('typed_name','')),str(obj.get('evidence','')),st,PACKET,check_gate)
                elif path=='/api/workflow/client/answer':result=wf.client_answer(c,client,obj.get('question_id'),obj.get('answer',''))
                elif path=='/api/workflow/client/read':
                    c.execute('UPDATE notifications SET read_at=? WHERE recipient=? AND id=?',(NOW(),client,obj.get('notification_id')));result={'ok':True}
                else:raise ValueError('Unknown client action')
                c.execute('COMMIT')
            return self.json_reply(200,result)
        staff=self.require()
        if not staff:return
        role=staff['role'];actor=staff['id']
        with LOCK,conn() as c:
            c.execute('BEGIN IMMEDIATE')
            _,st=wf.workpaper(c)
            if path=='/api/workflow/invites':
                if role!='partner':raise PermissionError('Only partner can issue client invitations')
                result=wf.create_invite(c,actor,obj.get('client_id'))
            elif path=='/api/workflow/questions':
                if role not in ('preparer','reviewer','partner'):raise PermissionError('Tax team only')
                result=wf.create_question(c,actor,obj.get('client_id'),obj.get('question',''))
            elif path=='/api/workflow/notifications/read':
                c.execute('UPDATE notifications SET read_at=? WHERE recipient=? AND id=?',(NOW(),actor,obj.get('notification_id')));result={'ok':True}
            elif path=='/api/workflow/filing/action':
                action=obj.get('action')
                if role!='partner' and not (action in ('notice_response','amendment_change') and role in ('preparer','reviewer')):
                    raise PermissionError('Partner authorization required for this filing control action')
                result={'filing':wf.filing_action(c,actor,action,obj,st,PACKET,check_gate)}
            elif path=='/api/workflow/firm/create':
                if role!='firm_administrator':raise PermissionError('Administrator role required')
                result=wf.firm_case_create(c,actor,obj)
            elif path=='/api/workflow/firm/update':
                if role!='firm_administrator':raise PermissionError('Administrator role required')
                result=wf.firm_case_update(c,actor,obj)
            else:raise ValueError('Unknown workflow action')
            c.execute('COMMIT')
        return self.json_reply(200,result)
    def workspace_get(self,path):
        staff=self.require()
        if not staff:return
        if path=='/api/workspace/security':
            with conn() as c:return self.json_reply(200,sec.info(c,staff['id'],STRICT_AUTH))
        if path=='/api/workspace/detail':
            cid=parse_qs(urlparse(self.path).query).get('case_id',[''])[0]
            with conn() as c:return self.json_reply(200,firm_store.workspace(c,cid,staff))
        if path=='/api/workspace/filing/receipt':
            with conn() as c:
                _,state=wf.workpaper(c);flow=wf.get_filing(c)
                frozen=flow.get('frozen');current=wf.fingerprint(state,PACKET)
                ack=wf.approvals(c,state,PACKET)
                receipt={'format':'proofledger.demonstration.review-authorization.workspace','legally_binding_signature':False,'case_id':wf.CASE_ID,'tax_year':2025,'review_fingerprint':current,'clients':ack,'reviewer_signoff':state.get('signoffs',{}).get('reviewer'),'partner_signoff':state.get('signoffs',{}).get('partner'),'agency_fixture_events':flow.get('events',[]),'freeze':frozen,'integrity_matches_checkpoint':bool(frozen and frozen.get('fingerprint')==current),'note':'This is a demonstration audit receipt, not an IRS Form 8879 or a qualified e-signature.'}
                receipt['receipt_sha256']=wf.digest(receipt)
                return self.json_reply(200,receipt)
        if path=='/api/workspace/case/evidence':
            q=parse_qs(urlparse(self.path).query)
            cid=q.get('case_id',[''])[0];eid=q.get('id',[''])[0]
            with conn() as c:return self.json_reply(200,firm_store.download(c,cid,staff,eid))
        return self.json_reply(404,{'error':'Unknown workspace resource'})
    def workspace_post(self,path):
        obj=self.body()
        staff=self.require()
        if not staff:return
        actor=staff['id'];role=staff['role']
        with LOCK,conn() as c:
            c.execute('BEGIN IMMEDIATE')
            cid=str(obj.get('case_id',''))
            if path=='/api/workspace/case/record':res=firm_store.add_record(c,cid,staff,obj)
            elif path=='/api/workspace/case/status':res=firm_store.update_record(c,cid,staff,obj)
            elif path=='/api/workspace/case/evidence':res=firm_store.upload(c,cid,staff,obj)
            elif path=='/api/workspace/case/member':
                if role not in ('partner','firm_administrator'):raise PermissionError('Partner or administrator required')
                res=firm_store.set_member(c,cid,actor,str(obj.get('staff_id','')),str(obj.get('access','')),STAFF)
            elif path=='/api/workspace/client/revoke':
                if role!='partner':raise PermissionError('Only partner can revoke invitations')
                invite=str(obj.get('invite_id',''))
                row=c.execute('SELECT client_id FROM client_invites WHERE id=?',(invite,)).fetchone()
                if not row:raise ValueError('Invitation not found')
                c.execute('UPDATE client_invites SET revoked_at=? WHERE id=?',(NOW(),invite))
                c.execute('DELETE FROM client_sessions WHERE client_id=?',(row[0],))
                wf.trail(c,actor,'client_invitation_revoked',{'invite_id':invite,'client_id':row[0]})
                res={'ok':True,'client_sessions_revoked':True}
            else:raise ValueError('Unknown workspace action')
            c.execute('COMMIT')
        return self.json_reply(200,res)
    def require(self):
        s=self.session()
        if not s: self.json_reply(401,{'error':'Login required to access the shared workpaper.'})
        return s
    def do_GET(self):
        path=urlparse(self.path).path
        if path.startswith('/api/workspace/'):
            try:return self.workspace_get(path)
            except PermissionError as exc:return self.json_reply(403,{'error':str(exc)})
            except (ValueError,TypeError,KeyError) as exc:return self.json_reply(400,{'error':str(exc)})
            except Exception as exc:
                print('Unexpected workspace GET failure:',repr(exc),flush=True)
                return self.json_reply(500,{'error':'Internal server error'})
        if path.startswith('/api/workflow/'):
            return self.workflow_get(path)
        if path=='/api/session':
            s=self.session();return self.json_reply(200 if s else 401,{'staff':{'id':s['id'],'name':s['name'],'role':s['role'],'sensitive_data_clearance':s['sensitive_data_clearance']} if s else None})
        if path=='/api/packet' or path=='/packet.json':
            staff=self.require()
            if staff:self.json_reply(200,PACKET if staff['sensitive_data_clearance'] else clean_packet(PACKET))
            return
        if path=='/api/workpaper':
            staff=self.require()
            if staff:
                with conn() as c:rev,blob=c.execute('SELECT revision,state FROM workpaper WHERE id=1').fetchone()
                return self.json_reply(200,{'revision':rev,'state':json.loads(blob)})
            return
        if path=='/api/events':
            staff=self.require()
            if staff:
                with conn() as c:rows=c.execute('SELECT at,staff_id,kind,details,revision FROM event_log ORDER BY id DESC LIMIT 300').fetchall()
                return self.json_reply(200,{'events':[dict(at=x[0],actor=x[1],kind=x[2],details=json.loads(x[3]),revision=x[4]) for x in rows]})
            return
        if path.startswith('/api/'):
            return self.json_reply(404,{'error':'Unknown API endpoint'})
        rel=path.lstrip('/') or 'index.html'; allowed={'index.html','client.html'} | {'static/'+name for name in ('firm_workflows.js','people_filing.js','client.js','app.js','enhancements.js','calculations.js','collaboration.js','judgments.js','planning.js','session.js','style.css')}
        if rel not in allowed:return self.json_reply(404,{'error':'Not found'})
        f=HERE/rel
        if not f.is_file():return self.json_reply(404,{'error':'Not found'})
        raw=f.read_bytes();typ=guess_type(f.name)[0] or 'application/octet-stream'
        self.send_response(200);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            if origin and urlparse(origin).netloc!=self.headers.get('Host'):raise PermissionError('Cross-origin request denied')
            path=urlparse(self.path).path
            if path.startswith('/api/workspace/'):
                return self.workspace_post(path)
            if path.startswith('/api/workflow/'):
                return self.workflow_post(path)
            if path=='/api/login':
                obj=self.body();s=STAFF.get(obj.get('staff_id'));password=str(obj.get('password',''))
                if not s:
                    return self.json_reply(403,{'error':'Incorrect login credentials'})
                with conn() as c:
                    good=sec.verify(c,s['id'],password,str(obj.get('otp','')),STRICT_AUTH,DEMO_PASSWORD)
                if not good: return self.json_reply(403,{'error':'Incorrect login credentials or verification code'})
                token=secrets.token_urlsafe(40);expiry=(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat()
                with conn() as c:c.execute('INSERT INTO sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),s['id'],expiry))
                self.json_reply_cookie(200,{'staff':{'id':s['id'],'name':s['name'],'role':s['role'],'sensitive_data_clearance':s['sensitive_data_clearance']}},token)
                return
            if path=='/api/logout':
                c=http.cookies.SimpleCookie();c.load(self.headers.get('Cookie',''))
                if 'pl_session' in c:
                    with conn() as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(c['pl_session'].value.encode()).hexdigest(),))
                return self.json_reply_cookie(200,{'ok':True},'deleted',max_age=0)
            staff=self.require()
            if not staff:return
            if path=='/api/workpaper':
                obj=self.body();given=int(obj.get('revision',-1));incoming=obj.get('state')
                if not isinstance(incoming,dict):raise ValueError('Expected review state object')
                with LOCK,conn() as c:
                    c.execute('BEGIN IMMEDIATE')
                    rev,blob=c.execute('SELECT revision,state FROM workpaper WHERE id=1').fetchone();old={**copy.deepcopy(STATE_DEFAULTS),**json.loads(blob)}
                    if rev!=given:
                        c.execute('ROLLBACK')
                        return self.json_reply(409,{'error':'Concurrent review change detected. Refresh before retrying.','revision':rev,'state':old})
                    changed=validate_edit(old,incoming,staff)
                    flow=wf.get_filing(c)
                    if flow.get('frozen'):
                        allowed={'tasks','timeEntries','viewLog','lastSeen','checkpoints','plan2026'}
                        if changed-allowed:raise PermissionError('The server-frozen filed return is immutable; open an amendment in Filing control')
                    # Client authorizations must be recorded by the clients themselves, never by a CPA role switcher.
                    old_authorizations=old.get('filingFlow',{}).get('authorizations',[])
                    new_authorizations=incoming.get('filingFlow',{}).get('authorizations',[])
                    if new_authorizations!=old_authorizations:raise PermissionError('Client authorization must originate from the independent invitation-only client portal')
                    new={k:copy.deepcopy(incoming.get(k)) for k in BASE_MUTABLE if k in incoming}
                    # Preserve unmodified fields and server-authoritative audit.
                    for k in BASE_MUTABLE:
                        if k not in new and k in old:new[k]=old[k]
                    new['version']='v3'
                    audit=list(old.get('audit') or [])
                    # The server authenticates and appends actor-attributed client event details,
                    # never accepting modifications to historical log records.
                    existing_ids={x.get('id') for x in audit if isinstance(x,dict)}
                    for item in incoming.get('audit',[]):
                        if not isinstance(item,dict) or item.get('id') in existing_ids:continue
                        if item.get('actor')!=staff['id']:raise PermissionError('Audit actor mismatch')
                        event={k:item.get(k) for k in ('id','at','actor','type','target','reason','version','delta','evidence') if k in item}
                        event['server_actor']=staff['id']
                        audit.append(event)
                    # Material edits invalidate approvals even if the client forgets to clear them.
                    material=changed-{'signoffs','filing','timeEntries','viewLog','lastSeen','checkpoints','tasks','filingFlow','plan2026'}
                    if material and old.get('signoffs'):
                        new['signoffs']={}
                        changed.add('signoffs')
                        audit.append({'id':'srv-'+secrets.token_hex(8),'at':NOW(),'actor':staff['id'],'type':'signoffs_reopened','target':'engagement','reason':'Source/review material changed','version':'v3'})
                    if changed:
                        entry={'id':'srv-'+secrets.token_hex(8),'at':NOW(),'actor':staff['id'],'type':'server_review_commit','target':','.join(sorted(changed)),'reason':'Server-validated changes','version':'v3','revision':rev+1}
                        audit.append(entry)
                    new['audit']=audit[-6000:]
                    c.execute('UPDATE workpaper SET revision=?,state=? WHERE id=1',(rev+1,json.dumps(new,ensure_ascii=False)))
                    c.execute('INSERT INTO event_log(at,staff_id,kind,details,revision) VALUES (?,?,?,?,?)',(NOW(),staff['id'],'workpaper_changed',json.dumps({'fields':sorted(changed)}),rev+1))
                    if changed:
                        targets={'st-01','st-02','st-03'}-{staff['id']}
                        wf.announce(c,sorted(targets),'Engagement workpaper updated',staff['name']+' updated '+', '.join(sorted(changed))[:190])
                        if 'signoffs' in changed and old.get('signoffs') and not new.get('signoffs'):
                            wf.announce(c,list(wf.CLIENTS),'Review approvals reopened','The CPA workpaper changed. Any previous client approval must be reviewed again.')
                    c.execute('COMMIT')
                return self.json_reply(200,{'revision':rev+1,'state':new,'changed':sorted(changed)})
            self.json_reply(404,{'error':'Unknown endpoint'})
        except RuntimeError as exc:self.json_reply(409,{'error':str(exc)})
        except PermissionError as exc:self.json_reply(403,{'error':str(exc)})
        except (ValueError,TypeError,KeyError) as exc:self.json_reply(400,{'error':str(exc)})
        except Exception as exc:
            print('Unexpected server failure:',repr(exc),flush=True);self.json_reply(500,{'error':'Internal server error'})
    def json_reply_cookie(self,status,obj,token,max_age=43200):
        raw=json.dumps(obj).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
        secure='; Secure' if self.headers.get('X-Forwarded-Proto')=='https' else ''
        self.send_header('Set-Cookie',f'pl_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}{secure}')
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)

def main():
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8081);a=p.parse_args()
    with conn():pass
    print(f'ProofLedger workspace shared server http://{a.host}:{a.port} | SQLite {DB}\nUse fictional packet only. Strict individual account mode: {STRICT_AUTH}.',flush=True)
    ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()
if __name__=='__main__':main()
