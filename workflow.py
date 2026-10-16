"""Server-owned case-study workflows for people, filing, notices, and firm operations.
All records are synthetic. No e-file transmission or legally valid electronic signing.
"""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

CLIENTS = {'cu-01':'Ngozi Okafor','cu-02':'Erik Lindqvist'}
CASE_ID = 'CL-20417'

def now(): return datetime.now(timezone.utc).isoformat()
def dump(x): return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
def digest(x): return hashlib.sha256(dump(x).encode()).hexdigest()

def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS client_invites(id TEXT PRIMARY KEY, client_id TEXT NOT NULL, token_hash TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, expires TEXT NOT NULL, redeemed_at TEXT)')
    cols={r[1] for r in db.execute('PRAGMA table_info(client_invites)')}
    if 'revoked_at' not in cols: db.execute('ALTER TABLE client_invites ADD COLUMN revoked_at TEXT')
    db.execute('CREATE TABLE IF NOT EXISTS client_sessions(token_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, expires TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS client_confirmations(client_id TEXT PRIMARY KEY, decision TEXT NOT NULL, fingerprint TEXT NOT NULL, at TEXT NOT NULL, evidence TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS client_questions(id TEXT PRIMARY KEY, client_id TEXT NOT NULL, asked_by TEXT NOT NULL, question TEXT NOT NULL, created_at TEXT NOT NULL, answer TEXT, answered_at TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY, recipient TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS filing_control(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS firm_cases(case_id TEXT PRIMARY KEY, client_label TEXT NOT NULL, tax_year INTEGER NOT NULL, status TEXT NOT NULL, owner TEXT NOT NULL, due TEXT, hours_budget REAL NOT NULL, created_at TEXT NOT NULL, notes TEXT, source TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS workflow_audit(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL)')
    db.execute('INSERT OR IGNORE INTO filing_control(id,payload) VALUES(1,?)',(dump({'status':'draft','events':[],'jurisdictions':{},'frozen':None,'amendments':[],'notices':[]}),))
    db.execute('INSERT OR IGNORE INTO firm_cases VALUES (?,?,?,?,?,?,?,?,?,?)', (CASE_ID,'Okafor–Lindqvist household',2025,'in_review','st-03','2026-10-15',sum([1.5,3,4,3.5,3.5,2,2,1.5,1]),now(),'Supplied fictional engagement; only this record has tax data','packet'))

def workpaper(db):
    rev,state=db.execute('SELECT revision,state FROM workpaper WHERE id=1').fetchone()
    return rev,json.loads(state)

def fingerprint(state, packet):
    """Only substantive prepared-return review fields. Activity and notification reads don't invalidate approval."""
    keys=('issueStatus','verifications','documentChecks','notes','questions','decisions','adjustments','coverage','docDisposition','taxReviews','signoffs')
    return digest({'packet':packet['packet']['version'], 'v3_engine_summary':packet['return_versions'][2]['summary'], 'workpaper':{k:state.get(k) for k in keys}})

def invitations(db):
    return [dict(id=x[0],client_id=x[1],created_by=x[2],created_at=x[3],expires=x[4],redeemed_at=x[5],revoked_at=x[6]) for x in db.execute('SELECT id,client_id,created_by,created_at,expires,redeemed_at,revoked_at FROM client_invites ORDER BY created_at DESC LIMIT 30')]

def approvals(db, state, packet):
    fp=fingerprint(state,packet)
    return [dict(client_id=x[0],client_name=CLIENTS[x[0]],decision=x[1],at=x[3],current=(x[2]==fp and x[1]=='approve'),fingerprint=x[2][:14],evidence=x[4]) for x in db.execute('SELECT client_id,decision,fingerprint,at,evidence FROM client_confirmations ORDER BY client_id')]

def approvals_ready(db, state, packet):
    valid={x['client_id'] for x in approvals(db,state,packet) if x['current']}
    return valid==set(CLIENTS)

def note(db,recipient,title,body):
    db.execute('INSERT INTO notifications VALUES(?,?,?,?,?,NULL)', ('n-'+secrets.token_hex(9),recipient,title[:160],body[:600],now()))

def announce(db, recipients,title,body):
    for person in recipients:note(db,person,title,body)

def trail(db,actor,action,details):
    db.execute('INSERT INTO workflow_audit(at,actor,action,details) VALUES (?,?,?,?)',(now(),actor,action,dump(details)))

def get_notifications(db,recipient):
    return [dict(id=r[0],title=r[1],body=r[2],at=r[3],read_at=r[4]) for r in db.execute('SELECT id,title,body,created_at,read_at FROM notifications WHERE recipient=? ORDER BY created_at DESC LIMIT 150',(recipient,))]

def get_questions(db,client=None):
    if client: rows=db.execute('SELECT * FROM client_questions WHERE client_id=? ORDER BY created_at DESC',(client,))
    else:rows=db.execute('SELECT * FROM client_questions ORDER BY created_at DESC')
    return [dict(id=r[0],client_id=r[1],client_name=CLIENTS.get(r[1]),asked_by=r[2],question=r[3],created_at=r[4],answer=r[5],answered_at=r[6]) for r in rows]

def get_filing(db): return json.loads(db.execute('SELECT payload FROM filing_control WHERE id=1').fetchone()[0])
def set_filing(db,flow):db.execute('UPDATE filing_control SET payload=? WHERE id=1',(dump(flow),))

def guard(db,state,packet,check_gate):
    ok,why=check_gate(state)
    if not ok:return False,why
    if not(state.get('signoffs',{}).get('reviewer') and state.get('signoffs',{}).get('partner')):return False,'Reviewer and partner sign-offs must both be current'
    if not approvals_ready(db,state,packet):return False,'Both clients must independently approve this exact reviewed version'
    return True,'Ready for scripted filing exercise'

def staff_people(db,state,packet):
    return {'invitations':invitations(db),'approvals':approvals(db,state,packet),'questions':get_questions(db),'required_client_ids':list(CLIENTS),'staff_notifications':[], 'fingerprint':fingerprint(state,packet)[:14]}

def create_invite(db,actor,client_id):
    if client_id not in CLIENTS:raise ValueError('Unknown named client')
    token=secrets.token_urlsafe(28)
    db.execute('INSERT INTO client_invites(id,client_id,token_hash,created_by,created_at,expires,redeemed_at) VALUES (?,?,?,?,?,?,NULL)', ('i-'+secrets.token_hex(8),client_id,hashlib.sha256(token.encode()).hexdigest(),actor,now(),(datetime.now(timezone.utc)+timedelta(days=3)).isoformat()))
    trail(db,actor,'client_invitation_created',{'client_id':client_id})
    return {'client_id':client_id,'client_name':CLIENTS[client_id], 'invite_code':token, 'path':'/client.html?who='+client_id+'&invite='+token, 'expires_in_hours':72}

def redeem_invite(db,client_id,token):
    if client_id not in CLIENTS or not isinstance(token,str) or len(token)>256:raise ValueError('Invalid invitation')
    h=hashlib.sha256(token.encode()).hexdigest()
    r=db.execute('SELECT id,expires,redeemed_at,revoked_at FROM client_invites WHERE client_id=? AND token_hash=?',(client_id,h)).fetchone()
    if not r or r[2] or r[3] or r[1]<now():raise PermissionError('Invitation is invalid, expired or already redeemed')
    db.execute('UPDATE client_invites SET redeemed_at=? WHERE id=?',(now(),r[0]))
    session=secrets.token_urlsafe(40)
    db.execute('INSERT INTO client_sessions VALUES (?,?,?)',(hashlib.sha256(session.encode()).hexdigest(),client_id,(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()))
    trail(db,client_id,'client_portal_invite_redeemed',{'invitation_id':r[0]})
    return session

def client_home(db,client_id,state,packet,check_gate):
    ok,reason=check_gate(state)
    a=approvals(db,state,packet)
    return {'client_id':client_id,'name':CLIENTS[client_id], 'case_id':CASE_ID, 'tax_year':2025,'summary':packet['return_versions'][2]['summary'], 'review_ready':bool(ok and state.get('signoffs',{}).get('reviewer') and state.get('signoffs',{}).get('partner')), 'review_blocker':reason if not ok else 'Awaiting reviewer and partner sign-off' if not (state.get('signoffs',{}).get('reviewer') and state.get('signoffs',{}).get('partner')) else '', 'approvals':a,'questions':get_questions(db,client_id),'notifications':get_notifications(db,client_id),'fingerprint':fingerprint(state,packet)[:14], 'disclaimer':'This acknowledgment is a simulated consent record, not an IRS-approved Form 8879 or certified e-signature.'}

def client_decision(db,client_id,decision,typed_name,evidence,state,packet,check_gate):
    if get_filing(db).get('frozen'):raise PermissionError('The original return is frozen; send post-filing information to the tax team')
    if decision not in ('approve','request_changes'):raise ValueError('Invalid client decision')
    if typed_name.strip().casefold()!=CLIENTS[client_id].casefold():raise ValueError('Enter your full name exactly to acknowledge the reviewed summary')
    if not isinstance(evidence,str) or len(evidence.strip())<8:raise ValueError('Acknowledge what you reviewed or describe your concerns (8+ characters)')
    if decision=='approve':
        ok,why=check_gate(state)
        if not ok:raise PermissionError('Approval blocked: '+why)
        if not(state.get('signoffs',{}).get('reviewer') and state.get('signoffs',{}).get('partner')):raise PermissionError('Both CPA sign-offs required before client approval')
    fp=fingerprint(state,packet)
    db.execute('INSERT INTO client_confirmations(client_id,decision,fingerprint,at,evidence) VALUES(?,?,?,?,?) ON CONFLICT(client_id) DO UPDATE SET decision=excluded.decision,fingerprint=excluded.fingerprint,at=excluded.at,evidence=excluded.evidence',(client_id,decision,fp,now(),evidence[:1000]))
    announce(db,['st-01','st-02','st-03'],'Client '+decision.replace('_',' '),CLIENTS[client_id]+' responded to the reviewed 2025 summary')
    trail(db,client_id,'client_'+decision,{'review_fingerprint':fp[:14],'evidence':evidence[:300]})
    return {'ok':True,'decision':decision,'fingerprint':fp[:14]}

def create_question(db,actor,client_id,question):
    if client_id not in CLIENTS:raise ValueError('Unknown client')
    if not isinstance(question,str) or not 8<=len(question.strip())<=1600:raise ValueError('Question must have 8–1600 characters')
    qid='cq-'+secrets.token_hex(7)
    db.execute('INSERT INTO client_questions VALUES(?,?,?,?,?,NULL,NULL)',(qid,client_id,actor,question.strip(),now()))
    note(db,client_id,'Your tax preparer has a question',question[:160])
    trail(db,actor,'client_question_created',{'client_id':client_id,'id':qid})
    return {'id':qid}

def client_answer(db,client_id,qid,answer):
    if not isinstance(answer,str) or not 3<=len(answer.strip())<=2000:raise ValueError('Response must have 3–2000 characters')
    row=db.execute('SELECT asked_by,answer FROM client_questions WHERE id=? AND client_id=?',(qid,client_id)).fetchone()
    if not row or row[1] is not None:raise ValueError('Question not available or already answered')
    db.execute('UPDATE client_questions SET answer=?,answered_at=? WHERE id=?',(answer.strip(),now(),qid))
    note(db,row[0],'Client question answered',CLIENTS[client_id]+' answered '+qid)
    # New primary client testimony is material evidence. Reopen any existing CPA approval.
    rev,state=workpaper(db)
    if state.get('signoffs') and not get_filing(db).get('frozen'):
        state['signoffs']={}
        state.setdefault('audit',[]).append({'id':'srv-'+secrets.token_hex(8),'at':now(),'actor':client_id,'type':'signoffs_reopened','target':'client_answer','reason':'New client testimony received for '+qid})
        db.execute('UPDATE workpaper SET revision=?,state=? WHERE id=1',(rev+1,dump(state)))
        announce(db,['st-01','st-02','st-03']+list(CLIENTS),'CPA reviews reopened','A client response introduced new evidence; the workpaper needs fresh review')
    trail(db,client_id,'client_question_answered',{'question_id':qid,'answer':answer[:300]})
    return {'ok':True,'signoffs_reopened':bool(rev and not state.get('signoffs'))}

def filing_action(db,actor,kind,body,state,packet,check_gate):
    flow=get_filing(db)
    frozen=flow.get('frozen')
    def event(action,extra=None):
        value={'id':'fe-'+secrets.token_hex(7),'at':now(),'actor':actor,'action':action,**(extra or {})}
        flow['events'].append(value)
        trail(db,actor,'filing_'+action,extra or {})
        return value
    if kind=='extension':
        if frozen:raise PermissionError('Original filing is frozen')
        if any(e['action']=='extension' for e in flow['events']):raise ValueError('Extension already recorded')
        event('extension',{'source':'timeline:extension-2026-04-14','note':str(body.get('note','Historical fixture reviewed'))[:500]})
    elif kind=='prepare':
        if frozen:raise PermissionError('Original filing is frozen')
        ok,reason=guard(db,state,packet,check_gate)
        if not ok:raise PermissionError(reason)
        flow['status']='prepared_for_fixture'
        event('prepared_for_fixture',{'review_fingerprint':fingerprint(state,packet)[:14]})
    elif kind=='agency_response':
        if frozen:raise PermissionError('Original filing is frozen')
        if flow['status'] not in ('prepared_for_fixture','rejected','partial_acceptance'):raise PermissionError('Prepare the reviewed return first')
        ok,reason=guard(db,state,packet,check_gate)
        if not ok:raise PermissionError(reason)
        index=body.get('index')
        if not isinstance(index,int) or index<0 or index>=len(packet['tax_agency_records']['efile']):raise ValueError('Select a valid packet response index')
        record=packet['tax_agency_records']['efile'][index]
        if any(e.get('fixture_index')==index for e in flow['events']):raise ValueError('This fixture response was already recorded')
        if record['status']=='accepted' and any(e.get('status')=='rejected' for e in flow['events']) and not any(e['action']=='rejection_cleared' for e in flow['events']):raise PermissionError('Document the corrected rejection before importing acceptance')
        flow['jurisdictions'][record['jurisdiction']]=record['status']
        status=record['status']
        event('agency_response',{'fixture_index':index,'jurisdiction':record['jurisdiction'],'status':status,'submission_id':record['submission_id'],'errors':record.get('errors',[])})
        outstanding_rejection=any(e.get('status')=='rejected' for e in flow['events']) and not any(e['action']=='rejection_cleared' for e in flow['events'])
        flow['status']='rejected' if outstanding_rejection else 'partial_acceptance'
    elif kind=='clear_rejection':
        if flow['status']!='rejected':raise PermissionError('No outstanding rejection')
        fix=str(body.get('fix','')).strip()
        if len(fix)<15:raise ValueError('Document the corrected source and verification (15+ characters)')
        event('rejection_cleared',{'fix':fix[:1500],'evidence':str(body.get('evidence',''))[:240]})
        flow['status']='prepared_for_fixture'
    elif kind=='freeze':
        if frozen:raise PermissionError('Already frozen')
        ok,reason=guard(db,state,packet,check_gate)
        if not ok:raise PermissionError(reason)
        if any(flow['jurisdictions'].get(j)!='accepted' for j in ('federal','california')):raise PermissionError('Both federal and California must have an accepted agency fixture')
        flow['status']='accepted_frozen'
        flow['frozen']={'at':now(),'actor':actor,'fingerprint':fingerprint(state,packet),'packet_version':packet['packet']['version'],'workpaper_revision':workpaper(db)[0], 'accepted':dict(flow['jurisdictions'])}
        event('filing_frozen',{'fingerprint':flow['frozen']['fingerprint'][:14]})
    elif kind=='start_amendment':
        if not frozen:raise PermissionError('Freeze the original before opening an amendment branch')
        reason=str(body.get('reason','')).strip()
        if len(reason)<12:raise ValueError('Explain reason for amendment (12+ characters)')
        am={'id':'am-'+secrets.token_hex(5),'at':now(),'actor':actor,'status':'draft','reason':reason[:1000],'parent_fingerprint':frozen['fingerprint'],'changes':[]}
        flow['amendments'].append(am);event('amendment_created',{'id':am['id']})
    elif kind=='amendment_change':
        target=next((x for x in flow['amendments'] if x['id']==body.get('amendment_id')),None)
        if not target:raise ValueError('Unknown amendment')
        if target['status']!='draft':raise PermissionError('Amendment is no longer editable')
        reason=str(body.get('reason','')).strip()
        if len(reason)<8:raise ValueError('Explain amended change')
        target['changes'].append({'at':now(),'actor':actor,'line':str(body.get('line',''))[:100],'delta':body.get('delta'),'reason':reason[:800],'source':str(body.get('source',''))[:120]})
        event('amendment_change',{'id':target['id'],'line':str(body.get('line',''))[:100]})
    elif kind=='open_notice':
        if not frozen:raise PermissionError('Only filed returns can have a post-filing response in this exercise')
        nid=str(body.get('notice_id','N-2025-L566'))
        source=next((n for n in packet['tax_agency_records']['notices'] if n['id']==nid),None)
        if not source:raise ValueError('Unknown source notice')
        if any(n['notice_id']==nid for n in flow['notices']):raise ValueError('Notice case already opened')
        flow['notices'].append({'id':'nc-'+secrets.token_hex(5),'notice_id':nid,'received_at':now(),'due':source.get('response_due'),'status':'open','assigned_to':'st-02','responses':[]})
        event('notice_opened',{'notice_id':nid})
        announce(db,['st-02','st-03'],'IRS notice received',nid+' requires a response by '+str(source.get('response_due')))
    elif kind=='notice_response':
        n=next((n for n in flow['notices'] if n['id']==body.get('case_id')),None)
        if not n or n['status']=='closed':raise ValueError('Open a notice case first')
        answer=str(body.get('answer','')).strip();evidence=str(body.get('evidence','')).strip()
        if len(answer)<20 or len(evidence)<3:raise ValueError('Provide a response narrative and source evidence')
        n['responses'].append({'at':now(),'actor':actor,'answer':answer[:3000],'evidence':evidence[:600]})
        n['status']='draft_response'
        event('notice_response_drafted',{'id':n['id'],'evidence':evidence[:120]})
    elif kind=='close_notice':
        n=next((n for n in flow['notices'] if n['id']==body.get('case_id')),None)
        if not n or not n['responses']:raise ValueError('Document a response first')
        n['status']='closed'
        event('notice_closed',{'id':n['id']})
    else:raise ValueError('Unknown filing action')
    set_filing(db,flow)
    return flow

def client_copy(db,state,packet):
    flow=get_filing(db)
    if not flow.get('frozen'):raise PermissionError('No accepted and frozen filing checkpoint')
    return {'format':'proofledger.synthetic.client-copy.v1','not_a_filed_return':True,'case_id':CASE_ID,'tax_year':2025,'taxpayers':list(CLIENTS.values()),'engine_summary':packet['return_versions'][2]['summary'],'frozen_checkpoint':flow['frozen'],'recorded_client_acknowledgments':approvals(db,state,packet)}

def notice_bundle(db,state,packet,notice_case_id):
    f=get_filing(db)
    n=next((x for x in f['notices'] if x['id']==notice_case_id),None)
    if not n:raise ValueError('Unknown notice case')
    notice=next(x for x in packet['tax_agency_records']['notices'] if x['id']==n['notice_id'])
    doc_links=set()
    for response in n['responses']:
        for doc in packet['documents']:
            if doc['id'] in response['evidence']:doc_links.add(doc['id'])
    return {'format':'proofledger.synthetic.notice-response.v1','case_id':CASE_ID,'notice':notice,'response_work':n,'filing_checkpoint':f['frozen'],
            'source_documents':[d for d in packet['documents'] if d['id'] in doc_links],
            'source_fields':[e for e in packet['extracted_values'] if e['document_id'] in doc_links],
            'supporting_review_decisions':state.get('taxReviews',{}),
            'client_communications':get_questions(db),
            'client_acknowledgments':approvals(db,state,packet),
            'record_hash':digest({'notice':n,'source_ids':sorted(doc_links)}),
            'disclaimer':'Synthetic evidence package; no IRS correspondence transmitted'}

def firm_cases(db):
    return [dict(case_id=r[0],client_label=r[1],tax_year=r[2],status=r[3],owner=r[4],due=r[5],hours_budget=r[6],created_at=r[7],notes=r[8],source=r[9]) for r in db.execute('SELECT * FROM firm_cases ORDER BY created_at DESC')]

def firm_case_create(db,actor,body):
    label=str(body.get('client_label','')).strip(); year=body.get('tax_year');owner=str(body.get('owner','st-03')); due=str(body.get('due','')).strip()
    if not 3<=len(label)<=120 or not isinstance(year,int) or not 2020<=year<=2035:raise ValueError('Supply a 3–120 character label and a valid tax year')
    if owner not in ('st-01','st-02','st-03','st-04'):raise ValueError('Assign a recognized preparer, reviewer or partner')
    budget=float(body.get('hours_budget',10))
    if not 0<budget<=1000:raise ValueError('Budget hours must be positive and under 1000')
    cid='DEMO-'+secrets.token_hex(4).upper()
    db.execute('INSERT INTO firm_cases VALUES (?,?,?,?,?,?,?,?,?,?)',(cid,label,year,'intake',owner,due,budget,now(),'Blank demonstration registry shell; no tax documents attached','registry_shell'))
    trail(db,actor,'firm_case_created',{'case_id':cid,'client_label':label})
    return {'case_id':cid,'source':'registry_shell'}

def firm_case_update(db,actor,body):
    cid=str(body.get('case_id',''));status=str(body.get('status',''))
    if status not in ('intake','in_review','waiting_client','ready_to_file','filed','closed'):raise ValueError('Invalid status')
    x=db.execute('SELECT source FROM firm_cases WHERE case_id=?',(cid,)).fetchone()
    if not x:raise ValueError('Unknown firm case')
    if x[0]=='packet':raise PermissionError('Original packet case status follows the actual filing workpaper')
    db.execute('UPDATE firm_cases SET status=? WHERE case_id=?',(status,cid))
    trail(db,actor,'firm_case_status_updated',{'case_id':cid,'status':status})
    return {'case_id':cid,'status':status}

def firm_summary(db,state,packet):
    cases=firm_cases(db); f=get_filing(db)
    for case in cases:
        if case['case_id']==CASE_ID:
            case['status']= 'filed' if f.get('frozen') else 'in_review'
            case['hours_logged']=round(sum(float(x.get('hours',0) or 0) for x in state.get('timeEntries',[])),2)
            case['task_count']=len([x for x in state.get('tasks',[]) if x.get('status')!='done'])
            case['document_count']=len(packet['documents'])
        else:
            case['hours_logged']=round(db.execute("SELECT COALESCE(SUM(hours),0) FROM case_records WHERE case_id=? AND kind='time'",(case['case_id'],)).fetchone()[0],2)
            case['task_count']=db.execute("SELECT COUNT(*) FROM case_records WHERE case_id=? AND kind='task' AND status NOT IN ('done','resolved')",(case['case_id'],)).fetchone()[0]
            case['document_count']=db.execute('SELECT COUNT(*) FROM case_evidence WHERE case_id=?',(case['case_id'],)).fetchone()[0]
    audit=[dict(at=r[0],actor=r[1],action=r[2],details=json.loads(r[3])) for r in db.execute('SELECT at,actor,action,details FROM workflow_audit ORDER BY id DESC LIMIT 80')]
    return {'cases':cases,'audit':audit,'standards':state.get('standardsOverride',{}),'note':'Additional engagements are metadata-only demo shells, not fabricated tax returns.'}
