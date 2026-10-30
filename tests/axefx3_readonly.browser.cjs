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
    let kind = 'axefx3';
    const state = () => ({connected: true, read_only: true,
      navigation_read_only: kind === 'axefx3',
      read_only_reason: 'Axe-Fx III support is read-only. Change presets on the unit.',
      preset: {number: 320, editor: 320, name: 'Read Test'},
      scene: {number: 1, name: 'Scene 1'}, firmware: '33.00',
      scenes: Array.from({length: 8}, (_, i) => ({number: i + 1, name: 'Scene ' + (i + 1)})),
      blocks: [{effect_id: 58, label: 'Amp 1', family: 'DISTORT', instance: 1,
        channel: 'A', bypassed: false}, {effect_id: 206, label: 'Block 206',
        family: 'UNKNOWN', instance: 1, channel: 'B', bypassed: true}],
      values: {}, params: {}, mods: [], cab_sel: null, gig_mode: false,
      device: {active: kind, selected: kind, label: kind === 'fm3' ? 'Fractal FM3' : 'Fractal Axe-Fx III',
        available: [{kind: 'fm9', label: 'Fractal FM9'}, {kind, label: 'Fractal ' + kind}],
        ambiguous: false, detected: []}});
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const req = route.request(), url = new URL(req.url());
      if (url.origin !== 'http://127.0.0.1:8909') return route.abort();
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
      if (url.pathname.startsWith('/language/')) {
        const asset = url.pathname.split('/').pop();
        const file = path.join(__dirname, '../ui/languages', asset);
        if (!fs.existsSync(file)) return route.fulfill({status:404, body:''});
        return route.fulfill({contentType:asset.endsWith('.js') ? 'text/javascript' : 'application/json',
          body:fs.readFileSync(file)});
      }
      if (url.pathname === '/api/state') return route.fulfill({json: state()});
      if (url.pathname === '/api/device') return route.fulfill({json: state().device});
      if (url.pathname.endsWith('/stream')) return route.fulfill({contentType: 'text/event-stream', body: ''});
      if (url.pathname === '/api/presets') return route.fulfill({json: {slots: []}});
      if (url.pathname === '/api/ai/status') return route.fulfill({json: {backends: [], ready: false}});
      if (url.pathname === '/api/version') return route.fulfill({json: {version: '1.5.16', label: '1.5.16'}});
      return route.fulfill({json: {}});
    });
    await page.goto('http://127.0.0.1:8909/');
    await page.evaluate(() => TCLanguage.ready);
    await page.waitForFunction(() => document.body.classList.contains('readonly-navigation'));
    assert.equal(await page.locator('#scenes .sc:disabled').count(), 8);
    assert.match(await page.locator('#blocks').innerText(), /Block 206/);
    assert.match(await page.locator('#blocks').innerText(), /Change presets on the unit/);
    assert(!/presets and scenes switch/.test(await page.locator('#blocks').innerText()));
    assert.match(await page.locator('#linktext').innerText(), /AXE-FX III/);
    await page.evaluate(async () => { await gotoScene(2); await gotoPreset(321, true); });
    assert.deepEqual(posts, []);
    for (const width of [1180, 1280, 1440]) {
      await page.setViewportSize({width, height: 1000});
      assert(await page.locator('#blocks').isVisible());
      assert.equal(await page.locator('#scenes .sc:disabled').count(), 8);
      await page.evaluate(() => openDrawer('settings'));
      assert(await page.locator('#tc-language-select').isVisible());
      await page.locator('#tc-language-select').selectOption('nl');
      await page.waitForFunction(() => TCLanguage.locale === 'nl');
      assert.equal(await page.locator('#shset').innerText(), 'INSTELLINGEN');
      assert.equal(await page.locator('#tc-language-settings input[type=file]').count(), 0);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.locator('#tc-language-select').selectOption('en');
      await page.waitForFunction(() => TCLanguage.locale === 'en');
      await page.evaluate(() => closeDrawer());
    }
    // Existing FM3 navigation must not inherit the III-only lockout.
    kind = 'fm3';
    await page.evaluate(() => refresh());
    assert.equal(await page.locator('#scenes .sc:disabled').count(), 0);
    assert(!await page.locator('body').evaluate(el => el.classList.contains('readonly-navigation')));
    assert.match(await page.locator('#blocks').innerText(), /presets and scenes switch/);
    assert.deepEqual(errors, []);
    assert.deepEqual(posts, []);
    console.log('PASS: main UI III status, unknown IDs, navigation lockout, three widths and FM3 recovery; no writes.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
