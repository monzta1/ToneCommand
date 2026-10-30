/* One experimental manual edit in the existing stages. SEND is click-only. */
'use strict';
window.AFX3ReviewedEdit = (() => {
  const node=id=>document.getElementById(id);
  const tcText=(key,values={})=>window.TCLanguage?.t(key,values)??key.replace(/\{\{(\w+)\}\}/g,(_,k)=>String(values[k]??''));
  let metadata=null, busy=false, polling=false, dirty=false, generation=0, latestContext='';
  let invalidating=Promise.resolve();
  const active=()=>!!currentPlan?.afx3_edit;
  const ticket=()=>currentPlan?.afx3_ticket;
  const status=text=>{node('afx3editstatus').textContent=text;};
  function controls(){
    node('afx3prepare').disabled=busy||!metadata?.available;
    const blocked=busy||(typeof newDesignBusy==='function'&&newDesignBusy());
    for(const id of ['newrequest','newdesign']){const n=node(id);if(n)n.disabled=blocked;}
  }
  async function api(path,body){
    const r=await fetch('/api/axefx3/edit/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok)throw new Error(typeof d.error==='string'?d.error:typeof d.detail==='string'?d.detail:tcText("Reviewed edit refused. Prepare it again."));
    return d;
  }
  async function transition(path,body,revision=generation){
    await invalidating;
    if(revision!==generation)throw new Error(tcText("The device target changed. Prepare a new reviewed edit."));
    const value=await api(path,body);
    if(revision!==generation)throw new Error(tcText("The device target changed. Prepare a new reviewed edit."));
    return value;
  }
  function payload(consent=false){
    const v=ticket();if(!v)throw new Error(tcText("Prepare a new reviewed edit first."));
    const p={};for(const k of ['token','actions','plan_digest','expected_preset','expected_scene'])p[k]=structuredClone(v[k]);
    if(consent){p.target_confirmed=node('ack').checked;p.external_audio_muted=node('afx3muted').checked;}
    return p;
  }
  function clearConsent(){
    node('ack').checked=false;node('afx3muted').checked=false;disarmSend();node('armbtn').disabled=true;
  }
  async function run(work){
    if(busy)return;busy=true;controls();
    try{await work();}
    catch(e){clearConsent();status(e.message);log(e.message,'err');}
    finally{busy=false;controls();}
  }
  function lockCards(){
    document.querySelectorAll('#plancards input,#plancards select,#plancards button').forEach(n=>n.disabled=true);
    document.querySelectorAll('#plancards .reviewimpact').forEach(n=>n.textContent=tcText("Channel A; shared scenes may change"));
  }
  function display(v){
    const plan={...v,afx3_edit:true,afx3_ticket:structuredClone(v),actions:structuredClone(v.actions)};
    showPlan(plan);setStage('plan',true);lockCards();clearConsent();
    if(typeof renderReadOnlyBlocks==='function')renderReadOnlyBlocks(lastState);
    status(tcText("Proposal ready. Nothing has been sent."));
  }
  async function prepare(){
    return run(async()=>{
      if(!metadata?.available)throw new Error(tcText("This connection cannot prepare a reviewed Amp edit."));
      const v=await transition('prepare',{actions:[{kind:'set_param',block:'amp',instance:1,
        param:node('afx3control').value,value:Number(node('afx3value').value)}],
        expected_preset:metadata.preset,expected_scene:metadata.scene,whole_rig:false});
      display(v);if(typeof closeDrawer==='function')closeDrawer();
    });
  }
  async function review(){
    return run(async()=>{
      if(ticket()?.stage==='plan')currentPlan.afx3_ticket=await transition('review',payload());
      if(ticket()?.stage!=='review')throw new Error(tcText("Prepare and review the edit again."));
      stageDone.plan=true;setStage('review');lockCards();
    });
  }
  async function restart(destination){
    return run(async()=>{
      const old=payload();invalidate();
      const v=await transition('prepare',{actions:old.actions,expected_preset:old.expected_preset,expected_scene:old.expected_scene,whole_rig:false});
      display(v);
      if(destination==='review'){
        currentPlan.afx3_ticket=await transition('review',payload());
        stageDone.plan=true;setStage('review');lockCards();
      }
    });
  }
  function renderConfirm(){
    node('cintro').textContent=tcText("One reviewed edit on the Axe-Fx III.");
    node('acklabel').textContent=tcText("I reviewed the target and the shared-channel warning.");
    node('afx3mutewrap').hidden=false;
    node('apply').textContent=tcText("SEND TO AXE-FX III");
    const rows=[[tcText("TARGET"),`Axe-Fx III / Preset ${ticket()?.expected_preset} / Scene ${ticket()?.expected_scene}`],
      [tcText("SCOPE"),tcText("One Amp 1/channel A change")],[tcText("DESTINATION"),tcText("Edit buffer only; not stored")],
      [tcText("RECOVERY"),tcText("No automatic Undo")]];
    node('cfacts').replaceChildren();
    for(const [label,value] of rows){
      const box=document.createElement('div');box.className='cfact';
      const l=document.createElement('div');l.className='cfl';l.textContent=label;
      const v=document.createElement('div');v.className='cfv';v.textContent=value;box.append(l,v);node('cfacts').append(box);
    }
    node('cblast').textContent=tcText("Other scenes sharing Amp channel A may change. No measured loudness limit or automatic Undo.");
    renderGigLockWhy();clearConsent();
  }
  function consentChanged(){
    if(!node('ack').checked||!node('afx3muted').checked)disarmSend();
    node('armbtn').disabled=busy||gigOn===true||!ticket()||!node('ack').checked||!node('afx3muted').checked;
  }
  async function arm(){
    return run(async()=>{
      if(gigOn===true||!node('ack').checked||!node('afx3muted').checked)throw new Error(tcText("Confirm the target and external audio mute first."));
      if(ticket()?.stage!=='review')throw new Error(tcText("The review expired. Go back to Review for a fresh proposal."));
      currentPlan.afx3_ticket=await transition('confirm',payload(true));
      node('armbtn').hidden=true;node('apply').hidden=false;node('armhint').hidden=false;
      armLeft=8;node('apply').disabled=false;
      node('apply').textContent=tcText("SEND TO AXE-FX III")+' / '+armLeft;
      armTimer=setInterval(()=>{
        armLeft--;if(armLeft<=0){disarmSend();return;}
        node('apply').textContent=tcText("SEND TO AXE-FX III")+' / '+armLeft;
      },1000);
    });
  }
  async function send(){
    return run(async()=>{
      const body=payload(true);
      if(!body.target_confirmed||!body.external_audio_muted||ticket()?.stage!=='confirm')throw new Error(tcText("Confirm the target and external audio mute first."));
      currentPlan.afx3_ticket=null;disarmSend();node('apply').disabled=true;
      planSending=true;setStage('send',true);sendPhase(tcText("Sending one reviewed Axe-Fx III edit"));
      try{
        const out=await transition('send',body);
        if(!out.verified)throw new Error(tcText("The edit was not verified. Keep audio muted."));
        stageDone.send=true;planSent=out.sent?1:0;planTotal=1;
        planResult(esc(out.sent?tcText("Verified in the edit buffer. Nothing stored; no automatic Undo."):tcText("The value already matched. No write was needed.")),'ok');
        sendPhase(tcText("Axe-Fx III edit verified"));
        document.querySelectorAll('#plancards .plan-card').forEach(n=>n.classList.add('done'));
      }catch(e){
        planResult(esc(tcText("Transmission not confirmed. Keep audio muted. No retry or automatic Undo."))+' '+esc(e.message),'bad');
        sendPhase(tcText("Stopped. Inspect the device before continuing."));throw e;
      }finally{
        planSending=false;node('sendfoot').hidden=false;node('storeafter').hidden=true;
        node('auditionbtn').textContent=tcText("Back to live context");
        node('apply').disabled=true;clearConsent();
      }
    });
  }
  function invalidate(){
    if(!active())return;
    generation++;
    currentPlan.afx3_ticket=null;clearConsent();
    // Serialize invalidation before a new proposal. A slow old discard must
    // never delete a newer review or let an in-flight response restore it.
    invalidating=invalidating.catch(()=>{}).then(()=>api('discard',{}));
    void invalidating.catch(e=>status(e.message));
  }
  async function poll(s){
    const nextContext=JSON.stringify([s.device?.active,s.preset?.number,s.scene?.number]);
    if(nextContext!==latestContext){metadata=null;node('afx3editbox').hidden=true;controls();}
    latestContext=nextContext;
    if(active()&&ticket()&&(s.device?.active!=='axefx3'||s.preset?.number!==ticket().expected_preset||s.scene?.number!==ticket().expected_scene)){
      invalidate();status(tcText("The device target changed. Prepare a new reviewed edit."));
    }
    if(polling)return;polling=true;
    const context=latestContext;
    try{
      const previous=metadata;
      const value=s.device?.active==='axefx3'?await api('state'):null;
      if(context!==latestContext)return;  // A late response belongs to the old selection.
      metadata=value;
      if(metadata?.available&&(!dirty||previous?.preset!==metadata.preset||previous?.scene!==metadata.scene)){
        node('afx3value').value=metadata.values[node('afx3control').value];dirty=false;
      }
      node('afx3editbox').hidden=!metadata?.configured;
      if(metadata?.configured&&!metadata.available)status(metadata.reason||tcText("Reviewed Amp editing is unavailable on this connection."));
      controls();
    }catch(e){metadata=null;controls();status(e.message);}
    finally{polling=false;}
  }
  node('afx3prepare').onclick=prepare;
  node('afx3control').onchange=()=>{
    if(metadata?.values)node('afx3value').value=metadata.values[node('afx3control').value];
    dirty=false;invalidate();
  };
  node('afx3value').oninput=()=>{dirty=true;invalidate();};
  node('afx3muted').onchange=consentChanged;
  const railText=confirm=>confirm
    ?tcText("Confirm the exact target and external audio mute. Other scenes may share Amp channel A. No automatic Undo or measured loudness limit.")
    :tcText("Review this one edit before continuing. Nothing has been sent; other scenes may share Amp channel A.");
  function renderRail(){
    const show=!!currentPlan&&stage!=='request';
    for(const id of ['blastcard','preflightcard','reversecard'])node(id).hidden=!show;
    node('targetbody').textContent=`Axe-Fx III / Preset ${currentPlan?.device?.preset?.number} / Scene ${currentPlan?.device?.scene?.number}`;
    node('blastbody').textContent=tcText("Other scenes sharing Amp channel A may change.");
    node('preflightbody').textContent=railText(stage==='confirm');
    node('reversebody').textContent=tcText("Edit buffer only; nothing is permanently stored. No automatic Undo.");
  }
  const readonlyNote=()=>tcText("General controls remain read-only. This opt-in proposal edits only Amp 1/channel A Gain or Mid through REVIEW, CONFIRM and SEND. No Store or automatic Undo.");
  const completionNote=()=>tcText(". This edit stays unsaved. There is no automatic Undo.");
  return {active,working:()=>busy,prepare,review,restart,renderConfirm,consentChanged,arm,send,invalidate,poll,lockCards,renderRail,readonlyNote,completionNote};
})();
