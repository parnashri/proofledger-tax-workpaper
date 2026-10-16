"""Multi-case collaborative operational workspaces and encrypted evidence storage.
No invented tax computation is created for additional engagements.
"""
import base64
import hashlib
import json
import secrets
from datetime import datetime,timezone
from cryptography.fernet import Fernet, InvalidToken

MAX_FILE_BYTES=1_000_000
ALLOWED_MIME={'application/pdf','image/png','image/jpeg','text/plain','application/json'}

def now():return datetime.now(timezone.utc).isoformat()
def audit(db,actor,action,data):
    db.execute('INSERT INTO workflow_audit(at,actor,action,details) VALUES (?,?,?,?)',(now(),actor,action,json.dumps(data,ensure_ascii=False)))

def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS case_records (id TEXT PRIMARY KEY,case_id TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL, status TEXT NOT NULL,owner TEXT,deadline TEXT,hours REAL NOT NULL DEFAULT 0,created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1)')
    db.execute('CREATE INDEX IF NOT EXISTS ix_case_records ON case_records(case_id,kind,status)')
    db.execute('CREATE TABLE IF NOT EXISTS case_evidence (id TEXT PRIMARY KEY,case_id TEXT NOT NULL,filename TEXT NOT NULL,mimetype TEXT NOT NULL, byte_len INTEGER NOT NULL, sha256 TEXT NOT NULL,ciphertext BLOB NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS ix_case_evidence ON case_evidence(case_id)')
    db.execute('CREATE TABLE IF NOT EXISTS case_access(case_id TEXT NOT NULL,staff_id TEXT NOT NULL,access TEXT NOT NULL,PRIMARY KEY(case_id,staff_id))')

def case(db,cid):
    row=db.execute('SELECT case_id,client_label,tax_year,status,owner,due,hours_budget,source FROM firm_cases WHERE case_id=?',(cid,)).fetchone()
    if not row:raise ValueError('Unknown engagement')
    return dict(zip(('case_id','client_label','tax_year','status','owner','due','hours_budget','source'),row))

def require_case(db,cid,staff,write=False):
    c=case(db,cid)
    role=staff['role'];id=staff['id']
    allowed=role in ('partner','firm_administrator') or c['owner']==id
    member=db.execute('SELECT access FROM case_access WHERE case_id=? AND staff_id=?',(cid,id)).fetchone()
    if member and (member[0]=='editor' or not write): allowed=True
    if not allowed: raise PermissionError('Not assigned to this engagement')
    if write and role in ('firm_administrator','quality_reviewer'):raise PermissionError('This role cannot edit engagement workpapers')
    return c

def set_member(db,cid,actor,staff_id,access,staff_ids):
    case(db,cid)
    if staff_id not in staff_ids or access not in ('viewer','editor','remove'):raise ValueError('Invalid staff member or access')
    if access=='remove':db.execute('DELETE FROM case_access WHERE case_id=? AND staff_id=?',(cid,staff_id))
    else:db.execute('INSERT INTO case_access VALUES(?,?,?) ON CONFLICT(case_id,staff_id) DO UPDATE SET access=excluded.access',(cid,staff_id,access))
    audit(db,actor,'case_access_updated',{'case_id':cid,'staff_id':staff_id,'access':access})
    return {'ok':True}

def workspace(db,cid,staff):
    c=require_case(db,cid,staff)
    rows=db.execute('SELECT id,kind,title,body,status,owner,deadline,hours,created_by,created_at,updated_at,revision FROM case_records WHERE case_id=? ORDER BY created_at DESC',(cid,)).fetchall()
    names=('id','kind','title','body','status','owner','deadline','hours','created_by','created_at','updated_at','revision')
    docs=db.execute('SELECT id,filename,mimetype,byte_len,sha256,created_by,created_at FROM case_evidence WHERE case_id=? ORDER BY created_at DESC',(cid,)).fetchall()
    names2=('id','filename','mimetype','byte_len','sha256','created_by','created_at')
    access=[dict(staff_id=r[0],access=r[1]) for r in db.execute('SELECT staff_id,access FROM case_access WHERE case_id=?',(cid,))]
    records=[dict(zip(names,r)) for r in rows]
    hours=round(sum(x['hours'] for x in records if x['kind']=='time'),2)
    return {'case':c,'records':records,'evidence':[dict(zip(names2,r)) for r in docs],'members':access,'hours_logged':hours,'budget_remaining':round(c['hours_budget']-hours,2),'read_only':staff['role'] in ('firm_administrator','quality_reviewer')}

def add_record(db,cid,staff,info):
    require_case(db,cid,staff,write=True)
    kind=str(info.get('kind',''));title=str(info.get('title','')).strip();body=str(info.get('body','')).strip()
    if kind not in ('task','note','decision','time','review'):raise ValueError('Record must be task, note, decision, review, or time')
    if not 3<=len(title)<=150 or len(body)>4000:raise ValueError('Title/body invalid')
    status=str(info.get('status','open'))
    if status not in ('open','in_progress','blocked','resolved','done'):raise ValueError('Invalid record status')
    hours=float(info.get('hours',0))
    if not 0<=hours<=24 or (kind=='time' and hours==0):raise ValueError('Time entry must be between 0 and 24 hours')
    if kind!='time' and hours:raise ValueError('Hours are only permitted for time entries')
    owner=str(info.get('owner') or staff['id']);due=str(info.get('deadline',''))[:30]
    rid='cr-'+secrets.token_hex(7);stamp=now()
    db.execute('INSERT INTO case_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,cid,kind,title,body,status,owner,due,hours,staff['id'],stamp,stamp,1))
    audit(db,staff['id'],'case_record_added',{'case_id':cid,'record_id':rid,'kind':kind})
    return {'id':rid,'revision':1}

def update_record(db,cid,staff,info):
    require_case(db,cid,staff,write=True)
    rid=str(info.get('id',''));revision=int(info.get('revision',-1));status=str(info.get('status',''))
    if status not in ('open','in_progress','blocked','resolved','done'):raise ValueError('Invalid status')
    old=db.execute('SELECT revision,kind FROM case_records WHERE id=? AND case_id=?',(rid,cid)).fetchone()
    if not old:raise ValueError('Record not found')
    if old[1]=='time':raise PermissionError('Time log entries are immutable; add a correcting entry')
    if old[0]!=revision:raise RuntimeError('Another staff member updated this record. Refresh before retrying.')
    db.execute('UPDATE case_records SET status=?,revision=revision+1,updated_at=? WHERE id=?',(status,now(),rid))
    audit(db,staff['id'],'case_record_status',{'case_id':cid,'record_id':rid,'status':status})
    return {'revision':revision+1}

def key_from_env():
    import os
    raw=os.getenv('PROOFLEDGER_EVIDENCE_KEY','').encode()
    if not raw:raise PermissionError('Encrypted uploads disabled: set PROOFLEDGER_EVIDENCE_KEY to a Fernet key')
    try:return Fernet(raw)
    except Exception:raise PermissionError('PROOFLEDGER_EVIDENCE_KEY is not a valid Fernet key')

def upload(db,cid,staff,info):
    require_case(db,cid,staff,write=True)
    fernet=key_from_env()
    name=str(info.get('filename','')).strip();mime=str(info.get('mimetype',''));data=info.get('base64','')
    if not name or len(name)>150 or '/' in name or '\\' in name:raise ValueError('Invalid filename')
    if mime not in ALLOWED_MIME:raise ValueError('Only PDF, JPEG, PNG, TXT and JSON are supported')
    if not isinstance(data,str) or len(data)>MAX_FILE_BYTES*2:raise ValueError('Evidence size exceeded')
    try:raw=base64.b64decode(data,validate=True)
    except Exception:raise ValueError('Evidence must be valid base64')
    if not raw or len(raw)>MAX_FILE_BYTES:raise ValueError('Evidence must contain 1 to 1,000,000 bytes')
    if mime=='application/pdf' and not raw.startswith(b'%PDF'):raise ValueError('File content does not match PDF MIME')
    if mime=='image/png' and not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('File content does not match PNG MIME')
    if mime=='image/jpeg' and not raw.startswith(b'\xff\xd8\xff'):raise ValueError('File content does not match JPEG MIME')
    eid='ce-'+secrets.token_hex(8)
    h=hashlib.sha256(raw).hexdigest()
    db.execute('INSERT INTO case_evidence VALUES (?,?,?,?,?,?,?,?,?)',(eid,cid,name,mime,len(raw),h,fernet.encrypt(raw),staff['id'],now()))
    audit(db,staff['id'],'case_evidence_uploaded',{'case_id':cid,'document_id':eid,'sha256':h})
    return {'id':eid,'sha256':h}

def download(db,cid,staff,eid):
    require_case(db,cid,staff)
    if not staff['sensitive_data_clearance']:raise PermissionError('Evidence download requires sensitive data clearance')
    r=db.execute('SELECT filename,mimetype,sha256,ciphertext FROM case_evidence WHERE id=? AND case_id=?',(eid,cid)).fetchone()
    if not r:raise ValueError('Document not found')
    try:raw=key_from_env().decrypt(r[3])
    except InvalidToken:raise PermissionError('Encrypted evidence could not be verified')
    if not hmac_compare(hashlib.sha256(raw).hexdigest(),r[2]):raise PermissionError('Evidence checksum mismatch')
    audit(db,staff['id'],'case_evidence_download',{'case_id':cid,'document_id':eid})
    return {'filename':r[0],'mimetype':r[1],'sha256':r[2],'base64':base64.b64encode(raw).decode()}

def hmac_compare(a,b):
    import hmac
    return hmac.compare_digest(a,b)
