"""Mocked UI smoke for the Workspace additions (real HTTP tested in workflow_workspace_integration)."""
import json,re,pathlib
from playwright.sync_api import sync_playwright
ROOT=pathlib.Path(__file__).resolve().parents[1]
packet=json.loads((ROOT/'packet.json').read_text())
case={'case_id':'DEMO-042','client_label':'Test secondary case','tax_year':2026,'status':'in_review','owner':'st-03','hours_budget':12,'source':'registry_shell'}
workspace={'case':case,'records':[{'id':'cr-example','kind':'task','title':'Confirm the 2026 source packet','body':'Evidence expected','status':'open','owner':'st-03','deadline':'2026-12-15','hours':0,'created_by':'st-03','created_at':'2026-10-15','updated_at':'2026-10-15','revision':1}], 'evidence':[{'id':'ce-example','filename':'source.pdf','mimetype':'application/pdf','byte_len':500,'sha256':'1234abcdef','created_by':'st-03','created_at':'2026-10-15'}], 'members':[{'staff_id':'st-02','access':'editor'}], 'hours_logged':2.5,'budget_remaining':9.5,'read_only':False}
people={'invitations':[{'id':'i-2026','client_id':'cu-01','created_by':'st-03','created_at':'2026-10-15','expires':'2026-10-18','redeemed_at':None,'revoked_at':None}],'approvals':[],'questions':[],'required_client_ids':['cu-01','cu-02'],'staff_notifications':[],'fingerprint':'abc123'}
firm={'cases':[case],'audit':[]}
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1400,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 html=re.sub(r'<script src="[^"]+" defer></script>','',(ROOT/'index.html').read_text())
 page.set_content(html);page.add_style_tag(content=(ROOT/'static'/'style.css').read_text())
 page.evaluate('''({packet,workspace,people,firm})=>{
  const store={};Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>store[k]||null,setItem:(k,v)=>store[k]=v,removeItem:k=>delete store[k]}});
  window.scrollTo=()=>{};
  window.fetch=async(url,opt={})=>{
   const path=String(url);let val={ok:true};
   if(path==='/api/session')val={staff:{id:'st-03',name:'Helen Strand',role:'partner',sensitive_data_clearance:true}};
   else if(path==='/api/packet')val=packet;
   else if(path==='/api/workpaper')val={revision:0,state:{}};
   else if(path==='/api/workflow/firm')val=firm;
   else if(path==='/api/workflow/people')val=people;
   else if(path==='/api/workspace/detail?case_id=DEMO-042')val=workspace;
   else if(path==='/api/workspace/security')val={strict_auth:true,individual_credentials:true,mfa_enabled:true};
   else if(path==='/api/workflow/filing')val={filing:{status:'draft',events:[],jurisdictions:{},frozen:null,amendments:[],notices:[]},approvals:[],ready:false,blocker:'Review incomplete'};
   return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>val};
  }
 }''',{'packet':packet,'workspace':workspace,'people':people,'firm':firm})
 for name in ['session','app','enhancements','calculations','collaboration','judgments','planning','people_filing','firm_workflows']:
  page.add_script_tag(content=(ROOT/'static'/(name+'.js')).read_text())
 page.wait_for_timeout(700)
 for route,expected in [('engagement-workspace','Multi-engagement review workspace'),('access-audit','Review identity & authorization receipt')]:
  page.locator(f'button[data-route="{route}"]').first.click();page.wait_for_timeout(350)
  h1=page.locator('h1').first.inner_text()
  assert expected in h1,(route,h1)
  assert not errors,errors
  print('PASS',route,'navigation and render')
 page.locator('button[data-route="engagement-workspace"]').first.click();page.wait_for_timeout(450)
 assert page.locator('text=Confirm the 2026 source packet').count()>0
 assert page.locator('text=source.pdf').count()>0
 assert not errors,errors
 print('PASS secondary case tasks and encrypted-file metadata render')
 browser.close()
