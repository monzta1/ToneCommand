// Execute the shipped reset functions without network, AI or device access.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const html=fs.readFileSync(process.env.TC_UI_FILE||path.join(__dirname,'../ui/index.html'),'utf8');
const script=html.split('<script>')[1].split('</script>')[0];
const actual=name=>{
  const match=script.match(new RegExp(`^function ${name}\\([^\\n]*\\)[ \\t]*\\{[\\s\\S]*?^\\}`,'m'));
  assert(match,`Missing shipped function ${name}`);return match[0];
};
const functions=['newDesignBusy','startNewDesign','discardPlan'].map(actual).join('\n');

function harness(){
  const calls=[],elements={};
  const get=id=>elements[id]||(elements[id]={value:'',hidden:false,checked:true,
    focus:()=>calls.push(['focus',id])});
  get('prompt').value='Unsent answer';
  const ctx=vm.createContext({
    $:get,chatBusy:false,srcWork:null,audioAnalysisBusy:false,planSending:false,
    chatLog:[{role:'user',content:'Previous request'}],chatReady:true,
    chatRequest:'Previous agreement',chatName:'Old name',chatScenes:['Old scene'],
    chatNeedsAnswer:true,chatStream:'Old partial reply',chatAgreedSeen:'Old agreement',
    currentPlan:{actions:[{kind:'set_param'}]},planRecipe:{old:true},workDone:{old:true},
    scenePreview:['Old scene'],lastState:{preset:{number:323,name:'TestPreset'}},
    requestMemory:{text:'Old request'},chatError:'Old error',lastPlanInput:{old:true},
    audioConversationSpec:{old:true},audioConversationNote:'Old measurements',
    srcAnswers:{scenes:4,name:'Old name'},CHAT_KEY:'chat',
    window:{confirm:()=>{calls.push(['confirm']);return true;}},
    localStorage:{removeItem:key=>calls.push(['remove',key])},
    disarmSend:()=>calls.push(['disarm']),clearAffected:()=>calls.push(['clearAffected']),
    setStage:name=>calls.push(['stage',name]),log:()=>{},
    renderScenes:state=>calls.push(['scenes',state]),renderChat:()=>calls.push(['renderChat']),
    growPrompt:()=>calls.push(['grow']),renderRequestWorkflow:()=>{},renderWorking:()=>{},
    updateRequestPreview:text=>calls.push(['preview',text]),
    setRequestOpen:(open,focus)=>{calls.push(['open',open]);if(focus)get('prompt').focus();},
    fetch:()=>{throw Error('Reset must not make network requests');}
  });
  vm.runInContext(functions,ctx);return {ctx,calls,get};
}

test('request screen has its own always-visible button and shared reset wiring',()=>{
  const pane=html.split('id="pane-request"')[1].split('id="pane-plan"')[0];
  assert.match(pane,/<button type="button" id="newdesign"[^>]*>NEW DESIGN<\/button>/);
  for(const id of ['newdesign','newrequest','cclear'])
    assert(script.includes(`$('${id}').onclick = startNewDesign;`));
  assert.doesNotThrow(()=>new vm.Script(script));
});

test('confirmed reset clears pending work and leaves live device state alone',()=>{
  const {ctx,calls,get}=harness(),before=JSON.stringify(ctx.lastState);
  assert.equal(ctx.startNewDesign(),true);
  assert.equal(ctx.chatLog.length,0);assert.equal(ctx.chatRequest,'');
  assert.equal(ctx.chatName,'');assert.equal(ctx.chatScenes.length,0);
  assert.equal(ctx.chatReady,false);assert.equal(ctx.chatNeedsAnswer,false);
  assert.equal(ctx.currentPlan,null);assert.equal(ctx.planRecipe,null);assert.equal(ctx.workDone,null);
  assert.equal(get('prompt').value,'');assert.equal(get('ack').checked,false);
  assert.equal(get('srcask').hidden,true);assert.equal(get('srcprogress').hidden,true);
  assert.equal(JSON.stringify(ctx.lastState),before);
  assert(calls.some(c=>c[0]==='disarm'));
  assert(calls.some(c=>c[0]==='stage'&&c[1]==='request'));
  assert(calls.some(c=>c[0]==='focus'&&c[1]==='prompt'));
  assert(calls.some(c=>c[0]==='remove'&&c[1]==='chat'));
  if(html.includes('let audioConversationSpec')){
    assert.equal(ctx.audioConversationSpec,null);assert.equal(ctx.audioConversationNote,'');
    assert.equal(ctx.lastPlanInput,null);assert.equal(ctx.requestMemory.text,'');
    assert.equal(get('muteack').checked,false);
  }else assert.equal(ctx.scenePreview,null);
});

test('cancelling confirmation preserves the draft, plan and conversation',()=>{
  const {ctx,calls,get}=harness();ctx.window.confirm=()=>false;
  const before=JSON.stringify([ctx.chatLog,ctx.currentPlan,ctx.lastState]);
  assert.equal(ctx.startNewDesign(),false);
  assert.equal(JSON.stringify([ctx.chatLog,ctx.currentPlan,ctx.lastState]),before);
  assert.equal(get('prompt').value,'Unsent answer');assert.deepEqual(calls,[]);
});

test('AI, source, send and supported audio busy states forbid resets',()=>{
  const states=['chatBusy','srcWork','planSending'];
  if(actual('newDesignBusy').includes('audioAnalysisBusy'))states.push('audioAnalysisBusy');
  for(const field of states){
    const {ctx,calls,get}=harness();ctx[field]=true;
    assert.equal(ctx.startNewDesign(),false,field);
    assert.equal(get('prompt').value,'Unsent answer');assert.equal(ctx.chatLog.length,1);
    assert.equal(calls.length,0,field);
  }
});

test('an already empty design needs no confirmation',()=>{
  const {ctx,calls,get}=harness();
  ctx.chatLog=[];ctx.currentPlan=null;get('prompt').value='';
  assert.equal(ctx.startNewDesign(),true);
  assert(!calls.some(c=>c[0]==='confirm'));
});
