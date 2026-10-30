// English MK1 landing page, shipped asset, fake APIs and no MIDI or accounts.
const {chromium}=require(process.env.TC_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.TC_BROWSER_EXECUTABLE?{executablePath:process.env.TC_BROWSER_EXECUTABLE}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:900}});
    const errors=[],calls=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url());
      if(url.pathname.startsWith('/language/'))return route.fulfill({contentType:url.pathname.endsWith('.json')?'application/json':'text/javascript',body:fs.readFileSync(path.join(__dirname,'../ui/languages',url.pathname.split('/').pop()))});
      if(url.pathname==='/mk1-test')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../packaging/mk1/welcome.html'),'utf8')});
      calls.push({path:url.pathname,method:request.method(),body:request.postDataJSON()});
      const report={observations:[{label:'baseline'}],read_only:true};
      let data;
      if(url.pathname.endsWith('/status'))data={version:'test',source_commit:'example'};
      else if(url.pathname.endsWith('/connect')||url.pathname.endsWith('/disconnect'))data={read_only:true};
      else if(url.pathname.endsWith('/observe'))data={observation:{label:'baseline',coherent:true},local_view:{preset:12,name:'<img src=x onerror=alert(1)>',scene:1,timestamp_utc:'now',coherent:true,blocks:[{effect_id:58,channel:0,bypassed:true}],grid:[{row:0,col:0,effect_id:58,is_shunt:false,cable_in_mask:0}]}};
      else if(url.pathname.endsWith('/report'))data=report;
      else throw new Error('Unexpected request: '+url.pathname);
      return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
    });
    await page.goto('http://127.0.0.1:8909/mk1-test');
    await page.waitForFunction(()=>document.getElementById('identity').textContent.includes('MK1 locked'));
    await page.click('#observe');
    assert((await page.textContent('#result')).includes('Confirm muted'));
    assert(!calls.some(call=>call.path.endsWith('/observe')));
    await page.click('#connect');
    await page.waitForFunction(()=>!document.getElementById('connect').disabled);
    await page.check('#consent');
    await page.fill('#firmware','33.00 beta2');
    await page.click('#observe');
    await page.waitForSelector('#grid table');
    assert.equal(await page.locator('#grid td').count(),84);
    assert((await page.textContent('#grid')).includes('Effect 58 / A / bypassed'));
    assert.equal(await page.locator('#gridStatus img').count(),0);
    assert((await page.textContent('#result')).includes('coherent'));
    const downloaded=page.waitForEvent('download');
    await page.click('#report');
    assert.equal((await downloaded).suggestedFilename(),'MK1-report.json');
    await page.waitForFunction(()=>!document.getElementById('disconnect').disabled);
    await page.click('#disconnect');
    await page.waitForFunction(()=>!document.getElementById('disconnect').disabled);
    assert(calls.some(call=>call.path==='/api/controllers/disconnect'));
    assert(!calls.some(call=>/send|store|install|login/.test(call.path)));
    for(const size of [{width:1180,height:720},{width:1440,height:1000}]){
      await page.setViewportSize(size);
      assert(await page.locator('#connect').evaluate(el=>el.getBoundingClientRect().right<=innerWidth));
    }
    assert.deepEqual(errors,[]);
    console.log('PASS: MK1 English connect/consent/grid/report/disconnect, 84 cells, XSS and fit; mocked APIs only.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
