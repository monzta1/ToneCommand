// Real Chrome, shipped workspace dropdowns, mocked GETs only; no AI or MIDI.
const {chromium}=require(process.env.TC_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.TC_BROWSER_EXECUTABLE?{executablePath:process.env.TC_BROWSER_EXECUTABLE}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  const errors=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
   const req=route.request(),url=new URL(req.url());
   requests.push({method:req.method(),path:url.pathname});
   if(url.origin!=='http://127.0.0.1:8909'||req.method()!=='GET')return route.abort();
   if(['/axefx3','/controllers'].includes(url.pathname)){
    let html=fs.readFileSync(path.join(root,'ui',url.pathname.slice(1)+'.html'),'utf8');
    html=html.replace(/<script[^>]*src="\/(?:axefx3|controllers)\.js"[^>]*><\/script>/g,'');
    return route.fulfill({contentType:'text/html',body:html});
   }
   if(url.pathname==='/simple')return route.fulfill({contentType:'text/html',body:
    '<html><body><details id="workspaceSettings"><summary>SETTINGS</summary><label for="tc-language-select">Language</label>'
    +'<select id="tc-language-select"></select><p id="tc-language-status" role="status"></p></details>'
    +'<button id="sample">SETTINGS</button><textarea id="prompt">Keep my draft</textarea><div id="plan">Keep my plan</div>'
    +'<input id="consent" type="checkbox" checked><script src="/language/i18next.min.js"></script>'
    +'<script src="/language/tc-language.js"></script></body></html>'});
   if(url.pathname==='/axefx3.css')return route.fulfill({contentType:'text/css',body:
    fs.readFileSync(path.join(root,'ui/index.html'),'utf8').split('<style>')[1].split('</style>')[0]});
   if(url.pathname.startsWith('/language/')){
    const asset=path.join(root,'ui/languages',path.basename(url.pathname));
    if(fs.existsSync(asset))return route.fulfill({contentType:asset.endsWith('.js')?'text/javascript':'application/json',body:fs.readFileSync(asset)});
   }
   return route.fulfill({status:404,body:''});
  });
  const open=async url=>{
   await page.goto('http://127.0.0.1:8909'+url);
   await page.evaluate(()=>TCLanguage.ready);
   await page.locator('#workspaceSettings>summary').click();
  };
  const choose=async locale=>{
   await page.locator('#tc-language-select').selectOption(locale);
   await page.waitForFunction(value=>TCLanguage.locale===value,locale);
  };
  for(const route of ['/axefx3','/controllers']){
   await open(route);
   assert.equal(await page.locator('#tc-language-select option').count(),3);
   assert.equal(await page.locator('#tc-language-dialog,.tc-language-trigger').count(),0);
   if(route==='/axefx3')await page.locator('#prompt').fill('Keep my design request');
   for(const locale of ['nl','de','en']){
    await choose(locale);
    assert.equal(await page.locator('#tc-language-select').inputValue(),locale);
    if(route==='/axefx3')assert.equal(await page.locator('#prompt').inputValue(),'Keep my design request');
   }
   for(const width of route==='/axefx3'?[1440,1180]:[1440,1180,390]){
    await page.setViewportSize({width,height:900});
    const box=await page.locator('#tc-language-select').boundingBox();
    assert(box&&box.x>=0&&box.x+box.width<=width,route+' dropdown fits '+width);
   }
   await page.setViewportSize({width:1280,height:900});
   await choose('nl');
   if(process.env.TC_LANGUAGE_SCREENSHOT&&route==='/axefx3')await page.screenshot({path:process.env.TC_LANGUAGE_SCREENSHOT});
   await page.reload();await page.evaluate(()=>TCLanguage.ready);
   assert.equal(await page.evaluate(()=>TCLanguage.locale),'nl');
  }
  await open('/simple');await choose('de');
  assert.equal(await page.textContent('#sample'),'EINSTELLUNGEN');
  assert.equal(await page.textContent('#plan'),'Keep my plan');
  assert.equal(await page.locator('#prompt').inputValue(),'Keep my draft');
  assert(await page.locator('#consent').isChecked());
  await page.locator('#tc-language-select').focus();
  await page.keyboard.press('Home');await page.keyboard.press('Enter');
  await page.waitForFunction(()=>TCLanguage.locale==='en');
  assert.deepEqual(errors,[]);
  assert(requests.every(r=>r.method==='GET'&&!r.path.startsWith('/api/')));
  console.log('PASS: native workspace Settings dropdowns, EN/NL/DE, supported widths, keyboard, persistence and unchanged draft/plan/consent; no device requests.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
