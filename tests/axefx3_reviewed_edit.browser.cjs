// Shipped shared GUI with mocked HTTP only. No MIDI, AI, accounts or real SET.
const {chromium}=require(process.env.TC_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.TC_BROWSER_EXECUTABLE?{executablePath:process.env.TC_BROWSER_EXECUTABLE}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],posts=[],sweeps=[];
  let pending=null,sets=0,hold=null,preparing=false;
  const values={DISTORT_DRIVE:3,DISTORT_MID:5};
  const device={active:'axefx3',selected:'axefx3',label:'Fractal Axe-Fx III',ambiguous:false,
   axefx3:{chassis:'mk2',preset_count:1024,declared:true,read_only:true},
   detected:[{kind:'axefx3'}],available:[{kind:'axefx3',label:'Fractal Axe-Fx III'}]};
  const snapshot=()=>({connected:true,read_only:true,navigation_read_only:true,device,firmware:'33.00',
   read_only_reason:'General controls remain read-only.',preset:{number:320,editor:320,name:'Synthetic fixture'},scene:{number:1,name:'Scene 1'},
   scenes:Array.from({length:8},(_,i)=>({number:i+1,name:'Scene '+(i+1)})),
   blocks:[{effect_id:58,label:'Amp 1',family:'DISTORT',instance:1,channel:'A',bypassed:false}],
   values:{},params:{},mods:[],cab_sel:null,gig_mode:false});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),asset=url.pathname.split('/').pop();
   if(url.origin!=='http://127.0.0.1:8909')return route.abort();
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../ui/index.html'),'utf8')});
   if(url.pathname==='/axefx3-reviewed-edit.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(__dirname,'../ui/axefx3-reviewed-edit.js'),'utf8')});
   if(url.pathname.startsWith('/language/'))return route.fulfill({contentType:asset.endsWith('.js')?'text/javascript':'application/json',body:fs.readFileSync(path.join(__dirname,'../ui/languages',asset))});
   if(url.pathname==='/api/state')return route.fulfill({json:snapshot()});
   if(url.pathname==='/api/device')return route.fulfill({json:device});
   if(url.pathname==='/api/axefx3/edit/state')return route.fulfill({json:{configured:true,available:true,preset:320,scene:1,values:{...values},stored:false}});
   if(url.pathname==='/api/shared/sweep'){sweeps.push(req.method());return route.fulfill({status:409,json:{error:'No III sweep'}});}
   if(url.pathname.startsWith('/api/axefx3/edit/')){
    assert.equal(req.method(),'POST');const op=asset,body=req.postDataJSON()||{};posts.push({op,body});
    if(op==='discard'){pending=null;return route.fulfill({json:{stage:'request',can_send:false,stored:false}});}
    if(op==='prepare'){
     preparing=true;if(hold)await hold;
     assert.equal(body.expected_preset,320);assert.equal(body.expected_scene,1);assert.equal(body.whole_rig,false);
     assert.equal(body.actions.length,1);const action=body.actions[0];
     pending={token:'synthetic-ticket',plan_digest:'synthetic-digest',actions:[{...action,reason:''}],expected_preset:320,expected_scene:1,stage:'plan',
      change:{preset:320,effect_id:58,channel:'A',before:values[action.param],after:action.value,executable:false},stored:false,undo_available:false,can_send:false};
     return route.fulfill({json:{...pending,afx3_edit:true,summary:'One synthetic reviewed edit.',device:{preset:{number:320,name:''},scene:{number:1}},values:{[action.param]:values[action.param]}}});
    }
    assert(pending);assert.equal(body.token,pending.token);assert.equal(body.plan_digest,pending.plan_digest);
    assert.deepEqual(body.actions,pending.actions);assert.equal(body.expected_preset,320);assert.equal(body.expected_scene,1);
    if(op==='review'){assert.equal(pending.stage,'plan');pending.stage='review';return route.fulfill({json:pending});}
    assert.equal(body.target_confirmed,true);assert.equal(body.external_audio_muted,true);
    if(op==='confirm'){assert.equal(pending.stage,'review');pending.stage='confirm';return route.fulfill({json:{...pending,can_send:true}});}
    assert.equal(op,'send');assert.equal(pending.stage,'confirm');sets++;const action=pending.actions[0];values[action.param]=action.value;pending=null;
    return route.fulfill({json:{verified:true,sent:true,stored:false,undo_available:false,health:[],stage:'sent',results:[{action,ok:true,detail:'Synthetic verified edit; not stored.'}]}});
   }
   if(req.method()!=='GET')throw new Error('Unexpected non-experimental write: '+url.pathname);
   if(url.pathname.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:''});
   if(url.pathname==='/api/presets')return route.fulfill({json:{slots:[]}});
   if(url.pathname==='/api/ai/status')return route.fulfill({json:{ready:false,backends:[]}});
   if(url.pathname==='/api/version')return route.fulfill({json:{version:'1.6.2',label:'1.6.2'}});
   return route.fulfill({json:{}});
  });
  await page.goto('http://127.0.0.1:8909/');await page.evaluate(()=>TCLanguage.ready);
  await page.evaluate(()=>openDrawer('devices'));await page.locator('#afx3prepare:not([disabled])').waitFor();
  await page.fill('#afx3value','3.3');await page.click('#afx3prepare');await page.waitForFunction(()=>stage==='plan');
  assert.equal(sets,0);assert.deepEqual(sweeps,[]);
  await page.click('#reviewbtn');await page.waitForFunction(()=>stage==='review');
  await page.click('#toconfirm');await page.waitForFunction(()=>stage==='confirm');
  assert(await page.locator('#afx3mutewrap').isVisible());assert(await page.locator('#armbtn').isDisabled());
  await page.check('#ack');assert(await page.locator('#armbtn').isDisabled());
  await page.check('#afx3muted');await page.click('#armbtn');await page.locator('#apply').waitFor({state:'visible'});
  assert.equal(sets,0);await page.click('#apply');await page.waitForFunction(()=>stageDone.send===true);
  assert.equal(sets,1);assert(await page.locator('#storeafter').isHidden());
  assert.match(await page.textContent('#sendphase'),/Axe-Fx III edit verified/);
  assert.deepEqual(sweeps,[]);
  page.once('dialog',d=>d.accept());await page.click('#newrequest');await page.waitForFunction(()=>stage==='request'&&currentPlan===null);
  await page.evaluate(()=>openDrawer('devices'));await page.selectOption('#afx3control','DISTORT_MID');await page.fill('#afx3value','5.6');
  let release;hold=new Promise(resolve=>release=resolve);preparing=false;
  await page.click('#afx3prepare');await page.waitForFunction(()=>AFX3ReviewedEdit.working());
  assert(await page.locator('#newdesign').isDisabled());assert.equal(await page.evaluate(()=>startNewDesign()),false);
  release();hold=null;await page.waitForFunction(()=>stage==='plan');
  await page.click('#discard');await page.waitForFunction(()=>stage==='request'&&currentPlan===null);
  assert.equal(sets,1);assert.deepEqual(sweeps,[]);assert.equal(preparing,true);
  assert.deepEqual(errors,[]);assert.equal(posts.filter(p=>p.op==='send').length,1);
  console.log('PASS: shared reviewed-edit Chrome flow, explicit review/two consents/click SEND, no III sweep/Store, one simulated SET and in-flight New Design guard.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
