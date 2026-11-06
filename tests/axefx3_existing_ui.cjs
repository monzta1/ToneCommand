/* Shipped addon, independent DOM/HTTP/clock. No browser, provider or hardware. */
'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8'),scenario=process.argv[3];
const nodes={},calls=[],timers=[],announcements=[];let hold=null,questionNext=false,sendError=false,configured=true,legacyPolls=0,legacySubmits=0;
let statePreset=329,stateScene=1;
function element(){return {hidden:false,disabled:false,checked:false,value:'',textContent:'',children:[],style:{},
  set id(value){this._id=value;nodes[value]=this;},get id(){return this._id;},
  classList:{add(){}},append(...items){this.children.push(...items);},before(){},setAttribute(){},addEventListener(){},
  replaceChildren(...items){this.children=[...items];},set innerHTML(v){throw new Error('Unsafe HTML assignment');}};}
const node=id=>nodes[id]??(nodes[id]=element());
const proposal={summary:'Keep the rig, add body.',target:{preset:329,name:'Existing'},changes:[
  {channel:'A',parameter:'DISTORT_DRIVE',before:5,after:5.4,model:'59 Bassguy Bright',affected_scenes:[1,3,6,7,8],reason:'<script>not markup</script>'},
  {channel:'B',parameter:'DISTORT_MID',before:5,after:5.6,model:'Vibrato Lux',affected_scenes:[2,4,5],reason:'More body.'}]};
const context={console,structuredClone,JSON,Promise,Error,Number,String,
  document:{getElementById:node,createElement:element,createTextNode:text=>({textContent:text})},
  currentPlan:null,stage:'request',stageDone:{},gigOn:false,armTimer:null,armLeft:0,
  planSending:false,planSent:0,planTotal:0,chatLog:[],submitRequest(){legacySubmits++;},
  lastState:{read_only:true},renderReadOnlyBlocks(){},
  workAnnounce(text,kind){assert.equal(context.planSending,false);announcements.push({text,kind});},
  esc:String,log(){},growPrompt(){},renderChat(){},renderGigLockWhy(){},planResult(){},sendPhase(){},
  disarmSend(){node('apply').hidden=true;node('apply').disabled=true;node('armbtn').hidden=false;},
  setStage(name){context.stage=name;},showPlan(value){context.currentPlan=value;},
  setInterval(fn){timers.push(fn);return timers.length;},clearInterval(){},
  async fetch(url,options={}){
    const path=url.split('/').pop(),body=options.body?JSON.parse(options.body):null;
    calls.push({path,body});
    if(hold?.path===path){const waiting=hold;hold=null;await waiting.promise;}
    let out;
    if(path==='state')out={configured,available:configured,preset:statePreset,scene:stateScene};
    if(path==='scan')out={scan_token:'s'.repeat(43),reference:{},scene_maps_verified:8};
    if(path==='discard')out={stage:'request'};
    if(path==='plan'){
      if(questionNext){questionNext=false;out={question:'Limit this adjustment to Gain and Mid?',scan_token:'s'.repeat(43)};}
      else out={token:'t'.repeat(43),plan_digest:'a'.repeat(64),expected_preset:329,expected_scene:1,proposal,stage:'plan'};
    }
    if(path==='review'||path==='confirm')out={...body,proposal,stage:path};
    if(path==='send')out=sendError?{error:'Uncertain: keep external audio muted'}:{verified:true,sent:2,stored:false,scene_maps_verified:8};
    return {ok:!sendError||path!=='send',json:async()=>out};
  }};
const legacy={active:()=>false,poll:async()=>{legacyPolls++;}};
for(const name of ['prepare','review','restart','renderConfirm','consentChanged','arm','send','invalidate','lockCards','renderRail','readonlyNote','completionNote'])legacy[name]=()=>{};
context.AFX3ReviewedEdit=legacy;context.window=context;vm.createContext(context);vm.runInContext(source,context);
context.AFX3Existing=context.installAFX3Existing();
const ui=context.AFX3Existing,bridge=context.AFX3ReviewedEdit;
const III={device:{active:'axefx3'},preset:{number:329},scene:{number:1}};
const count=path=>calls.filter(c=>c.path===path).length;
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function suspend(path){let release;const promise=new Promise(resolve=>{release=resolve;});hold={path,promise};return release;}
function scanConsent(){node('afx3existtarget').checked=true;node('afx3existscanmute').checked=true;node('afx3existscanmute').onchange();}
async function scanned(){await ui.poll(III);scanConsent();await ui.scan();}
async function prepared(){await scanned();node('prompt').value='More body without replacing the rig.';await ui.submit();}
async function reviewed(){await prepared();await ui.review();bridge.renderConfirm();}
async function armed(){await reviewed();node('ack').checked=true;node('afx3muted').checked=true;await ui.arm();}
(async()=>{
  if(scenario==='lifecycle'){
    await armed();assert.equal(count('send'),0);assert.equal(node('apply').hidden,false);assert.equal(context.stage,'review');
    await ui.send();assert.equal(count('send'),1);assert.equal(context.currentPlan.afx3_ticket,null);
    assert.equal(context.planSent,2);assert.equal(node('storeafter').hidden,true);
    assert.equal(calls.find(c=>c.path==='send').body.actions,undefined);await ui.send();assert.equal(count('send'),1);
    assert.match(announcements.at(-1).text,/2 changes verified/);assert.equal(announcements.at(-1).kind,'ok');
  }else if(scenario==='rescan'){
    await prepared();assert(context.currentPlan.afx3_ticket);
    await ui.scan();assert.equal(context.currentPlan.afx3_ticket,null);
    assert.equal(node('ack').checked,false);assert.equal(node('afx3muted').checked,false);
    assert.equal(count('scan'),2);assert.equal(count('send'),0);
  }else if(scenario==='scan-consent'){
    await ui.poll(III);await ui.scan();assert.equal(count('scan'),0);
    node('afx3existtarget').checked=true;await ui.scan();assert.equal(count('scan'),0);
    node('afx3existscanmute').checked=true;node('afx3existscanmute').onchange();await ui.scan();assert.equal(count('scan'),1);
  }else if(scenario==='target-consent-before-scan'||scenario==='target-consent-after-scan'){
    if(scenario.endsWith('after-scan'))await scanned();else {await ui.poll(III);scanConsent();}
    const previous=count('scan');
    await ui.poll({...III,preset:{number:328}});await tick();
    assert.equal(node('afx3existtarget').checked,false);assert.equal(node('afx3existscanmute').checked,false);
    assert.equal(node('afx3existread').disabled,true);await ui.scan();assert.equal(count('scan'),previous);
  }else if(scenario==='metadata-target-disagreement'||scenario==='metadata-scene-disagreement'){
    await ui.poll(III);scanConsent();assert.equal(node('afx3existread').disabled,false);
    if(scenario==='metadata-target-disagreement')statePreset=330;
    stateScene=2;
    await ui.poll(III);await tick();
    assert.equal(node('afx3existtarget').checked,false);assert.equal(node('afx3existscanmute').checked,false);
    assert.equal(node('afx3existread').disabled,true);await ui.scan();assert.equal(count('scan'),0);
    scanConsent();assert.equal(node('afx3existtarget').checked,false);await ui.scan();assert.equal(count('scan'),0);
    await ui.poll({...III,preset:{number:statePreset},scene:{number:stateScene}});await tick();
    assert.equal(node('afx3existtarget').checked,false);assert.equal(node('afx3existscanmute').checked,false);
    await ui.scan();assert.equal(count('scan'),0);
    scanConsent();await ui.scan();assert.equal(count('scan'),1);
    const body=calls.find(c=>c.path==='scan').body;
    assert.equal(body.expected_preset,statePreset);assert.equal(body.expected_scene,stateScene);
  }else if(scenario==='initial-metadata-disagreement'){
    statePreset=330;stateScene=2;await ui.poll(III);scanConsent();
    assert.equal(node('afx3existtarget').checked,false);assert.equal(node('afx3existscanmute').checked,false);
    await ui.scan();assert.equal(count('scan'),0);
  }else if(scenario==='scan-consent-revoked-while-waiting'){
    await ui.poll(III);const release=suspend('discard');ui.invalidate();await tick();
    scanConsent();const pending=ui.scan();node('afx3existtarget').checked=false;
    release();await pending;assert.equal(count('scan'),0);
  }else if(scenario==='sidebar-review-from-plan'){
    await prepared();assert.equal(context.currentPlan.afx3_ticket.stage,'plan');
    await bridge.restart('review');assert.equal(count('review'),1);
    assert.equal(context.currentPlan.afx3_ticket.stage,'review');assert.equal(context.stage,'review');
    bridge.renderConfirm();node('ack').checked=true;node('afx3muted').checked=true;
    await ui.arm();assert.equal(count('confirm'),1);assert.equal(context.currentPlan.afx3_ticket.stage,'confirm');
  }else if(scenario==='question'){
    await scanned();questionNext=true;node('prompt').value='Broaden this preset.';await ui.submit();
    assert.equal(context.currentPlan,null);assert.equal(node('prompt').value,'');assert.match(node('engage').textContent,/ANSWER/);
    node('prompt').value='Yes, Gain and Mid only.';await ui.submit();
    const body=calls.filter(c=>c.path==='plan').at(-1).body;
    assert.equal(body.prompt,'Broaden this preset.');assert.equal(body.answer,'Yes, Gain and Mid only.');assert.equal(count('send'),0);
  }else if(scenario==='confirm-consent'){
    await reviewed();node('ack').checked=true;await ui.arm();assert.equal(count('confirm'),0);
    node('ack').checked=true;node('afx3muted').checked=true;await ui.arm();assert.equal(count('confirm'),1);
    node('afx3muted').checked=false;bridge.consentChanged();assert.equal(node('apply').hidden,true);await ui.send();assert.equal(count('send'),0);
  }else if(scenario==='late-plan'){
    await scanned();node('prompt').value='More body.';const release=suspend('plan'),pending=ui.submit();await tick();
    await ui.poll({device:{active:'fm9'},preset:{number:1},scene:{number:1}});release();await pending;await tick();
    assert.equal(context.currentPlan,null);assert.equal(count('send'),0);
  }else if(scenario==='late-state'){
    const release=suspend('state'),pending=ui.poll(III);await tick();
    await ui.poll({device:{active:'fm9'},preset:{number:1},scene:{number:1}});release();await pending;
    assert.equal(node('afx3existingbox').hidden,true);assert.equal(count('scan'),0);
  }else if(scenario==='unsafe-result'){
    await armed();sendError=true;await ui.send();assert.equal(count('send'),1);assert.equal(context.currentPlan.afx3_ticket,null);
    assert.equal(node('storeafter').hidden,true);assert.match(node('afx3existingstatus').textContent,/muted/);
    assert.equal(announcements.at(-1).kind,'bad');assert.match(announcements.at(-1).text,/muted/);
  }else if(scenario==='arm-expiry'){
    await armed();for(let i=0;i<8;i++)timers.at(-1)();assert.equal(node('apply').hidden,true);assert.equal(count('send'),0);
    await bridge.restart('review');assert.equal(context.currentPlan.afx3_ticket.stage,'review');assert.equal(node('ack').checked,false);
  }else if(scenario==='legacy'){
    configured=false;await ui.poll(III);await context.submitRequest();assert.equal(legacyPolls,1);assert.equal(legacySubmits,1);
    assert.equal(count('plan'),0);assert.equal(node('afx3existingbox').hidden,true);
  }else if(scenario==='text-only'){
    await prepared();assert.equal(node('plancards').children.length,2);assert.equal(count('send'),0);
    assert.equal(node('plancards').children[0].children[3].textContent,'<script>not markup</script>');
  }else throw new Error('Unknown scenario');
  assert(calls.every(c=>!['apply','store','undo'].includes(c.path)));console.log('PASS',scenario);
})().catch(e=>{console.error(e);process.exitCode=1;});
