// Shipped pages in Chrome with JavaScript disabled. No server, AI or MIDI.
const {chromium}=require(process.env.TC_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
const root=path.join(__dirname,'..');
const pages={'/':'ui/index.html','/axefx3':'ui/axefx3.html',
 '/controllers':'ui/controllers.html','/mk1-ai':'packaging/mk1-ai/index.html',
 '/mk1-test':'packaging/mk1/welcome.html'};
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.TC_BROWSER_EXECUTABLE?{executablePath:process.env.TC_BROWSER_EXECUTABLE}:{})});
 try{
  const context=await browser.newContext({javaScriptEnabled:false,viewport:{width:1440,height:1000}});
  const requests=[];
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());requests.push({method:request.method(),path:url.pathname});
   assert.equal(request.method(),'GET');
   if(url.origin!=='http://127.0.0.1:8909')return route.abort();
   if(pages[url.pathname])return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,pages[url.pathname]))});
   if(['/axefx3.css','/trial.css'].includes(url.pathname))return route.fulfill({contentType:'text/css',body:fs.readFileSync(path.join(root,'ui/index.html'),'utf8').split('<style>')[1].split('</style>')[0]});
   return route.fulfill({status:404,body:''});
  });
  const page=await context.newPage();
  for(const route of Object.keys(pages)){
   await page.goto('http://127.0.0.1:8909'+route);
   assert((await page.title()).includes('Unofficial FX3'));
   const header=page.locator('header').first();await header.waitFor({state:'visible'});
   assert((await header.innerText()).includes('Unofficial FX3'));
   const links=page.locator('a[href="https://github.com/Axelman8/ToneCommand/issues"]');
   assert(await links.count()>0);assert(await links.first().isVisible());
   assert.equal(await header.locator('img').count(),0);
   assert(!(await header.innerText()).includes('TONE // COMMAND'));
   if(process.env.TC_BRANDING_ARTIFACTS){
    fs.mkdirSync(process.env.TC_BRANDING_ARTIFACTS,{recursive:true});
    await page.screenshot({path:path.join(process.env.TC_BRANDING_ARTIFACTS,(route==='/'?'main':route.slice(1))+'.png')});
   }
  }
  assert(!requests.some(r=>r.path.includes('logo')));
  assert(!requests.some(r=>r.path.startsWith('/api/')));
  console.log(JSON.stringify({passed:true,pages:Object.keys(pages),scriptDisabled:true,apiRequests:0,logoRequests:0}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
