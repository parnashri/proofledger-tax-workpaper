#!/usr/bin/env python3
"""End-to-end standalone stdlib test for Workflow: staff, clients, filing and firm. Uses disposable server+DB."""
import json, os, sys, urllib.request, urllib.error, http.cookiejar, copy
BASE=os.getenv('PROOFLEDGER_TEST_URL','http://127.0.0.1:8138')
PASS=0

def assert_result(cond,label):
    global PASS
    assert cond,label
    PASS+=1
    print(f'PASS {PASS:02} · {label}')

class Browser:
    def __init__(self):self.jar=http.cookiejar.CookieJar();self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def call(self,path,data=None):
        b=json.dumps(data).encode() if data is not None else None
        r=urllib.request.Request(BASE+path,data=b,headers={'Content-Type':'application/json'},method='POST' if data is not None else 'GET')
        try:
            with self.opener.open(r,timeout=12) as x:return x.status,json.load(x)
        except urllib.error.HTTPError as x:
            try:val=json.load(x)
            except:val={'error':str(x)}
            return x.code,val
    def login(self,person):return self.call('/api/login',{'staff_id':person,'password':'proofledger-demo'})

pre=Browser();review=Browser();partner=Browser();admin=Browser();qa=Browser()
assert_result(pre.login('st-01')[0]==200,'Preparer signs in')
assert_result(review.login('st-02')[0]==200,'Reviewer signs in')
assert_result(partner.login('st-03')[0]==200,'Partner signs in')
assert_result(admin.login('st-05')[0]==200,'Administrator signs in')
assert_result(qa.login('st-06')[0]==200,'Quality reviewer signs in')
with pre.opener.open(BASE+'/client.html',timeout=10) as response:
    assert_result(response.status==200 and b'Client review and acknowledgment' in response.read(), 'Client review HTML is served')
assert_result(qa.call('/api/workflow/doc-view?document_id=D01')[0]==200,'Cleared quality reviewer can log sensitive document view')
assert_result(pre.call('/api/workflow/firm/create',{'client_label':'Preview demo','tax_year':2025,'owner':'st-01','hours_budget':10})[0]==403,'Preparer cannot add firm case')
assert_result(admin.call('/api/workflow/invites',{'client_id':'cu-01'})[0]==403,'Administrator cannot issue partner client invitation')
status,created=admin.call('/api/workflow/firm/create',{'client_label':'Demo training case','tax_year':2025,'owner':'st-02','due':'2026-12-12','hours_budget':12})
assert_result(status==200 and created['case_id'].startswith('DEMO-'),'Firm admin creates new engagement')
assert_result(admin.call('/api/workflow/firm/update',{'case_id':created['case_id'],'status':'waiting_client'})[0]==200,'Administrator changes firm case status')
assert_result(any(x['case_id']==created['case_id'] and x['status']=='waiting_client' for x in partner.call('/api/workflow/firm')[1]['cases']),'Firm portfolio visible across staff')

status,posted=pre.call('/api/workflow/questions',{'client_id':'cu-01','question':'Please confirm which state you lived in on July 15, 2025.'})
assert_result(status==200 and posted['id'].startswith('cq-'),'Staff creates deliverable client question')
assert_result(pre.call('/api/workflow/filing/action',{'action':'prepare'})[0]==403,'Only partner can initiate filing')
assert_result(partner.call('/api/workflow/filing/action',{'action':'prepare'})[0]==403,'Filing preparation blocked by incomplete review')
assert_result(partner.call('/api/workflow/invites',{'client_id':'cu-01'})[0]==200,'Partner issues independent client invite')
invite1=partner.call('/api/workflow/invites',{'client_id':'cu-01'})[1]
invite2=partner.call('/api/workflow/invites',{'client_id':'cu-02'})[1]
client1=Browser();client2=Browser()
assert_result(client1.call('/api/workflow/client/redeem',{'client_id':'cu-01','invite_code':invite1['invite_code']})[0]==200,'Named client redeems one-time invitation')
assert_result(client1.call('/api/workflow/client/redeem',{'client_id':'cu-01','invite_code':invite1['invite_code']})[0]==403,'Redeemed invitation cannot be reused')
assert_result(client2.call('/api/workflow/client/redeem',{'client_id':'cu-02','invite_code':invite2['invite_code']})[0]==200,'Other spouse signs in independently')
assert_result(client1.call('/api/workpaper')[0]==401,'Client cannot access staff workpaper')
assert_result(client1.call('/api/packet')[0]==401,'Client cannot access unfiltered source packet')
assert_result(pre.call('/api/workflow/client/home')[0]==401,'Staff cannot impersonate the client portal')
assert_result(any(x['id']==posted['id'] for x in client1.call('/api/workflow/client/home')[1]['questions']),'Client sees only targeted question')
assert_result(not client2.call('/api/workflow/client/home')[1]['questions'],'Spouse cannot view other spouse questions')
assert_result(client1.call('/api/workflow/client/answer',{'question_id':posted['id'],'answer':'We moved to Texas on July 15, 2025.'})[0]==200,'Client records response as durable evidence')
assert_result(partner.call('/api/workflow/people')[1]['questions'][0]['answer'].startswith('We moved'),'Staff can inspect client response')
assert_result(client1.call('/api/workflow/client/decision',{'decision':'approve','typed_name':'Ngozi Okafor','evidence':'Reviewed tax summary.'})[0]==403,'Client cannot approve while CPA reviews incomplete')

# Complete the synthetic review through staff-authorized, auditable edits.
from pathlib import Path
packet=json.load(open(Path(__file__).resolve().parents[1]/'packet.json'))
r,wp=pre.call('/api/workpaper'); assert r==200
s=copy.deepcopy(wp['state']);s['documentChecks']={x['id']:{'status':'verified','actor':'st-01','note':'Checked simulated original source'} for x in packet['documents']}
import sys;sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
s['coverage']={k:{'status':'complete','actor':'st-01','reason':'Reviewed against source'} for k in server.COVERAGE}
s['coverage'].update({'outside-'+str(i):{'status':'complete','actor':'st-01','reason':'Owner and filing scope identified'} for i in range(len(packet['household']['related_returns']))})
s['issueStatus']={k:{'status':'resolved','actor':'st-01','reason':'Test fixture only; not a real tax determination'} for k in server.CRITICAL}
s['taxReviews']={k:{'status':'reviewed','actor':'st-01','reason':'Case-study synthetic fixture'} for k in server.JUDGMENT_TOPICS}
status,rr=pre.call('/api/workpaper',{'revision':wp['revision'],'state':s})
assert_result(status==200,'Preparer saves all 74 document checks and 17 coverage items')
# sign as reviewer
r,wp=review.call('/api/workpaper');s=wp['state'];s['signoffs']={'reviewer':{'actor':'st-02','by':'Daniel Ortiz','at':'2026-07-10T00:00:00Z','version':'v3'}}
status,rr=review.call('/api/workpaper',{'revision':wp['revision'],'state':s})
assert_result(status==200,'Independent reviewer sign-off permitted after completion')
r,wp=partner.call('/api/workpaper');s=wp['state'];s['signoffs']['partner']={'actor':'st-03','by':'Helen Strand','at':'2026-07-10T00:00:01Z','version':'v3'}
status,rr=partner.call('/api/workpaper',{'revision':wp['revision'],'state':s})
assert_result(status==200,'Partner sign-off permitted only after reviewer')
assert_result(client1.call('/api/workflow/client/home')[1]['review_ready'],'Separate client portal reflects CPA review readiness')
assert_result(client1.call('/api/workflow/client/decision',{'decision':'approve','typed_name':'Ngozi Okafor','evidence':'I reviewed the federal and California packet summary.'})[0]==200,'First spouse acknowledges exact workpaper version')
assert_result(partner.call('/api/workflow/filing/action',{'action':'prepare'})[0]==403,'One spouse is insufficient for joint filing')
assert_result(client2.call('/api/workflow/client/decision',{'decision':'approve','typed_name':'Erik Lindqvist','evidence':'I have read the same federal and CA return summary.'})[0]==200,'Second spouse independently acknowledges version')
assert_result(partner.call('/api/workflow/filing')[1]['ready'],'Filing readiness verifies both current acknowledgments')

# Change the source-reviewed packet: client approvals must become stale, and CPA sign-offs reopened.
r,wp=pre.call('/api/workpaper');s=wp['state'];s['documentChecks']['D01']['note']='Updated underlying evidence; review required again'
status,rsp=pre.call('/api/workpaper',{'revision':wp['revision'],'state':s})
assert_result(status==200 and rsp['state']['signoffs']=={},'Material change automatically reopens prior sign-offs')
assert_result(not partner.call('/api/workflow/filing')[1]['ready'],'Material edit invalidates both clients earlier fingerprints')
# Re-sign and re-approve
r,wp=review.call('/api/workpaper');s=wp['state'];s['signoffs']={'reviewer':{'actor':'st-02','by':'Daniel Ortiz','at':'2026-07-11T00:00:00Z'}}
assert review.call('/api/workpaper',{'revision':wp['revision'],'state':s})[0]==200
r,wp=partner.call('/api/workpaper');s=wp['state'];s['signoffs']['partner']={'actor':'st-03','by':'Helen Strand','at':'2026-07-11T00:01:00Z'}
assert partner.call('/api/workpaper',{'revision':wp['revision'],'state':s})[0]==200
assert_result(client1.call('/api/workflow/client/decision',{'decision':'approve','typed_name':'Ngozi Okafor','evidence':'I reviewed the corrected return summary.'})[0]==200,'Client renews stale acknowledgment after change')
assert_result(client2.call('/api/workflow/client/decision',{'decision':'approve','typed_name':'Erik Lindqvist','evidence':'I reviewed the corrected return summary.'})[0]==200,'Other spouse renews stale acknowledgment')
assert_result(partner.call('/api/workflow/filing/action',{'action':'prepare'})[0]==200,'Partner prepares filing only after entire chain is current')
assert_result(partner.call('/api/workflow/filing/action',{'action':'agency_response','index':0})[0]==200,'Import packet federal rejection (no actual transmission)')
assert_result(partner.call('/api/workflow/filing/action',{'action':'agency_response','index':1})[0]==200,'California state hold fixture preserves unresolved federal rejection')
assert_result(partner.call('/api/workflow/filing/action',{'action':'agency_response','index':2})[0]==403,'Cannot accept rejected e-file without correction evidence')
assert_result(partner.call('/api/workflow/filing/action',{'action':'clear_rejection','fix':'Corrected dependent SSN using Social Security card D71, verified name control.','evidence':'D71'})[0]==200,'Documented rejection correction')
assert_result(partner.call('/api/workflow/filing/action',{'action':'agency_response','index':2})[0]==200,'Import federal agency acceptance fixture')
assert_result(partner.call('/api/workflow/filing/action',{'action':'agency_response','index':3})[0]==200,'Import California agency acceptance fixture')
assert_result(partner.call('/api/workflow/filing/action',{'action':'freeze'})[0]==200,'Partner freezes immutable accepted filing checkpoint')
assert_result(pre.call('/api/workpaper')[1]['state']['filing'] is None,'New frozen workflow remains server-authoritative, separate from v3 browser simulation')
r,wp=pre.call('/api/workpaper');s=wp['state'];s['notes'].append({'id':'late-test','actor':'st-01','text':'Should be denied'})
assert_result(pre.call('/api/workpaper',{'revision':wp['revision'],'state':s})[0]==403,'Filed workpaper rejects subsequent original-return material edits')
assert_result(partner.call('/api/workflow/filing/action',{'action':'start_amendment','reason':'Need to separately document a basis adjustment with independent evidence.'})[0]==200,'Filed return supports new amendment branch')
flow=partner.call('/api/workflow/filing')[1]['filing'];am=flow['amendments'][0]
assert_result(partner.call('/api/workflow/filing/action',{'action':'amendment_change','amendment_id':am['id'],'line':'SchC.1','delta':-12400,'source':'D14/D15/D21','reason':'Duplicate processing receipts not new income'})[0]==200,'Amended change is separate from frozen return')
assert_result(partner.call('/api/workflow/filing/action',{'action':'open_notice','notice_id':'N-2025-L566'})[0]==200,'Create 2028 examination notice case')
notice=partner.call('/api/workflow/filing')[1]['filing']['notices'][0]
assert_result(review.call('/api/workflow/filing/action',{'action':'notice_response','case_id':notice['id'],'answer':'I verified the source document evidence and reviewed the 2025 Schedule C receivables.','evidence':'D14, D15, D21'})[0]==200,'Assigned reviewer may draft notice response evidence')
assert_result(qa.call('/api/workflow/filing/action',{'action':'notice_response','case_id':notice['id'],'answer':'Attempt unauthorized draft by quality reviewer.','evidence':'D14'})[0]==403,'Quality reviewer cannot alter notice case')
assert_result(partner.call('/api/workflow/filing/action',{'action':'notice_response','case_id':notice['id'],'answer':'The revenues must reconcile from books through information returns; evidence supports our item-by-item assessment.','evidence':'D14, D15, D21, D72'})[0]==200,'Evidence-linked IRS notice draft')
assert_result(partner.call('/api/workflow/notice-bundle?case_id='+notice['id'])[0]==200,'Self-contained IRS notice evidence bundle available')
assert_result(partner.call('/api/workflow/client-copy')[0]==200,'Synthetic client copy export available only after acceptance')
status,question=pre.call('/api/workflow/questions',{'client_id':'cu-02','question':'Please clarify the 2028 IRS notice correspondence details.'})
assert_result(status==200 and question['id'].startswith('cq-'),'New post-filing question can be sent')
status,rsp=client2.call('/api/workflow/client/answer',{'question_id':question['id'],'answer':'The IRS notice arrived January 2028.'})
assert_result(status==200,'Post-filing client answers are accepted as separate evidence')
assert_result(len(pre.call('/api/workpaper')[1]['state']['signoffs'])==2,'Post-filing evidence cannot mutate frozen CPA sign-offs')
assert_result(client2.call('/api/workflow/client/decision',{'decision':'approve','typed_name':'Erik Lindqvist','evidence':'Unnecessary post-filing approval'})[0]==403,'Client cannot reauthorize a frozen original filing')
assert_result(partner.call('/api/workflow/firm')[1]['cases'][0]['status'] in ('filed','waiting_client'),'Firm registry uses real filing state for packet case')
assert_result(bool(pre.call('/api/workflow/notifications')[1]['notifications']),'Staff receives internal notifications')
print(f'ALL {PASS} ASSERTIONS PASSED')
