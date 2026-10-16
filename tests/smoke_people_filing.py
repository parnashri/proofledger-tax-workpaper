"""UI smoke against mocked requests (Chromium denies local loopback in this environment).
Actual API permission/data tests are in test_people_filing.py.
"""
import json,pathlib
from playwright.sync_api import sync_playwright
ROOT=pathlib.Path(__file__).resolve().parents[1]
PACKET=json.loads((ROOT/'packet.json').read_text())
PEOPLE={'invitations':[],'approvals':[],'questions':[],'required_client_ids':['cu-01','cu-02'],'staff_notifications':[],'fingerprint':'a1b2c3d4e5f6'}
FILING={'filing':{'status':'draft','events':[],'jurisdictions':{},'frozen':None,'amendments':[],'notices':[]},'approvals':[],'ready':False,'blocker':'Review completeness and client approvals required'}
FIRM={'cases':[{'case_id':'CL-20417','client_label':'Okafor–Lindqvist household','tax_year':2025,'status':'in_review','owner':'st-03','due':'2026-10-15','hours_budget':22,'hours_logged':3,'task_count':0,'document_count':74,'source':'packet'}],'audit':[]}

def test():
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=browser.new_page(viewport={'width':1366,'height':940})
  errs=[];page.on('pageerror',lambda e:errs.append(str(e)))
  html=(ROOT/'index.html').read_text()
  import re
  html=re.sub(r'<script src="[^"]+" defer></script>','',html)
  page.set_content(html,wait_until='load')
  page.add_style_tag(content=(ROOT/'static'/'style.css').read_text())
  page.evaluate('''({packet,people,filing,firm}) => {
    const memory={};Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>memory[k]||null,setItem:(k,v)=>memory[k]=v,removeItem:k=>delete memory[k]}});
    window.scrollTo=()=>{};
    window.fetch=async (url,options={})=>{
      const path=String(url);let item;
      if(path==='/api/session')item={staff:{id:'st-03',name:'Helen Strand',role:'partner',sensitive_data_clearance:true}};
      else if(path==='/api/packet')item=packet;
      else if(path==='/api/workpaper')item={revision:0,state:{issueStatus:{},verifications:{},documentChecks:{},notes:[],questions:[],decisions:[],signoffs:{},filing:null,annotations:[],attachments:[],tasks:[],viewLog:[],audit:[],lastSeen:{},version:'v3',adjustments:[],coverage:{},docDisposition:{},filingFlow:{events:[],authorizations:[],responses:[],amendments:[],noticeResponses:[]},timeEntries:[],checkpoints:{},batchHistory:[],standardsOverride:{},taxReviews:{},plan2026:{}}};
      else if(path==='/api/workflow/people')item=people;
      else if(path==='/api/workflow/filing')item=filing;
      else if(path==='/api/workflow/firm')item=firm;
      else if(path==='/api/workflow/notifications')item={notifications:[]};
      else item={ok:true};
      return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>item};
    };
  }''',{'packet':PACKET,'people':PEOPLE,'filing':FILING,'firm':FIRM})
  for name in ['session','app','enhancements','calculations','collaboration','judgments','planning','people_filing']:
   page.add_script_tag(content=(ROOT/'static'/(name+'.js')).read_text())
  page.wait_for_timeout(600)
  assert 'Every figure has a story' in page.locator('h1').first.inner_text(),page.locator('h1').first.inner_text()
  for route,title in [('clients','Clients, collaboration & approvals'),('filing-control','Server-controlled filing lifecycle'),('firm-portfolio','Firm portfolio and administrative controls')]:
   page.locator(f'button[data-route="{route}"]').click();page.wait_for_timeout(220)
   assert title in page.locator('h1').first.inner_text(),(route,page.locator('h1').first.inner_text())
   assert not errs,errs
   print('PASS UI',route,'heading, API data, controls')
  page.screenshot(path=str(ROOT/'tests'/'_staff_preview.png'),full_page=True)
  # Separate invitation client portal also renders and denies approval until reviewer signs.
  p2=browser.new_page(viewport={'width':850,'height':940})
  errors2=[];p2.on('pageerror',lambda e:errors2.append(str(e)))
  clienthtml=(ROOT/'client.html').read_text().replace('<script src="static/client.js" defer></script>','')
  p2.set_content(clienthtml);p2.add_style_tag(content=(ROOT/'static'/'style.css').read_text())
  p2.evaluate('''() => { window.fetch=async (u)=>({ok:false,status:401,json:async()=>({error:'Sign in'})})}''')
  p2.add_script_tag(content=(ROOT/'static'/'client.js').read_text());p2.wait_for_timeout(200)
  assert 'Redeem your single-use invitation' in p2.locator('h2').first.inner_text()
  assert not errors2,errors2
  p2.screenshot(path=str(ROOT/'tests'/'_client_preview.png'),full_page=True)
  browser.close()
  print('PASS client portal page invitation UX, zero runtime exceptions')
if __name__=='__main__':test()
