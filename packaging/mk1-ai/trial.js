'use strict';
const el=id=>document.getElementById(id);
let plan=null,busy=false;
const stages=['requestStage','planStage','reviewStage','confirmStage','resultStage'];
function stage(index){stages.forEach((id,i)=>el(id).hidden=i!==index);
  document.querySelectorAll('.steps span').forEach((node,i)=>node.classList.toggle('active',i===index));}
function controls(){document.querySelectorAll('button,input,select,textarea').forEach(node=>node.disabled=busy);
  el('send').disabled=busy||!plan||!['targetConsent','muteConsent','experimentConsent'].every(id=>el(id).checked);}
function invalidate(){plan=null;for(const id of ['targetConsent','muteConsent','experimentConsent'])el(id).checked=false;controls();}
async function api(path,body){const response=await fetch('/api/'+path,body===undefined?{}:{method:'POST',
  headers:{'Content-Type':'application/json','X-ToneCommand':'1'},body:JSON.stringify(body)});
  let data;try{data=await response.json();}catch{throw new Error('Invalid TC response. Check state; do not automatically resend.');}
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Request refused. Nothing automatically retried.');
  return data;}
async function run(action){if(busy)return;busy=true;controls();el('messages').textContent='Working...';
  try{await action();el('messages').textContent='Ready.';}catch(error){el('messages').textContent=error.message;}
  finally{busy=false;controls();}}
async function read(){const state=await api('state');el('buildVersion').textContent=(state.version||'')+' | '+(state.source_commit||'development').slice(0,12)+(state.development?' | DEVELOPMENT / NOT VALIDATED | '+state.source_branch+' | '+(state.source_dirty?'MODIFIED':'clean')+' | source '+state.source_digest.slice(0,12):'');el('deviceStatus').textContent=state.connected?
  'MK1 connected | Preset '+state.preset+' | Scene '+state.scene+(state.uncertain?' | STOP: uncertain writes':''):'Not connected';}
el('saveSettings').onclick=()=>run(async()=>{invalidate();await api('settings',{backend:el('backend').value,
  model:el('aiModel').value,baseUrl:el('aiUrl').value,apiKey:el('aiKey').value});el('aiKey').value='';el('aiStatus').textContent='AI settings saved locally. No hardware action.';});
el('connect').onclick=()=>run(async()=>{invalidate();await api('connect',{});await read();});
el('disconnect').onclick=()=>run(async()=>{invalidate();await api('disconnect',{});await read();});
el('read').onclick=()=>run(read);
for(const id of ['prompt','target'])el(id).addEventListener('input',()=>{invalidate();stage(0);});
el('generate').onclick=()=>run(async()=>{invalidate();el('question').hidden=true;
  const target=Number(el('target').value);if(!el('target').value||!Number.isInteger(target)||target<0||target>511)throw new Error('Enter your own permitted empty test preset number first.');
  const result=await api('plan',{prompt:el('prompt').value,expected_preset:target});
  if(result.question){el('question').textContent='TONECOMMAND: '+result.question+'\nInclude your answer in YOUR REQUEST, then generate again.';el('question').hidden=false;stage(0);return;}
  plan=result;el('planSummary').textContent=result.design.summary;el('planRoute').textContent=result.routing;
  el('planBackend').textContent='AI: '+result.backend+' | '+(result.model||'configured default');
  el('design').textContent=JSON.stringify(result.design,null,2);
  el('actions').replaceChildren(...result.actions.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
  el('confirmTarget').textContent='Target: your MK1 preset '+result.target+' | '+result.design.name+' | scene 1 | NOT SAVED';stage(1);});
el('toReview').onclick=()=>stage(2);el('toConfirm').onclick=()=>stage(3);
el('edit').onclick=()=>{invalidate();stage(0);};
for(const id of ['targetConsent','muteConsent','experimentConsent'])el(id).onchange=controls;
el('send').onclick=()=>run(async()=>{
  if(!plan||!['targetConsent','muteConsent','experimentConsent'].every(id=>el(id).checked))throw new Error('Review and confirm all three conditions first.');
  const reviewed=plan;invalidate();stage(4);el('result').textContent='Sending once with readback. Keep monitoring muted.';
  try{const result=await api('send',{token:reviewed.token,expected_preset:reviewed.target,
    target_confirmed:true,external_audio_muted:true,experimental_mk1_consent:true});
    el('result').textContent=result.actions+' executor steps verified. Nothing stored.\n'+result.note;}
  catch(error){el('result').textContent='STOPPED. Partial edits may remain. Do not repeat SEND.\n'+error.message;throw error;}});
el('newRequest').onclick=()=>run(async()=>{invalidate();await api('discard',{});stage(0);});
el('report').onclick=()=>run(async()=>{const report=await api('report'),blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='MK1-AI-trial-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
stage(0);controls();run(async()=>{const info=await api('settings');
  if(info.settings?.backend)el('backend').value=info.settings.backend;
  el('aiModel').value=info.model||'';el('aiUrl').value=info.settings?.baseUrl||'';
  el('aiStatus').textContent=info.planning||'Choose your AI backend first.';await read();});
