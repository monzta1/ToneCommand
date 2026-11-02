/* Opt-in preserving edits in the original Request/Plan/Review/Confirm/Send UI. */
'use strict';
window.installAFX3Existing = () => {
  const node=id=>document.getElementById(id), legacy=window.AFX3ReviewedEdit;
  const t=(key)=>window.TCLanguage?.t(key)??key;
  let metadata=null, scanToken=null, busy=false, question=false, original='', generation=0;
  let polling=false, latest='', invalidating=Promise.resolve();
  const active=()=>!!currentPlan?.afx3_existing;
  const ticket=()=>currentPlan?.afx3_ticket;
  const status=text=>{node('afx3existingstatus').textContent=text;};
  const panel=document.createElement('div');panel.id='afx3existingbox';panel.hidden=true;panel.className='hint';
  const title=document.createElement('strong');title.textContent=t('Adjust this existing preset');
  const note=document.createElement('p');note.textContent=t('Read all eight scenes first. Keep the original chain, effects, models, controllers and levels. This experimental mode adjusts supported Gain/Mid settings only.');
  panel.append(title,note);
  for(const [id,label] of [['afx3existtarget','I confirm the current preset is the one to adjust.'],['afx3existscanmute','External speakers/headphones are muted and will remain muted during scene recalls and editing.']]){
    const line=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.id=id;
    line.append(input,document.createTextNode(' '+t(label)));line.style.display='block';panel.append(line);input.onchange=controls;
  }
  const scanButton=document.createElement('button');scanButton.id='afx3existread';scanButton.type='button';scanButton.textContent=t('READ ALL 8 SCENES');
  const message=document.createElement('p');message.id='afx3existingstatus';message.setAttribute('role','status');
  panel.append(scanButton,message);node('chat').before(panel);
  function controls(){
    scanButton.disabled=busy||!metadata?.available||!node('afx3existtarget').checked||!node('afx3existscanmute').checked;
    if(metadata?.configured){
      node('engage').disabled=busy||!metadata.available||!scanToken||!node('prompt').value.trim();
      node('engage').textContent=t(question?'SEND ANSWER':'SEND REQUEST');
    }
  }
  function clearConsent(){
    node('ack').checked=false;node('afx3muted').checked=false;disarmSend();node('armbtn').disabled=true;
  }
  async function api(path,body){
    const r=await fetch('/api/axefx3/existing/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();if(!r.ok)throw new Error(d.error||d.detail||t('Existing-preset operation refused.'));return d;
  }
  async function transition(path,body,revision=generation){
    await invalidating;if(revision!==generation)throw new Error(t('The context changed. Read the scenes again.'));
    const out=await api(path,body);
    if(revision!==generation)throw new Error(t('The context changed. Read the scenes again.'));return out;
  }
  async function run(work){
    if(busy)return;busy=true;controls();
    try{await work();}catch(e){clearConsent();status(e.message);log(e.message,'err');}
    finally{busy=false;controls();}
  }
  function invalidate(){
    generation++;scanToken=null;question=false;original='';
    if(active())currentPlan.afx3_ticket=null;clearConsent();
    invalidating=invalidating.catch(()=>{}).then(()=>api('discard',{}));
    void invalidating.catch(e=>status(e.message));controls();
  }
  async function scan(){return run(async()=>{
    if(!metadata?.available||!node('afx3existtarget').checked||!node('afx3existscanmute').checked)throw new Error(t('Confirm the target and external audio mute first.'));
    scanToken=null;question=false;original='';
    if(active())currentPlan.afx3_ticket=null;clearConsent();
    const out=await transition('scan',{expected_preset:metadata.preset,expected_scene:metadata.scene,target_confirmed:true,external_audio_muted:true});
    scanToken=out.scan_token;question=false;original='';
    status(t('All eight original scene maps read. Describe your adjustment below. Nothing stored; no physical limiter.'));
  });}
  function lockCards(){
    const container=node('plancards');container.replaceChildren();
    const plan=ticket()?.proposal??currentPlan?.afx3_proposal;
    for(const row of plan?.changes??[]){
      const card=document.createElement('div');card.className='plan-card';
      const heading=document.createElement('strong');heading.textContent=`Amp 1 / ${row.channel} / ${row.parameter}`;
      const values=document.createElement('p');values.textContent=`${Number(row.before).toFixed(2)} → ${Number(row.after).toFixed(2)} / ${row.model}`;
      const impact=document.createElement('p');impact.textContent=t('Shared-channel impact:')+' '+row.affected_scenes.join(', ');
      const reason=document.createElement('p');reason.textContent=row.reason;
      card.append(heading,values,impact,reason);container.append(card);
    }
  }
  function display(out){
    const p=out.proposal;
    const actions=p.changes.map(r=>({kind:'set_param',block:'amp',instance:1,param:r.parameter,value:r.after,reason:r.reason}));
    showPlan({...out,summary:p.summary,actions,afx3_edit:true,afx3_existing:true,
      afx3_proposal:structuredClone(p),afx3_ticket:structuredClone(out),
      device:{preset:{number:out.expected_preset,name:p.target.name},scene:{number:out.expected_scene}}});
    setStage('plan',true);lockCards();clearConsent();
    if(lastState.read_only)renderReadOnlyBlocks(lastState);
    status(t('Proposal ready. Review the exact changes and shared scenes before sending.'));
  }
  async function submit(){return run(async()=>{
    const said=node('prompt').value.trim();if(!said||!scanToken)throw new Error(t('Read all eight scenes before requesting an adjustment.'));
    const body={scan_token:scanToken,prompt:question?original:said};if(question)body.answer=said;else original=said;
    chatLog.push({role:'user',content:said});node('prompt').value='';growPrompt();renderChat();
    status(t('Preparing your existing-preset proposal. Nothing is being sent to the device.'));
    const out=await transition('plan',body);
    if(out.question){question=true;chatLog.push({role:'assistant',content:out.question});renderChat();status(out.question);return;}
    question=false;display(out);
  });}
  function payload(consent=false){
    if(!ticket())throw new Error(t('Prepare a fresh proposal first.'));
    const body={};for(const key of ['token','plan_digest','expected_preset','expected_scene'])body[key]=ticket()[key];
    if(consent){body.target_confirmed=node('ack').checked;body.external_audio_muted=node('afx3muted').checked;}return body;
  }
  async function review(){return run(async()=>{
    if(ticket()?.stage==='plan'||ticket()?.stage==='confirm')currentPlan.afx3_ticket=await transition('review',payload());
    if(ticket()?.stage!=='review')throw new Error(t('Prepare a fresh proposal first.'));
    stageDone.plan=true;setStage('review');lockCards();clearConsent();
  });}
  async function restart(destination){
    if(ticket()?.stage==='confirm'){await review();if(destination==='plan')setStage('plan');return;}
    clearConsent();setStage(destination);lockCards();
  }
  function renderConfirm(){
    node('cintro').textContent=t('Preserving adjustment of the existing Axe-Fx III preset.');
    node('acklabel').textContent=t('I reviewed the exact target, changes and shared-scene impacts.');
    node('afx3mutewrap').hidden=false;node('cfacts').replaceChildren();
    for(const [label,value] of [['TARGET',`Preset ${ticket()?.expected_preset} / Scene ${ticket()?.expected_scene}`],
      ['SCOPE',`${ticket()?.proposal.changes.length} scalar changes / 8 original scenes`],['DESTINATION','Edit buffer only; not stored'],['RECOVERY','No automatic Undo']]){
      const box=document.createElement('div');box.className='cfact';const l=document.createElement('div');l.className='cfl';l.textContent=t(label);
      const v=document.createElement('div');v.className='cfv';v.textContent=t(value);box.append(l,v);node('cfacts').append(box);
    }
    node('cblast').textContent=t('Original scene assignments and all unrequested settings stay unchanged. Shared channels affect every listed scene. No physical limiter.');
    renderGigLockWhy();clearConsent();
  }
  function consentChanged(){
    if(!node('ack').checked||!node('afx3muted').checked)disarmSend();
    node('armbtn').disabled=busy||gigOn===true||!ticket()||!node('ack').checked||!node('afx3muted').checked;
  }
  async function arm(){return run(async()=>{
    if(gigOn===true||!node('ack').checked||!node('afx3muted').checked)throw new Error(t('Confirm the target and external audio mute first.'));
    currentPlan.afx3_ticket=await transition('confirm',payload(true));
    node('armbtn').hidden=true;node('apply').hidden=false;node('apply').disabled=false;armLeft=8;
    node('apply').textContent=t('SEND TO AXE-FX III')+' / '+armLeft;
    armTimer=setInterval(()=>{armLeft--;if(armLeft<=0){disarmSend();return;}node('apply').textContent=t('SEND TO AXE-FX III')+' / '+armLeft;},1000);
  });}
  async function send(){return run(async()=>{
    const body=payload(true);if(ticket().stage!=='confirm'||!body.target_confirmed||!body.external_audio_muted)throw new Error(t('Confirm the target and external audio mute first.'));
    currentPlan.afx3_ticket=null;disarmSend();planSent=0;planTotal=currentPlan.afx3_proposal.changes.length;
    planSending=true;setStage('send',true);sendPhase(t('Verifying original scenes and applying the reviewed scalar changes'));
    let verified=false;
    try{
      const out=await transition('send',body);if(!out.verified)throw new Error(t('Execution not independently verified.'));
      stageDone.send=true;planSent=out.sent;planTotal=currentPlan.afx3_proposal.changes.length;
      verified=true;
      planResult(esc(t('Requested changes and all eight original scene maps verified. Nothing stored; no automatic Undo.')),'ok');
      sendPhase(t('Existing preset verified'));scanToken=null;
    }catch(e){planResult(esc(t('Stopped. Keep external audio muted; no retry or automatic Undo.'))+' '+esc(e.message),'bad');throw e;}
    finally{
      planSending=false;node('sendfoot').hidden=false;node('storeafter').hidden=true;node('apply').disabled=true;clearConsent();
      workAnnounce(verified?`${planSent} `+t('changes verified. Nothing stored.'):
        t('Stopped. Keep external audio muted; inspect before reconnecting.'),verified?'ok':'bad');
    }
  });}
  function renderRail(){
    for(const id of ['blastcard','preflightcard','reversecard'])node(id).hidden=false;
    node('targetbody').textContent=`Axe-Fx III / Preset ${currentPlan?.device?.preset?.number}`;
    node('blastbody').textContent=t('Every listed shared-channel scene is affected.');
    node('preflightbody').textContent=t('Original scenes and complete state are rechecked before SEND. External mute is required.');
    node('reversebody').textContent=t('Edit buffer only; no Store or automatic Undo.');
  }
  async function poll(s){
    const key=JSON.stringify([s.device?.active,s.preset?.number,s.scene?.number]);
    if(latest&&key!==latest&&(scanToken||ticket()))invalidate();
    if(key!==latest){metadata=null;panel.hidden=true;controls();}latest=key;
    if(polling||busy)return;polling=true;
    try{
      const value=s.device?.active==='axefx3'?await api('state'):null;
      if(key!==latest)return;metadata=value;
      panel.hidden=!metadata?.configured;
      if(metadata?.configured){node('afx3editbox').hidden=true;if(!metadata.available)status(metadata.reason);}
      if(!metadata?.configured&&!active())void legacy.poll(s);
      controls();
    }catch(e){metadata=null;controls();status(e.message);}
    finally{polling=false;}
  }
  scanButton.onclick=scan;
  const previousSubmit=submitRequest;
  submitRequest=()=>metadata?.configured?submit():previousSubmit();node('engage').onclick=submitRequest;
  node('prompt').addEventListener('input',controls);
  node('afx3muted').onchange=()=>active()?consentChanged():legacy.consentChanged();
  const methods={prepare:submit,review,restart,renderConfirm,consentChanged,arm,send,invalidate,poll,
    lockCards,renderRail,readonlyNote:()=>t('Preserving existing-preset mode: supported Gain/Mid only, all other settings unchanged.'),
    completionNote:()=>t('. Edit buffer only; nothing stored and no automatic Undo.')};
  const delegated={active:()=>active()||legacy.active(),poll};
  for(const key of Object.keys(methods))if(key!=='poll')delegated[key]=(...args)=>active()?methods[key](...args):legacy[key](...args);
  window.AFX3ReviewedEdit=delegated;
  return {active,scan,submit,review,arm,send,poll,invalidate,controls};
};
