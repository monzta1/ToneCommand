// Shipped main UI, all requests intercepted. No server, MIDI, account or AI.
const {chromium} = require(process.env.TC_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.TC_BROWSER_EXECUTABLE ? {executablePath: process.env.TC_BROWSER_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [], posts = [];
    let kind = 'axefx3', chassis = 'mk1', rejectChoice = false;
    let selected = null, iiiAvailable = true, fm3Available = true, connected = true;
    const profilePosts = [];
    const state = () => ({connected, read_only: true,
      navigation_read_only: kind === 'axefx3',
      read_only_reason: 'Axe-Fx III support is read-only. Change presets on the unit.',
      preset: {number: 320, editor: kind === 'axefx3' ? 320 : 321, name: 'Read Test'},
      scene: {number: 1, name: 'Scene 1'}, firmware: '33.00',
      scenes: Array.from({length: 8}, (_, i) => ({number: i + 1, name: 'Scene ' + (i + 1)})),
      blocks: [{effect_id: 58, label: 'Amp 1', family: 'DISTORT', instance: 1,
        channel: 'A', bypassed: false}, {effect_id: 206, label: 'Block 206',
        family: 'UNKNOWN', instance: 1, channel: 'B', bypassed: true}],
      values: {}, params: {}, mods: [], cab_sel: null, gig_mode: false,
      device: {active: kind, selected: selected ?? kind,
        ...(kind === 'axefx3' ? {axefx3:{chassis,preset_count:chassis === 'mk1' ? 512 : 1024,declared:true,read_only:true}} : {}), label: kind === 'fm3' ? 'Fractal FM3' : 'Fractal Axe-Fx III',
        available: [{kind: 'fm9', label: 'Fractal FM9'},
          ...(iiiAvailable ? [{kind:'axefx3', label:'Fractal Axe-Fx III'}] : []),
          ...(fm3Available ? [{kind:'fm3',label:'Fractal FM3'}] : [])],
        ambiguous: false, detected: []}});
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const req = route.request(), url = new URL(req.url());
      if (url.origin !== 'http://127.0.0.1:8909') return route.abort();
      if (req.method() === 'POST' && url.pathname === '/api/device/select') {
        const payload = JSON.parse(req.postData());
        assert.equal(payload.kind,'axefx3');
        assert(['mk1','mk2','turbo'].includes(payload.chassis));
        profilePosts.push(payload);
        if(rejectChoice) return route.fulfill({status:423,json:{error:'GIG LOCK is on'}});
        chassis = payload.chassis;
        kind = 'axefx3';
        return route.fulfill({json:{ok:true,active:kind,selected:kind,axefx3:state().device.axefx3}});
      }
      if (req.method() !== 'GET') {
        posts.push(url.pathname);
        return route.fulfill({status: 409, json: {error: 'Offline browser test'}});
      }
      if (url.pathname === '/') return route.fulfill({contentType: 'text/html',
        body: fs.readFileSync(path.join(__dirname, '../ui/index.html'), 'utf8')});
      if (url.pathname === '/axefx3-reviewed-edit.js') return route.fulfill({contentType:'text/javascript',
        body:fs.readFileSync(path.join(__dirname,'../ui/axefx3-reviewed-edit.js'),'utf8')});
      if (url.pathname === '/api/axefx3/edit/state') return route.fulfill({json:{configured:false,available:false}});
      if (url.pathname === '/logo.png') return route.fulfill({contentType: 'image/png',
        body: fs.readFileSync(path.join(__dirname, '../ui/logo.png'))});
      if (url.pathname === '/api/state') return route.fulfill({json: state()});
      if (url.pathname === '/api/device') return route.fulfill({json: state().device});
      if (url.pathname === '/api/presets/stream') {
        const total = chassis === 'mk1' ? 512 : 1024;
        return route.fulfill({contentType:'text/event-stream',body:'event: progress\ndata: '
          + JSON.stringify({read:total,total}) + '\n\nevent: result\ndata: '
          + JSON.stringify({slots:[{number:total-1,editor:total-1,name:'Boundary name'}],cached:false}) + '\n\n'});
      }
      if (url.pathname.endsWith('/stream')) return route.fulfill({contentType: 'text/event-stream', body: ''});
      if (url.pathname === '/api/presets') return route.fulfill({json: {slots: []}});
      if (url.pathname === '/api/ai/status') return route.fulfill({json: {backends: [], ready: false}});
      if (url.pathname === '/api/version') return route.fulfill({json: {version: '1.5.16', label: '1.5.16'}});
      return route.fulfill({json: {}});
    });
    await page.goto('http://127.0.0.1:8909/');
    await page.waitForFunction(() => document.body.classList.contains('readonly-navigation'));
    assert.equal(await page.locator('#scenes .sc:disabled').count(), 8);
    assert.match(await page.locator('#blocks').innerText(), /Block 206/);
    assert.match(await page.locator('#blocks').innerText(), /Change presets on the unit/);
    assert(!/presets and scenes switch/.test(await page.locator('#blocks').innerText()));
    assert.match(await page.locator('#linktext').innerText(), /AXE-FX III/);
    assert.equal(await page.locator('#preset .pnum').innerText(), '320');
    await page.evaluate(async () => { await gotoScene(2); await gotoPreset(321, true); });
    assert.deepEqual(posts, []);
    for (const width of [1180, 1280, 1440]) {
      await page.setViewportSize({width, height: 1000});
      assert(await page.locator('#blocks').isVisible());
      assert.equal(await page.locator('#scenes .sc:disabled').count(), 8);
    }
    await page.evaluate(() => openDrawer('devices'));
    assert(await page.locator('#axefx3chassis').isVisible());
    assert.equal(await page.locator('#axefx3chassis').inputValue(),'mk1');
    await page.locator('#axefx3chassis').selectOption('mk2');
    await page.waitForFunction(() => deviceState.axefx3?.chassis === 'mk2' && !axeFxChassisBusy);
    assert.match(await page.locator('#axefx3chassisstatus').innerText(),/0..1023/);
    assert((await page.evaluate(() => allSlots)).every(slot => slot.number === 1023),
      'Names must be cleared or replaced by a fresh MK2 scan, never the old MK1 boundary');
    await page.evaluate(() => loadPresets(true));
    assert.equal(await page.evaluate(() => allSlots.at(-1).number),1023);
    assert.equal(await page.evaluate(() => allSlots.at(-1).editor),1023);
    await page.locator('#axefx3chassis').selectOption('turbo');
    await page.waitForFunction(() => deviceState.axefx3?.chassis === 'turbo' && !axeFxChassisBusy);
    rejectChoice = true;
    await page.locator('#axefx3chassis').selectOption('mk1');
    await page.waitForFunction(() => document.getElementById('axefx3chassisstatus').textContent.includes('Could not confirm'));
    assert.equal(await page.locator('#axefx3chassis').inputValue(),'turbo');
    rejectChoice = false;
    await page.locator('#axefx3chassis').selectOption('mk1');
    await page.waitForFunction(() => deviceState.axefx3?.chassis === 'mk1' && !axeFxChassisBusy);
    await page.evaluate(() => loadPresets(true));
    assert.equal(await page.evaluate(() => allSlots.at(-1).number),511);
    assert.equal(await page.evaluate(() => allSlots.at(-1).editor),511);
    await page.evaluate(() => closeDrawer());
    assert.equal(profilePosts.length,4);
    // Existing FM3 navigation must not inherit the III-only lockout.
    kind = 'fm3';
    await page.evaluate(() => refresh());
    assert.equal(await page.locator('#scenes .sc:disabled').count(), 0);
    assert(!await page.locator('body').evaluate(el => el.classList.contains('readonly-navigation')));
    assert.match(await page.locator('#blocks').innerText(), /presets and scenes switch/);
    // The III-only box is absent until relevant, including before any poll.
    const markup = fs.readFileSync(path.join(__dirname, '../ui/index.html'), 'utf8');
    assert.match(markup, /<div[^>]*id="axefx3hardware"[^>]*hidden>/);
    await page.locator('#prompt').fill('Keep this unsent request');
    await page.evaluate(() => openDrawer('devices'));
    for (const width of [1180, 1280, 1440]) {
      await page.setViewportSize({width, height: 1000});
      for (const active of ['fm9', 'fm3']) {
        kind = active;
        selected = null;
        iiiAvailable = false;
        await page.evaluate(() => refresh());
        assert(await page.locator('#axefx3hardware').isHidden());
        assert(await page.locator('#axefx3chassis').isDisabled());
      }
      // A detected III can be declared before connecting above slot 511.
      iiiAvailable = true;
      await page.evaluate(() => refresh());
      assert(await page.locator('#axefx3hardware').isVisible());
      assert(await page.locator('#axefx3chassis').isEnabled());
      // A selected but disconnected III keeps the declaration accessible.
      iiiAvailable = false;
      selected = 'axefx3';
      connected = false;
      await page.evaluate(() => refresh());
      assert(await page.locator('#axefx3hardware').isVisible());
      // An active III remains relevant even if discovery temporarily drops it.
      kind = 'axefx3';
      selected = null;
      connected = true;
      await page.evaluate(() => refresh());
      assert(await page.locator('#axefx3hardware').isVisible());
      // Removing the III while another device is selected hides the whole box.
      kind = 'fm9';
      await page.evaluate(() => refresh());
      assert(await page.locator('#axefx3hardware').isHidden());
    }
    assert.equal(await page.locator('#prompt').inputValue(), 'Keep this unsent request');
    kind = 'axefx3'; selected = null; fm3Available = false;
    await page.evaluate(() => refresh());
    assert(await page.locator('#fm3hardware').isHidden());
    assert(await page.locator('#deviceManualSetup').isVisible());
    await page.locator('#deviceManualSetup').click();
    assert(await page.locator('#fm3hardware').isVisible());
    await page.locator('#deviceManualSetup').click();
    assert(await page.locator('#fm3hardware').isHidden());
    fm3Available = true;
    await page.evaluate(() => refresh());
    assert(await page.locator('#fm3hardware').isVisible());
    assert(await page.locator('#deviceManualSetup').isHidden());
    fm3Available = false;
    await page.evaluate(() => refresh());
    assert(await page.locator('#fm3hardware').isHidden());
    assert.equal(await page.locator('#prompt').inputValue(), 'Keep this unsent request');
    assert.equal(profilePosts.length, 4, 'Visibility changes must not select a device');
    assert.deepEqual(errors, []);
    assert.deepEqual(posts, []);
    console.log('PASS: capacity, scoped names, refusal recovery, III-only box visibility, preserved draft, navigation lockout and FM3 recovery; only explicit local-profile POSTs.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
