// Shipped chain renderer and styles in real Chrome. No API, AI or MIDI calls.
const {chromium}=require(process.env.TC_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

(async()=>{
  const html=fs.readFileSync(process.env.TC_UI_FILE||path.join(__dirname,'../ui/index.html'),'utf8');
  const style=html.slice(html.indexOf('<style>')+7,html.indexOf('</style>'));
  const renderer=html.slice(html.indexOf('const CW ='),html.indexOf('async function loadGrid()'));
  assert(renderer.includes('function renderGrid('));
  const browser=await chromium.launch({headless:true,
    ...(process.env.TC_BROWSER_EXECUTABLE?{executablePath:process.env.TC_BROWSER_EXECUTABLE}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:700}});
    await page.route('**/*',route=>route.abort());
    await page.setContent(`<style>${style}</style><div id="blocks"></div><div id="gridwhy"></div><div id="gridbig"></div>`);
    await page.addScriptTag({content:`
      const $=id=>document.getElementById(id);
      const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      let lastState={values:{AMP_MODEL:'Brit 800',WAH_TYPE_NAME:'Cry Babe',DELAY_TYPE_NAME:'Digital Mono'}};
      let gridOpen=false;
      function openGrid(){$('gridbig').innerHTML=$('blocks').innerHTML;}
      ${renderer}
    `});
    await page.evaluate(()=>{
      renderGrid({alive:true,cells:[
        {row:2,col:0,family:'DISTORT',instance:1,label:'Amp 1',channel:'A',live:true,bypassed:false,feeds:[]},
        {row:2,col:1,family:'WAH',instance:1,label:'Wah 1',channel:'B',live:true,bypassed:true,feeds:[2]},
        {row:2,col:2,family:'DELAY',instance:1,label:'Delay 1',channel:'C',live:false,bypassed:true,feeds:[2]}
      ]});
      gridOpen=true;openGrid();
    });
    for(const container of ['#blocks','#gridbig']){
      const cells=page.locator(`${container} svg.grid .cell`);
      assert.equal(await cells.count(),3);
      const active=await cells.first().evaluate(c=>({
        name:getComputedStyle(c.querySelector('.nm')).fill,
        border:getComputedStyle(c.querySelector('.chbox')).stroke
      }));
      assert.equal(active.name,'rgb(255, 255, 255)');
      assert.equal(active.border,'rgb(61, 255, 160)');
      for(const i of [1,2]){
        const bypass=await cells.nth(i).evaluate(c=>({
          name:getComputedStyle(c.querySelector('.nm')).fill,
          model:getComputedStyle(c.querySelector('.sub')).fill,
          opacity:getComputedStyle(c.querySelector('.sub')).opacity,
          channel:getComputedStyle(c.querySelector('.ch')).fill,
          border:getComputedStyle(c.querySelector('.chbox')).stroke,
          badgeDash:getComputedStyle(c.querySelector('.chbox')).strokeDasharray,
          blockDash:getComputedStyle(c.querySelector('rect')).strokeDasharray,
          label:c.querySelector('title').textContent
        }));
        for(const field of ['name','model','channel'])assert.equal(bypass[field],'rgb(255, 255, 255)');
        assert.equal(bypass.opacity,'1');
        assert.equal(bypass.border,'rgb(255, 84, 112)');
        assert.equal(bypass.badgeDash,'none');
        assert.equal(bypass.blockDash,'4px, 3px');
        assert.match(bypass.label,/bypassed/);
      }
    }
    if(process.env.TC_SCREENSHOT)await page.screenshot({path:process.env.TC_SCREENSHOT,fullPage:true});
    console.log('PASS: live/dead bypass names white, solid red channel badges, active styling and expanded chain preserved. No hardware writes.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
