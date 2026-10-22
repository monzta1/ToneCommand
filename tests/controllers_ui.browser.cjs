// Local shipped assets and mocked APIs. No server, MIDI or hardware writes.
// TC_PLAYWRIGHT_MODULE can point to an existing Playwright installation.
const {chromium} = require(process.env.TC_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.TC_BROWSER_EXECUTABLE ? {executablePath:process.env.TC_BROWSER_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1280,height:1000}});
    const errors = [], sends = [], reviews = [];
    page.on('pageerror', error => errors.push(error.message));
    let connected=false, selected=false, draft=null, fail=false, connectFailure=true;
    const state = {connected:true, gig_locked:false, firmware:'32.06',preset:324,preset_name:'Controller test',scene:1,
      sources:[{value:12,label:'External 1'},{value:13,label:'External 2'}],
      targets:[{effect_id:95,label:'Wah 2 / Control',source:12,source_name:'External 1',auto_engage:'Fast Pos',writable:true,modes:['Off','Fast Pos']},
               {effect_id:102,label:'Volume 1 / Volume',source:13,source_name:'External 2',auto_engage:'Off',writable:true,modes:['Off']}]};
    await page.route('**/api/controllers/**', async route => {
      const request=route.request(), endpoint=request.url().split('/').pop(), body=request.postDataJSON();
      let result={ok:true}, status=200;
      if(endpoint==='state') result=connected?state:{connected:false,controller_selected:selected,gig_locked:false};
      if(endpoint==='connect') {
        selected=true;connected=!connectFailure;
        result=connectFailure?{detail:'Test: device unavailable'}:{connected:true};
        status=connectFailure?503:200;
      }
      if(endpoint==='disconnect') { connected=false;selected=false;result={connected:false}; }
      if(endpoint==='review') {
        reviews.push(body);draft=body;
        const target=state.targets.find(t=>t.effect_id===body.effect_id);
        result={token:'review-token',preset:324,preset_name:state.preset_name,scene:1,target:target.label,
          before_source:target.source_name,after_source:body.source===12?'External 1':'External 2',
          before_auto:target.auto_engage,after_auto:body.auto_engage||"Preserve",new_binding:false};
      }
      if(endpoint==='send') {
        sends.push(body);
        assert.equal(body.token,'review-token');
        assert.equal(body.external_audio_muted,true);assert.equal(body.target_confirmed,true);
        result={ok:!fail,stored:false,results:[{ok:!fail,detail:fail?'Readback mismatch; stopped':'Matched'}]};
        if(!fail) {
          const target=state.targets.find(t=>t.effect_id===draft.effect_id);
          target.source=draft.source; target.source_name=draft.source===12?'External 1':'External 2';
        }
      }
      await route.fulfill({status,contentType:'application/json',body:JSON.stringify(result)});
    });
    await page.route('**/*',async route=>{
      const pathname=new URL(route.request().url()).pathname;
      if(pathname.startsWith('/language/'))return route.fulfill({contentType:pathname.endsWith('.json')?'application/json':'text/javascript',body:fs.readFileSync(path.join(__dirname,'../ui/languages',pathname.split('/').pop()))});
      if(pathname.startsWith('/api/controllers/'))return route.fallback();
      const names={'/controllers':'controllers.html','/controllers.js':'controllers.js','/logo.png':'logo.png'};
      const name=names[pathname];
      if(!name)return route.fulfill({status:404,body:''});
      return route.fulfill({contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.png')?'image/png':'text/html',
        body:fs.readFileSync(path.join(__dirname,'../ui',name))});
    });
    await page.goto((process.env.TC_TEST_URL || 'http://127.0.0.1:8911')+'/controllers');
    await page.locator('#connect:not([disabled])').waitFor();
    assert.equal(sends.length,0);
    await page.click('#connect');await page.locator('#disconnect:not([disabled])').waitFor();
    assert.match(await page.locator('#status').textContent(),/unavailable/);
    await page.click('#disconnect');await page.locator('#connect:not([disabled])').waitFor();
    assert(await page.locator('#back').isVisible());
    connectFailure=false;
    await page.click('#connect');await page.locator('#source-95').waitFor();
    await page.selectOption('#source-95','13');
    assert.equal(sends.length,0);assert.equal(reviews.length,0);
    await page.locator('.row').filter({has:page.locator('#source-95')}).getByRole('button',{name:'Review',exact:true}).click();
    await page.locator('#review:not([hidden])').waitFor();
    assert(await page.locator('#send').isDisabled());
    await page.check('#targetConfirmed');assert(await page.locator('#send').isDisabled());
    // Editing a choice invalidates the displayed ticket and acknowledgements.
    await page.selectOption('#source-95','12');
    assert(await page.locator('#review').isHidden());assert(!(await page.locator('#targetConfirmed').isChecked()));
    await page.selectOption('#source-102','12');assert(await page.locator('#mode-102').isDisabled());
    await page.locator('.row').filter({has:page.locator('#source-102')}).getByRole('button',{name:'Review',exact:true}).click();
    await page.check('#targetConfirmed');await page.check('#muted');
    await page.locator('#send:not([disabled])').waitFor();
    await page.click('#send');await page.getByRole('heading',{name:"Binding read back and confirmed"}).waitFor();
    await page.locator('#refresh:not([disabled])').waitFor();assert.equal(sends.length,1);
    assert(await page.locator('#send').isDisabled());
    assert.equal(reviews.at(-1).auto_engage,'Off');
    if(process.env.TC_DESKTOP_SCREENSHOT) await page.screenshot({path:process.env.TC_DESKTOP_SCREENSHOT,fullPage:true});
    // A failed independent verification must not look like success or retry.
    fail=true;
    await page.selectOption('#source-95','13');
    await page.locator('.row').filter({has:page.locator('#source-95')}).getByRole('button',{name:'Review',exact:true}).click();
    await page.check('#targetConfirmed');await page.check('#muted');await page.click('#send');
    await page.getByRole('heading',{name:"Transmission stopped"}).waitFor();
    await page.locator('#refresh:not([disabled])').waitFor();assert.equal(sends.length,2);
    assert.match(await page.locator('#resultText').textContent(),/Partial changes/);
    // Device strings are text, never HTML.
    state.preset_name='<img src=x onerror="window.injection=true">';
    await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(await page.evaluate(()=>window.injection),undefined);
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    if(process.env.TC_SCREENSHOT) await page.screenshot({path:process.env.TC_SCREENSHOT,fullPage:true});
    assert.deepEqual(errors,[]);
    // The migrated FW33 wah remains usable while unmeasured Volume is blocked.
    state.firmware='33.00-beta.20261006';
    state.targets[1].writable=false;state.targets[1].reason='Volume has not been migrated';
    await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#source-95').isEnabled());
    assert(await page.locator('#source-102').isDisabled());
    assert.match(await page.locator('#rows').textContent(),/Volume has not been migrated/);
    await page.click('#disconnect');await page.locator('#connect:not([disabled])').waitFor();
    assert.equal(sends.length,2);
    console.log('PASS: controller UI selection, review invalidation, confirmations, send, failure, XSS, mobile, disconnect. Hardware writes: 0.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
