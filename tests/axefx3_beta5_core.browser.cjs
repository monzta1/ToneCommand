// Actual shipped GUI with synthetic HTTP. No server, device, AI or accounts.
const {chromium}=require(process.env.TC_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.TC_BROWSER_EXECUTABLE?{executablePath:process.env.TC_BROWSER_EXECUTABLE}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[],posts=[];
  page.on('pageerror',e=>errors.push(e.message));
  let pending=false;
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),name=url.pathname.split('/').pop();
   if(url.pathname.startsWith('/language/'))return route.fulfill({contentType:name.endsWith('.json')?'application/json':'text/javascript',body:fs.readFileSync(path.join(root,'ui/languages',name))});
   if(url.pathname==='/logo.png')return route.fulfill({contentType:'image/png',body:fs.readFileSync(path.join(root,'ui/logo.png'))});
   if(url.pathname==='/axefx3.css')return route.fulfill({contentType:'text/css',body:fs.readFileSync(path.join(root,'ui/index.html'),'utf8').split('<style>')[1].split('</style>')[0]});
   if(url.pathname==='/axefx3'||url.pathname==='/axefx3.js')return route.fulfill({contentType:name.endsWith('.js')?'text/javascript':'text/html',body:fs.readFileSync(path.join(root,'ui',name==='axefx3'?'axefx3.html':name))});
   if(url.pathname==='/api/device')return route.fulfill({json:{active:'axefx3',detected:[{kind:'axefx3'}]}});
   if(req.method()==='POST')posts.push(url.pathname);
   if(url.pathname==='/api/axefx3/state')return route.fulfill({json:{connected:true,beta5_core_supported:true,
    firmware:'33.00-beta5.20261026',preset:327,name:'<EMPTY>',scene:1,cab_count:0,
    profile:{variant:'mk2',write_supported:false},route:[],route_problem:null,
    scene_names:Array.from({length:8},(_,i)=>[i+1,'']),warning:'Experimental one-scene core only.'}});
   if(url.pathname==='/api/axefx3/plan'){
    const body=req.postDataJSON();assert.equal(body.scenes,1);assert.equal(body.expected_preset,327);pending=true;
    return route.fulfill({json:{mode:'beta5-core',token:'synthetic-one-use',name:'AI-Core',target:{preset:327},
     summary:'<img src=x> synthetic proposal',scenes:['Crunch'],required_route:['Input 1','Amp 1','Cab 1','Output 1'],
     warnings:['No Store or physical audio claim.'],actions:[{kind:'param',eid:58,pid:1,value:5.2}],
     cab_choices:[{side:'IR1',name:'4x12 Brit 70s GB 57 B',position:'bank 1, slot 517'}],
     design:{name:'Core',scene_name:'Crunch',amp_model:'Brit 800 2204 High',
      amp:{gain:5.2,bass:4,mid:6.5,treble:5.5,master:5,depth:2,presence:4.5,level:-18},cab:{bank:1,slot:517}}}});
   }
   if(url.pathname==='/api/axefx3/send'){
    assert(pending);pending=false;const body=req.postDataJSON();assert.equal(body.external_audio_muted,true);assert.equal(body.target_confirmed,true);
    return route.fulfill({json:{ok:true,stored:false,results:[{ok:true,detail:'Synthetic verified'}],skipped:0,detail:'Synthetic acceptance only.'}});
   }
   if(url.pathname==='/api/axefx3/discard'){pending=false;return route.fulfill({json:{ok:true}});}
   return route.fulfill({status:404,json:{detail:'Not supported in fixture'}});
  });
  await page.goto('http://tc.test/axefx3');await page.waitForFunction(()=>!busy&&state?.beta5_core_supported);
  assert.equal(await page.locator('#deviceChoice option').count(),1);
  assert.equal(await page.locator('#scenes').inputValue(),'1');
  assert(await page.locator('#scenes').evaluate(e=>[...e.options].filter(o=>Number(o.value)>1).every(o=>o.disabled)));
  assert(await page.locator('#engage').isEnabled(),'Factory catalog must not require imported user names');
  await page.fill('#prompt','One British crunch scene');await page.click('#engage');await page.waitForFunction(()=>!busy&&proposal?.token);
  assert.equal(await page.locator('#sceneRows tr').count(),1);assert.match(await page.textContent('#sceneRows'),/Brit 800.*gain 5.2/);
  assert.equal(await page.locator('#conversation img').count(),0);assert.equal(posts.filter(p=>p.endsWith('/send')).length,0);
  await page.click('#reviewbtn');await page.click('#toconfirm');assert(await page.locator('#apply').isDisabled());
  await page.check('#confirmed');assert(await page.locator('#apply').isDisabled());await page.check('#muted');await page.click('#apply');
  await page.waitForFunction(()=>!busy&&currentStage===4);
  assert.equal(posts.filter(p=>p.endsWith('/send')).length,1);
  assert(!posts.some(p=>p.includes('/store')||p.includes('/nam/')));assert.deepEqual(errors,[]);
  console.log('PASS: bounded Beta5 GUI, Factory-only empty grid, one-scene review, two acknowledgements, one synthetic SEND; no hardware claim.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
