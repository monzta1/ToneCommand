const {chromium} = require(process.env.TC_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.TC_BROWSER_EXECUTABLE ? {executablePath:process.env.TC_BROWSER_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage();
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(error.message));
    const catalog = JSON.parse(fs.readFileSync(path.join(__dirname,'../ui/languages/en.json'),'utf8'));
    await page.route('**/*', route => {
      const req = route.request(), url = new URL(req.url());
      requests.push({url:req.url(),method:req.method()});
      if(url.origin !== 'http://127.0.0.1:8909') return route.abort();
      if(url.pathname === '/') return route.fulfill({contentType:'text/html',body:
        '<html lang="en"><body><header></header><button id="sample">Interface language</button>'
        + '<select id="wire"><option>External 1</option><option>Fast Pos</option></select>'
        + '<textarea id="prompt">Mijn verzoek</textarea><p id="live">Live preset name</p>'
        + '<input id="consent" type="checkbox" checked><div id="plan">My pending plan</div>'
        + '<script src="/language/i18next.min.js"></script><script src="/language/tc-language.js"></script>'
        + '<script>document.getElementById("live").textContent="Mijn preset";</script></body></html>'});
      const asset = url.pathname.split('/').pop();
      const location = path.join(__dirname,'../ui/languages',asset);
      if(!fs.existsSync(location)) return route.fulfill({status:404,body:''});
      return route.fulfill({contentType:asset.endsWith('.js')?'text/javascript':'application/json',body:fs.readFileSync(location)});
    });
    await page.goto('http://127.0.0.1:8909/');
    await page.evaluate(() => TCLanguage.ready);
    assert.equal(await page.evaluate(() => TCLanguage.locale),'en');
    await page.locator('button[aria-label="Interface language"]').click();
    assert(await page.locator('#tc-language-dialog').isVisible());
    const pack = {schema:1,locale:'nl',name:'Nederlands',catalog_version:catalog.catalog_version,
      catalog_sha256:catalog.catalog_sha256,translations:{'Interface language':'Interfacetaal'}};
    const upload = value => page.locator('#tc-language-dialog input').setInputFiles({name:'nl.json',
      mimeType:'application/json',buffer:Buffer.from(JSON.stringify(value))});
    await upload(pack);
    await page.waitForFunction(() => TCLanguage.locale === 'nl');
    assert.equal(await page.textContent('#sample'),'Interfacetaal');
    assert.equal(await page.locator('#wire').inputValue(),'External 1');
    assert.equal(await page.locator('#prompt').inputValue(),'Mijn verzoek');
    assert.equal(await page.textContent('#live'),'Mijn preset');
    assert.equal(await page.textContent('#plan'),'My pending plan');
    assert(await page.locator('#consent').isChecked());
    const protectedKey = catalog.protected_keys[0];
    await upload({...pack,translations:{[protectedKey]:'Unsafe replacement'}});
    assert.match(await page.locator('#tc-language-dialog [role=status]').innerText(),/not installed/);
    await upload({...pack,catalog_sha256:'wrong'});
    assert.match(await page.locator('#tc-language-dialog [role=status]').innerText(),/incompatible/);
    await upload({...pack,translations:{'not-a-key':'x'}});
    assert.match(await page.locator('#tc-language-dialog [role=status]').innerText(),/unknown key/);
    await page.locator('#tc-language-dialog select').selectOption('en');
    await page.waitForFunction(() => TCLanguage.locale === 'en');
    assert.equal(await page.textContent('#sample'),'Interface language');
    assert.equal(await page.textContent('#live'),'Mijn preset');
    assert(requests.every(r=>r.method==='GET' && r.url.startsWith('http://127.0.0.1:8909/')));
    assert.deepEqual(errors,[]);
    console.log('PASS: local import/fallback, protected text, wire values, drafts, plans, consent and no AI/device requests.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
