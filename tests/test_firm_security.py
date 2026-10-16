#!/usr/bin/env python3
"""End-to-end tests for workspace strict logins, multi-case access, encrypted evidence,
revoked client sessions and filing authorization receipt. Creates its OWN DB/server.
"""
from pathlib import Path
import base64,hashlib,http.cookiejar,json,os,socket,subprocess,sys,tempfile,time,urllib.error,urllib.request
from cryptography.fernet import Fernet
ROOT=Path(__file__).resolve().parents[1]
count=0

def check(cond,text):
 global count
 assert cond,text
 count+=1;print(f'PASS {count:02} · {text}')

class Browser:
 def __init__(self,url):
  self.url=url;self.jar=http.cookiejar.CookieJar();self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
 def call(self,path,data=None):
  req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
  try:
   with self.opener.open(req,timeout=10) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:
   try:payload=json.load(e)
   except:payload={'error':e.reason}
   return e.code,payload
 def login(self,id,pwd,otp=''):return self.call('/api/login',{'staff_id':id,'password':pwd,'otp':otp})

with tempfile.TemporaryDirectory() as tmp:
 db=Path(tmp)/'testing.sqlite3'
 env={**os.environ,'PROOFLEDGER_DB':str(db),'PROOFLEDGER_STRICT_AUTH':'1','PROOFLEDGER_EVIDENCE_KEY':Fernet.generate_key().decode()}
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 # Provision credentials while offline, then start strict-only application.
 setup='import server,security as s\nwith server.conn() as c:\n s.provision(c,"st-01","PreparerPassword!2026")\n s.provision(c,"st-02","ReviewerPassword!2026")\n s.provision(c,"st-03","PartnerPassword!2026")\n s.provision(c,"st-05","AdministratorPassword!2026")\n'
 subprocess.run([sys.executable,'-c',setup],env=env,cwd=ROOT,check=True,capture_output=True)
 process=subprocess.Popen([sys.executable,'server.py','--port',str(port)],env=env,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 try:
  url=f'http://127.0.0.1:{port}'
  for i in range(60):
   try:urllib.request.urlopen(url+'/api/session',timeout=.6)
   except urllib.error.HTTPError as e:
    if e.code==401:break
   except Exception:time.sleep(.1)
  pre=Browser(url);admin=Browser(url);partner=Browser(url);reviewer=Browser(url);stranger=Browser(url)
  check(pre.login('st-01','proofledger-demo')[0]==403,'Shared demo password disabled in strict mode')
  check(pre.login('st-01','Wrong passphrase')[0]==403,'Incorrect personal password rejected')
  check(pre.login('st-01','PreparerPassword!2026')[0]==200,'Individual preparer account authenticates')
  check(admin.login('st-05','AdministratorPassword!2026')[0]==200,'Individual administrator account authenticates')
  check(partner.login('st-03','PartnerPassword!2026')[0]==200,'Individual partner account authenticates')
  check(reviewer.login('st-02','ReviewerPassword!2026')[0]==200,'Individual reviewer account authenticates')
  check(pre.call('/api/workspace/security')[1]['strict_auth'],'App reports enabled strict mode')
  sys.path.insert(0,str(ROOT))
  import security as sec
  import sqlite3
  with sqlite3.connect(db) as dbc:
   secret=sec.provision(dbc,'st-04','SpecialPasswordForMfa!2026',totp=True)
  from math import floor
  valid_code=sec.otp_code(secret,int(time.time()//30))
  check(sec.verify_otp(secret,valid_code),'TOTP validates a correct current authenticator code')
  check(not sec.verify_otp(secret,'000000') or valid_code=='000000','Wrong authenticator codes are rejected')
  check(stranger.login('st-04','SpecialPasswordForMfa!2026','111111')[0]==403,'Valid password without correct MFA is rejected')
  check(stranger.login('st-04','SpecialPasswordForMfa!2026',valid_code)[0]==200,'Staff account with TOTP can sign in')
  st,r=admin.call('/api/workflow/firm/create',{'client_label':'Additional case with operational records','tax_year':2026,'owner':'st-01','hours_budget':12})
  check(st==200,'Administrator provisions secondary engagement')
  cid=r['case_id'];check(pre.call('/api/workspace/detail?case_id='+cid)[0]==200,'Assigned preparer can view new case')
  check(reviewer.call('/api/workspace/detail?case_id='+cid)[0]==403,'Unassigned reviewer cannot read case')
  check(reviewer.call('/api/workspace/case/record',{'case_id':cid,'kind':'note','title':'Unauthorized record'})[0]==403,'Unassigned reviewer cannot edit case')
  check(admin.call('/api/workspace/case/member',{'case_id':cid,'staff_id':'st-02','access':'viewer'})[0]==200,'Admin grants individual case read access')
  check(reviewer.call('/api/workspace/detail?case_id='+cid)[0]==200,'Authorized reviewer now can read case')
  check(reviewer.call('/api/workspace/case/record',{'case_id':cid,'kind':'note','title':'Unauthorized record'})[0]==403,'Viewer cannot write case')
  check(partner.call('/api/workspace/case/member',{'case_id':cid,'staff_id':'st-02','access':'editor'})[0]==200,'Partner promotes reviewer to case editor')
  st,r=reviewer.call('/api/workspace/case/record',{'case_id':cid,'kind':'task','title':'Check basis packet','body':'Compare filed year balances to prior-year support','owner':'st-02','deadline':'2026-12-14'})
  check(st==200,'Reviewer creates persistent case task')
  rid=r['id'];check(reviewer.call('/api/workspace/case/status',{'case_id':cid,'id':rid,'revision':1,'status':'resolved'})[0]==200,'Case task status revision accepted')
  check(reviewer.call('/api/workspace/case/status',{'case_id':cid,'id':rid,'revision':1,'status':'done'})[0]==409,'Concurrent stale task edit blocked')
  # 500 on RuntimeError prior to handler mapping is functional rejection, but improve to 409 later.
  st,r=pre.call('/api/workspace/case/record',{'case_id':cid,'kind':'time','title':'Records review','hours':2.25,'body':'Verified filing evidence'})
  check(st==200,'Time entry recorded')
  check(pre.call('/api/workspace/detail?case_id='+cid)[1]['hours_logged']==2.25,'Time budget computed from actual case entries')
  raw=b'%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF';h=hashlib.sha256(raw).hexdigest()
  st,r=pre.call('/api/workspace/case/evidence',{'case_id':cid,'filename':'support.pdf','mimetype':'application/pdf','base64':base64.b64encode(raw).decode()})
  check(st==200 and r['sha256']==h,'PDF encrypted with its SHA256 fingerprint')
  eid=r['id'];check(reviewer.call('/api/workspace/case/evidence?case_id='+cid+'&id='+eid)[0]==200,'Cleared assigned reviewer can retrieve evidence')
  st,doc=pre.call('/api/workspace/case/evidence?case_id='+cid+'&id='+eid)
  check(st==200 and base64.b64decode(doc['base64'])==raw,'Evidence decrypts to original identical bytes')
  check(admin.call('/api/workspace/case/evidence',{'case_id':cid,'filename':'x.txt','mimetype':'text/plain','base64':'eA=='})[0]==403,'Firm administrator cannot alter client case evidence')
  with __import__('sqlite3').connect(db) as c:
   cipher=c.execute('SELECT ciphertext FROM case_evidence WHERE id=?',(eid,)).fetchone()[0]
  check(raw not in cipher,'SQLite stores evidence ciphertext, not plaintext file')
  inv=partner.call('/api/workflow/invites',{'client_id':'cu-01'})[1]
  client=Browser(url)
  check(client.call('/api/workflow/client/redeem',{'client_id':'cu-01','invite_code':inv['invite_code']})[0]==200,'Client redeems invitation')
  check(client.call('/api/workflow/client/home')[0]==200,'Client portal works before revocation')
  inv_id=next(x['id'] for x in partner.call('/api/workflow/people')[1]['invitations'] if x['client_id']=='cu-01')
  check(partner.call('/api/workspace/client/revoke',{'invite_id':inv_id})[0]==200,'Partner revokes invitation')
  check(client.call('/api/workflow/client/home')[0]==401,'Revocation invalidates existing client sessions')
  check(client.call('/api/workflow/client/redeem',{'client_id':'cu-01','invite_code':inv['invite_code']})[0]==403,'Revoked invitation cannot be reused')
  st,receipt=partner.call('/api/workspace/filing/receipt')
  check(st==200 and receipt['legally_binding_signature'] is False,'Receipt clearly disclaims certified e-signature')
  check('receipt_sha256' in receipt and receipt['freeze'] is None,'Audit receipt has deterministic hash even before filing')
  check(admin.call('/api/workspace/case/member',{'case_id':cid,'staff_id':'st-02','access':'remove'})[0]==200,'Administrator revokes case membership')
  check(reviewer.call('/api/workspace/detail?case_id='+cid)[0]==403,'Revoked case membership blocks access immediately')
  print('ALL',count,'Workspace ASSERTIONS PASSED')
 finally:
  process.terminate();process.wait(timeout=5)
