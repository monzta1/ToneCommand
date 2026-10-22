'use strict';
const tcText=(key,values={})=>window.TCLanguage?.t(key,values)??key.replace(/\{\{(\w+)\}\}/g,(_,name)=>String(values[name]??''));
const viewIds={planPanel:'pane-plan',review:'pane-review',confirmPanel:'pane-confirm',result:'pane-send',generate:'engage',toReview:'reviewbtn',toConfirm:'toconfirm',send:'apply'};
const el=id=>document.getElementById(viewIds[id]||id);
let state=null, proposal=null, busy=false;
let audioReference=null;
let audioReferenceKey='';
let namAccount=null,namSelection=null,namPreview=null;
let namSlots=null;
let storePreview=null;
let currentStage=0;
let routeExploration=null;
let navigationPreview=null,presetLibrary=[];
let refineContext=null,adjusting=false;
let intakeResolution={},intakeSceneCount=null;
let dialogueToken=null,dialogueQuestions=[],dialogueAnswers={},lastDialogueRoute='';
const dialogueHistory=document.createElement('div');dialogueHistory.id='dialogueHistory';dialogueHistory.hidden=true;
el('conversation').after(dialogueHistory);
const intakePanel=document.createElement('section');intakePanel.id='requestQuestions';intakePanel.hidden=true;
intakePanel.setAttribute('aria-label',tcText("Clarify your request"));
el('routeOptionsPanel').before(intakePanel);
function resetDialogue(){dialogueToken=null;dialogueQuestions=[];dialogueAnswers={};lastDialogueRoute='';dialogueHistory.replaceChildren();dialogueHistory.hidden=true;
  if(intakePanel.querySelector('[data-ai-answer]')){intakePanel.replaceChildren();intakePanel.hidden=true;}}
function resetIntake(){resetDialogue();intakeResolution={};intakeSceneCount=null;intakePanel.replaceChildren();intakePanel.hidden=true;}
function dialoguePayload(){return state?.ai_clarification_supported?{dialogue_token:dialogueToken,
  answers:dialogueQuestions.map(q=>({id:q.id,text:dialogueAnswers[q.id]||''}))}:{};}
function receiveDialogue(result){
  if(!Object.hasOwn(result,'dialogue_token'))return;
  dialogueToken=result.dialogue_token;dialogueAnswers={};
  dialogueQuestions=result.needs_clarification?(result.intake.questions||[]).filter(q=>q.kind==='answer'):[];
  dialogueHistory.replaceChildren();
  for(const turn of result.dialogue_history||[]){
    if(!turn.answers?.length)continue;
    const question=document.createElement('p');question.className='cmsg';
    question.textContent='TONECOMMAND: '+turn.message+'\n'+turn.questions.map(q=>q.text).join('\n');dialogueHistory.append(question);
    const answer=document.createElement('p');answer.className='cmsg';
    answer.textContent='YOU: '+turn.answers.map(a=>a.text).join('\n\n');dialogueHistory.append(answer);
  }
  dialogueHistory.hidden=!dialogueHistory.childElementCount;
  if(!dialogueHistory.hidden){el('conversationPanel').hidden=false;el('emptyConversation').hidden=true;}
  if(!result.needs_clarification)intakePanel.hidden=true;
}
function showIntake(result){
  intakeSceneCount=result.scenes;el('scenes').value=String(result.scenes);
  intakePanel.replaceChildren();intakePanel.hidden=result.ready;
  if(result.ready)return;
  stage(0);proposal=null;
  const title=document.createElement('h2');title.textContent=result.questions.some(q=>q.kind==='answer')?tcText("TONECOMMAND HAS A QUESTION"):tcText("CLARIFY BEFORE TC BUILDS THE PLAN");intakePanel.append(title);
  if(result.message){const message=document.createElement('p');message.textContent=result.message;intakePanel.append(message);}
  for(const question of result.questions){
    const row=document.createElement('label');row.className='intake-question';row.append(document.createTextNode(question.text+' '));
    if(question.kind==='answer'){
      const input=document.createElement('textarea');input.rows=3;input.maxLength=2000;input.dataset.aiAnswer=question.id;
      input.setAttribute('aria-label',question.text);input.placeholder=tcText("Your answer or adjustment...");input.value=dialogueAnswers[question.id]||'';
      input.oninput=()=>{dialogueAnswers[question.id]=input.value;invalidate();};row.append(input);
      for(const suggestion of question.suggestions||[]){const button=document.createElement('button');button.type='button';button.textContent=suggestion;
        button.onclick=event=>{event.preventDefault();input.value=suggestion;dialogueAnswers[question.id]=suggestion;invalidate();input.focus();};row.append(button);}
    }else if(question.kind==='choice'){
      const select=document.createElement('select');select.dataset.intake=question.id;select.append(new Option(tcText("Choose what you mean"),''));
      for(const option of question.options)select.append(new Option(option.label,option.value));
      select.value=intakeResolution[question.id]||'';
      select.onchange=()=>{intakeResolution[question.id]=select.value||null;invalidate();};row.append(select);
    }else if(question.kind==='omission'){
      const input=document.createElement('input');input.type='checkbox';input.dataset.intake=question.id;
      input.checked=(intakeResolution.accepted_omissions||[]).includes(question.id);
      input.onchange=()=>{const chosen=new Set(intakeResolution.accepted_omissions||[]);input.checked?chosen.add(question.id):chosen.delete(question.id);
        intakeResolution.accepted_omissions=[...chosen];invalidate();};
      row.prepend(input);row.append(document.createTextNode(tcText(" Yes, defer this part.")));
    }else if(question.kind==='scenes'){
      const select=document.createElement('select');select.dataset.intake='scene_count';select.append(new Option(tcText("Choose the scene count explicitly"),''));
      for(let n=1;n<=8;n++)select.append(new Option(String(n),String(n)));
      select.onchange=()=>{if(!select.value)return;el('scenes').value=select.value;intakeSceneCount=Number(select.value);intakeResolution.scene_count_override=true;invalidate();};row.append(select);
    }
    intakePanel.append(row);
  }
  const hint=document.createElement('p');hint.textContent=tcText("Your original request is preserved. TC will not build an incomplete plan without your choice. Nothing is sent.");intakePanel.append(hint);
  const next=document.createElement('button');next.type='button';next.textContent=result.questions.some(q=>q.kind==='answer')?tcText("SEND ANSWER"):tcText("CONTINUE WITH MY ANSWERS");next.onclick=()=>el('generate').click();intakePanel.append(next);
  intakePanel.scrollIntoView({block:'nearest'});note(result.questions.some(q=>q.kind==='answer')?
    tcText("ToneCommand is waiting for your answer. Fill in the empty field and click SEND ANSWER; Enter inserts a new line."):
    tcText("TC is waiting for your clarification. It will then prepare a proposal only."));
}
async function ensureIntake(mode){
  if(dialogueQuestions.some(q=>!dialogueAnswers[q.id]?.trim())){
    note(tcText("Answer ToneCommand's pending question and click SEND ANSWER. Your request is preserved."));
    intakePanel.scrollIntoView({block:'nearest'});return false;
  }
  if(!state?.request_intake_supported)return true;
  const result=await api('intake',{prompt:el('prompt').value,expected_preset:state.preset,mode,scenes:Number(el('scenes').value),
    resolution:intakeResolution,refining:adjusting,wah_source:el('wah').value||null});
  if(!result.ready||!dialogueQuestions.length)showIntake(result);return result.ready;
}
const ampRefreshButton=document.createElement('button');ampRefreshButton.id='ampRefresh';ampRefreshButton.textContent='REFRESH AMP MODELS';
const ampRefreshStatus=document.createElement('p');ampRefreshStatus.id='ampRefreshStatus';ampRefreshStatus.setAttribute('role','status');
const ampChanges=document.createElement('ul');ampChanges.id='ampChanges';ampChanges.style.maxHeight='200px';ampChanges.style.overflow='auto';ampChanges.hidden=true;
el('ampCount').after(ampRefreshButton,ampRefreshStatus,ampChanges);
const intentPanel=document.createElement('section');intentPanel.id='sceneIntent';intentPanel.hidden=true;
el('controllerChoice').after(intentPanel);
const comparisonPanels=['pane-plan','pane-review'].map((id,index)=>{
  const panel=document.createElement('section');panel.id=index?'sceneComparisonReview':'sceneComparison';panel.hidden=true;
  panel.setAttribute('aria-label',tcText("Review of planned tone differences"));
  el(id).querySelector('.stagecard').prepend(panel);return panel;
});
const refineButton=document.createElement('button');refineButton.id='refineSound';refineButton.textContent=tcText("REFINE AFTER LISTENING");refineButton.hidden=true;
el('returnRequest').after(refineButton);
const adjustPanel=document.createElement('fieldset');adjustPanel.id='adjustScenes';adjustPanel.hidden=true;
el('requestOptions').after(adjustPanel);
const comparisonPanel=document.createElement('details');comparisonPanel.id='audioComparePanel';comparisonPanel.hidden=true;
comparisonPanel.innerHTML="<summary>COMPARE RECORDING</summary><p>Compare your recorded guitar passage with the reference in SONG / AUDIO or your request. Use the same passage and comparable picking. This is not an automatic tone score.</p><label>Your recording <input id=\"recordingFile\" type=\"file\" accept=\"audio/*\"></label><label>Start (seconds) <input id=\"recordingStart\" type=\"number\" min=\"0\" max=\"86400\" step=\"0.25\" value=\"0\"></label><label>Length (up to 60 seconds) <input id=\"recordingLength\" type=\"number\" min=\"0.25\" max=\"60\" step=\"0.25\" value=\"20\"></label><button id=\"compareAudio\">COMPARE SEGMENTS</button><p id=\"comparisonStatus\" role=\"status\">Local analysis only; no recording, playback, AI call or transmission to the Fractal.</p><div id=\"comparisonResults\"></div>";
el('rightrail').prepend(comparisonPanel);
function clearAudioComparison(){el('comparisonResults').replaceChildren();el('comparisonStatus').textContent=tcText("Source or recording changed. Compare the segments again.");}
for(const id of ['recordingFile','recordingStart','recordingLength'])el(id).addEventListener('input',clearAudioComparison);
function enterRefinement(){
  if(!refineContext)return;
  resetIntake();
  adjusting=true;invalidate();el('buildRoute').value=refineContext.mode;
  el('scenes').value=String(refineContext.count);el('prompt').value='';
  adjustPanel.replaceChildren();const legend=document.createElement('legend');legend.textContent=tcText("Which scenes should change? Other scene settings remain protected.");adjustPanel.append(legend);
  for(let n=1;n<=refineContext.count;n++){
    const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=String(n);
    input.addEventListener('change',invalidate);label.append(input,document.createTextNode(` Scene ${n} `));adjustPanel.append(label);
  }
  adjustPanel.hidden=false;el('generate').textContent=tcText("PROPOSE ADJUSTMENT");
  el('requestPanel').open=true;stage(0);controls();el('prompt').focus();
  note(tcText("Describe what you hear and what should change. Select scenes. For FW33 AMP/CAB, select scene 1 first; confirm again before SEND."));
}
refineButton.onclick=()=>{if(!busy)enterRefinement();};
function clearRouteExploration(){routeExploration=null;el('buildRoute').value=adjusting&&refineContext?refineContext.mode:'';el('routeOptions').replaceChildren();el('routeReason').textContent=adjusting?tcText("Keep the existing build route for this listening adjustment."):tcText("Enter your request and click GENERATE PLAN. TC explores the routes first; NAM is not selected automatically.");}
const note=text=>{el('status').textContent=text;};
const stageNames=['request','plan','review','confirm','send'];
const stagePanes=['pane-request','planPanel','review','confirmPanel','result'];
// Keep source intent compact beside the upstream-style request controls.
const sourceLabel=document.createElement('label');sourceLabel.textContent=tcText("Source ");
const sourceKind=document.createElement('select');sourceKind.id='sourceKind';
sourceKind.append(new Option(tcText("Sound reference / plain request"),'tone'),new Option(tcText("Rig explanation / equipment video"),'rig'));
sourceLabel.append(sourceKind);el('requestPanel').querySelector('.formbar').prepend(sourceLabel);
sourceLabel.hidden=true;
const modeLabel=document.createElement('label');modeLabel.textContent='Rigvertaling ';
const rigMode=document.createElement('select');rigMode.id='rigMode';
rigMode.append(new Option('Dichtstbijzijnde benadering','closest'),new Option('Getrouwe routing (weigert beperkingen)','faithful'),new Option('Vereenvoudigde live-rig','simplified'));
modeLabel.append(rigMode);modeLabel.hidden=true;sourceLabel.after(modeLabel);
sourceKind.onchange=()=>{resetIntake();modeLabel.hidden=sourceKind.value!=='rig';audioReference=null;invalidate();
  clearRouteExploration();controls();
  el('audioStatus').textContent=sourceKind.value==='rig'?tcText("Equipment explanations are read; speech is not measured as guitar tone."):tcText("A linked sound reference is measured locally.");};
rigMode.onchange=invalidate;
const captureLabel=document.createElement('label');captureLabel.textContent='Geinstalleerde NAM ';
const captureSlot=document.createElement('select');captureSlot.id='namBuildSlot';
captureSlot.append(new Option(tcText("Keep current NAM"),''));
captureLabel.append(captureSlot);modeLabel.after(captureLabel);captureLabel.hidden=true;
captureSlot.onchange=invalidate;
function stage(index){
  currentStage=index;document.body.dataset.stage=stageNames[index];
  stagePanes.forEach((id,i)=>{el(id).hidden=i!==index;});
  document.querySelectorAll('#rail .stg').forEach((step,i)=>{
    const available=i===0||(i<4&&!!proposal)||(i===4&&!proposal&&!!el('resultText').textContent.trim());
    step.disabled=busy||!available;step.classList.toggle('on',i===index);step.classList.toggle('avail',available);
    if(i===index)step.setAttribute('aria-current','step');else step.removeAttribute('aria-current');
  });
  el('navTitle').textContent=stageNames[index].toUpperCase();
  el('navHelp').textContent=[tcText("Tell TC what you want."),tcText("Proposal only; nothing sent yet."),tcText("Review all changes."),tcText("Confirm the target and external audio muting."),tcText("Transmission result.")][index];
}
function controls(){
  historyControls();
  comparisonPanel.hidden=state?.audio_analysis_version!==2;
  for(const id of ['compareAudio','recordingFile','recordingStart','recordingLength'])el(id).disabled=busy;
  ampRefreshButton.disabled=busy||!state?.connected||!state?.amp_refresh_supported;
  el('target').disabled=busy||!state?.connected||!state?.navigation_supported;
  const switchingDevice=el('deviceChoice').value==='fm9';
  el('connectDevice').textContent=switchingDevice?'OPEN FM9':state?.connected?'CONNECTED':tcText("CONNECT");
  el('connectDevice').classList.toggle('linked',!!state?.connected&&!switchingDevice);
  el('connectDevice').title=switchingDevice?tcText("Open the FM9 interface after releasing the FX3 MIDI port."):state?.connected?`Axe-Fx III | ${state.firmware}`:tcText("Connect to the Fractal");
  el('navigationSelect').disabled=busy||!navigationPreview||!el('navigationMute').checked||(navigationPreview.kind==='preset'&&!el('navigationDiscard').checked);
  for(const button of el('sceneRack').querySelectorAll('button'))button.disabled=busy||!state?.navigation_supported;
  const chooseRoute=!!state?.route_options_supported;
  el('routeOptionsPanel').hidden=!chooseRoute;
  el('exploreRoutes').disabled=busy||adjusting||!state?.connected||!el('prompt').value.trim();
  el('buildRoute').disabled=busy||adjusting||!routeExploration;
  const sourceSupported=!!state?.source_support?.rig_reader;
  sourceLabel.hidden=!sourceSupported;modeLabel.hidden=!sourceSupported||sourceKind.value!=='rig';
  if(!sourceSupported){sourceKind.value='tone';rigMode.value='closest';}
  sourceKind.disabled=busy;rigMode.disabled=busy;
  const serial=el('buildRoute').value==='serial';
  const album=el('buildRoute').value==='amp'&&!!state?.album_build_supported;
  const albumCounts=state?.album_scene_counts?.length?state.album_scene_counts:[8];
  const albumCountText=albumCounts.length===1&&albumCounts[0]===8?'acht':albumCounts.length===8&&albumCounts.every((n,i)=>n===i+1)?'1-8':albumCounts.join('/');
  el('buildRoute').querySelector('option[value="amp"]').textContent=state?.album_build_supported?tcText("AMP / CAB: {{v0}} scenes with tone goals", {v0:(albumCountText)}):'AMP / CAB + pedals';
  const serialOption=el('buildRoute').querySelector('option[value="serial"]');
  serialOption.hidden=!state?.serial_build_supported;
  serialOption.disabled=!state?.serial_build_supported||sourceKind.value==='rig';
  captureLabel.hidden=!state?.nam_selection_supported||(state?.route_options_supported&&el('buildRoute').value!=='nam');
  captureSlot.disabled=busy||!state?.nam_selection_supported;
  for(const id of ['refresh','generate','cabImport','prompt','scenes','wah','cabKind','cabFile','discard','variant','deviceChoice','connectDevice','newDesign','audioFile','audioStart','audioLength','namQuery','namFormat','namSearch','namLogin','namWithRequest','editRequest','toReview','backPlan','toConfirm','backReview','returnRequest']) el(id).disabled=busy;
  el('connectDevice').disabled=busy||(!!state?.connected&&!switchingDevice);
  el('wahMode').disabled=busy||!el('wah').value;
  const fw33=state?.firmware==='33.00-beta.20261006';
  const awaitingRoute=chooseRoute&&!el('buildRoute').value&&!adjusting;
  const ampAvailable=awaitingRoute&&!!state?.album_build_supported;
  const maxScenes=album||ampAvailable?Math.max(...albumCounts):serial?1:fw33?(state.route?.length?2:1):state?.multiscene_planning_supported?8:4;
  for(const option of el('scenes').options)option.disabled=album||ampAvailable?!albumCounts.includes(Number(option.value)):Number(option.value)>maxScenes;
  if(intakeSceneCount===null){
    if((album||ampAvailable)&&!albumCounts.includes(Number(el('scenes').value)))el('scenes').value=String(albumCounts[0]);
    if(Number(el('scenes').value)>maxScenes)el('scenes').value=String(maxScenes);
  }
  el('requestOptionsSummary').textContent=tcText("DESIGN OPTIONS: {{v0}} SCENE(S), SOURCE AND CONTROLLERS", {v0:(el('scenes').value)});
  el('generate').disabled=busy||el('deviceChoice').value!=='axefx3'||!state?.connected||!!state.route_problem||(!fw33&&!state.cab_count);
  if((serial||album)&&state?.scene!==1)el('generate').disabled=true;
  const chosenRoute=routeExploration?.routes.find(r=>r.mode===el('buildRoute').value);
  if(chooseRoute&&!adjusting&&chosenRoute&&!chosenRoute.enabled)el('generate').disabled=true;
  el('generate').textContent=adjusting?tcText("PROPOSE ADJUSTMENT"):chooseRoute&&routeExploration&&!chosenRoute?'CHOOSE ROUTE':'GENERATE PLAN';
  if(!intakePanel.hidden)el('generate').textContent=tcText("CONTINUE WITH MY ANSWERS");
  if(dialogueQuestions.length)el('generate').textContent=tcText("SEND ANSWER");
  el('requestNext').textContent=busy?tcText("TC is busy. Your request is preserved; wait for the result."):
    !state?.connected?tcText("Connect the Fractal first; nothing is sent automatically."):
    switchingDevice?tcText("Click OPEN FM9 to open the selected device interface."):
    state.route_problem?state.route_problem:
    !fw33&&!state.cab_count?tcText("Import an available cab name list through CAB LIBRARY first."):
    (serial||album)&&state.scene!==1?tcText("Select scene 1 in the scene strip first. This does not store unsaved preset changes."):
    adjusting?tcText("Select scenes and describe your listening feedback. The button creates a new proposal only."):
    chooseRoute&&!routeExploration?tcText("Start with your request and GENERATE PLAN. TC explores the routes, then asks for your choice."):
    chooseRoute&&!chosenRoute?tcText("TC is waiting for your build route. Click CHOOSE ROUTE or open CHOOSE BUILD ROUTE."):
    chosenRoute&&!chosenRoute.enabled?chosenRoute.reason:
    tcText("Next: GENERATE PLAN creates a proposal for {{v0}} scene(s). REVIEW and CONFIRM come before SEND.", {v0:(el('scenes').value)});
  if(adjusting){el('scenes').disabled=true;el('wah').disabled=true;el('wahMode').disabled=true;sourceKind.disabled=true;captureSlot.disabled=true;}
  refineButton.hidden=!refineContext;refineButton.disabled=busy;
  for(const input of adjustPanel.querySelectorAll('input'))input.disabled=busy;
  for(const input of intakePanel.querySelectorAll('input,select,textarea,button'))input.disabled=busy;
  for(const id of ['namSaveKey','namDisconnect','namSuggest','namKey'])el(id).disabled=busy;
  el('namSlotsRefresh').disabled=busy||!namAccount?.installation_supported||!state?.connected;
  el('namSlot').disabled=busy||!namSlots;
  el('namInstallPrepare').disabled=busy||!namSelection?.model||!namAccount?.installation_supported||!state?.connected||!namSlots||!el('namSlot').value;
  el('namInstallCommit').disabled=busy||!namPreview||!el('namInstallMute').checked||!el('namInstallFlash').checked||!el('namInstallOverwrite').checked;
  const wahSupported=!fw33||(album&&state?.wah_planning_supported);
  el('wah').disabled=busy||!wahSupported||adjusting; if(!wahSupported)el('wah').value='';
  el('wahMode').disabled=busy||!wahSupported||adjusting||!el('wah').value;
  el('storePrepare').disabled=busy||!fw33||!state?.connected;
  el('storeCommit').disabled=busy||!storePreview||!el('storeMute').checked||!el('storeFlash').checked;
  el('send').disabled=busy||currentStage!==3||el('deviceChoice').value!=='axefx3'||!proposal||!el('confirmed').checked||!el('muted').checked;
  stage(currentStage);
  el('controllerHint').textContent=awaitingRoute?tcText("Choose AMP/CAB or NAM after the route advice. Scene count and controls depend on that route and the verified device profile."):album?tcText("FW33: {{v0}} scenes, up to four amp voices/four cab channels A-D. Delay/Chorus share A; Output -18dB. Start on scene 1. {{v1}}", {v0:(albumCountText), v1:(state.wah_planning_supported?tcText("Wah Cry Babe with External 1/2 and Off/Fast Pos is available. An explicit binding in your text is also used. Preserve without an existing wah binding means Auto Engage Off, not automatic engagement."):tcText("New wah controller bindings are unavailable for this profile."))}):serial?tcText("Measured AMP/CAB test chain: scene 1/A only. Models are retained and reserve blocks stay bypassed. No new controllers."):fw33?tcText("FW33 NAM: first build one scene from empty; then up to two with NAM A/B. New controller bindings are not yet verified for this profile."):!el('wah').value?tcText("An explicit wah binding in your text is used if the build route supports it. Otherwise an existing binding is preserved."):
    el('wahMode').value==='Fast Pos'?tcText("Fast Pos: moving the pedal can engage Wah even in a scene where Wah is off. Choose Off for scene-controlled bypass."):
    el('wahMode').value==='Off'?tcText("Off: the pedal controls the wah filter position but does not automatically engage or bypass Wah."):
    tcText("The existing Auto Engage mode is preserved. A new binding uses the device default; check its behavior.");
  if(!fw33&&state?.multiscene_planning_supported)el('controllerHint').textContent+=tcText(" Up to eight scenes, with at most four different settings per block. Matching settings share channels; bypass and output level can distinguish rhythm and solo.");
  if(album&&state?.wah_planning_supported)el('controllerHint').textContent+=tcText(" Fast Pos can override scene bypass through pedal movement; Off uses scene-controlled bypass. Global CC mapping stays on your device.");
  if(fw33&&state?.firmware_migration?.wah_controller_workspace){
    el('controllerHint').textContent=el('controllerHint').textContent.replace(tcText("New controller bindings are not yet verified for this profile."),tcText("This NAM build route does not create new controller bindings."));
    el('controllerHint').textContent+=state?.wah_planning_supported&&album?tcText(" Wah 1/2 can also be bound separately through CONTROLLERS. Raising pitch is a different function."):tcText(" Wah 1/2 can be bound separately through CONTROLLERS. This build route does not create the binding itself.");
  }
}
function invalidate(){proposal=null;stage(0);el('confirmed').checked=el('muted').checked=false;
  el('rigReport').hidden=true;
  clearNamPreview();
  storePreview=null;el('storeMute').checked=el('storeFlash').checked=false;el('storeSummary').textContent='';
  el('requestPreview').textContent=el('prompt').value.slice(0,160)+(el('prompt').value.length>160?'...':'');controls();}
async function api(name,body,prefix='/api/axefx3/'){
  let r,data;
  try{r=await fetch(prefix+name,body===undefined?{headers:{'X-ToneCommand':'1'}}:{method:'POST',headers:{'Content-Type':'application/json','X-ToneCommand':'1'},body:JSON.stringify(body)});}
  catch(e){
    if(state)state={...state,connected:false};
    throw new Error(tcText("No response from TC. Check the connection and use RESCAN. Your request is preserved. After a transmission, check device state first; do not automatically resend."));
  }
  try{data=await r.json();}catch(e){
    if(state)state={...state,connected:false};
    throw new Error(tcText("TC returned an invalid response. Use RESCAN to check state. Your request is preserved. Do not automatically resend."));
  }
  if(!data||typeof data!=='object'||Array.isArray(data)){
    if(state)state={...state,connected:false};
    throw new Error(tcText("TC returned an invalid response. Check state with RESCAN; do not automatically resend."));
  }
  if(!r.ok&&data.detail?.code==='dialogue_stale'){
    const draft=dialogueQuestions.map(q=>q.text+'\n'+(dialogueAnswers[q.id]||'')).join('\n\n');
    resetDialogue();
    if(draft){const saved=document.createElement('p');saved.className='cmsg';saved.textContent=tcText("Previous answer, not resent:\n")+draft;
      dialogueHistory.append(saved);dialogueHistory.hidden=false;el('conversationPanel').hidden=false;el('emptyConversation').hidden=true;}
    throw new Error(data.detail.message);
  }
  if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:(data.error||tcText("Request refused. Read state again.")));
  return data;
}
async function run(work){if(busy)return;busy=true;el('workflowError').hidden=true;controls();try{await work();}catch(e){invalidate();el('workflowError').textContent=e.message;el('workflowError').hidden=false;note(e.message);}finally{busy=false;controls();}}
function renderAmps(amps){
  el('ampCount').textContent=amps?tcText("{{v0}} models available to the AMP/CAB builder. AI chooses from this full FW33 list. Nothing changes without review and SEND.", {v0:(amps.count)}):'The full FW33 amp list requires the supported MK2 profile.';
  el('ampModels').replaceChildren();
  if(amps)for(const amp of amps.models){const item=document.createElement('li');item.textContent=amp.name;el('ampModels').append(item);}
}
function renderCabs(){
  const query=el('cabSearch').value.trim().toLocaleLowerCase();
  const all=state?.cab_inventory||[],matches=all.filter(c=>`${c.position} ${c.name}`.toLocaleLowerCase().includes(query));
  el('cabInventoryCount').textContent=tcText("{{v0}} non-empty names available; {{v1}} matches{{v2}}", {v0:(all.length), v1:(matches.length), v2:(matches.length>100?tcText(", showing the first 100. Refine your search."):'.')});
  el('cabNames').replaceChildren();
  for(const cab of matches.slice(0,100)){const row=document.createElement('li');row.textContent=`${cab.position}: ${cab.name}${cab.fullres?tcText(" (IR3/4 only)"):''}`;el('cabNames').append(row);}
  const mix=state?.cab_mix;el('cabMixer').replaceChildren();
  el('cabMixerNote').textContent=mix?.supported?tcText("Cab 1 / {{v0}}: current independent reading.", {v0:('ABCD'[mix.channel])}):(mix?.reason||tcText("No verified current mix was read."));
  for(const slot of mix?.slots||[]){
    const name=all.find(c=>c.bank===slot.bank&&c.slot===slot.ordinal+1);
    const row=document.createElement('li');row.textContent=`IR${slot.slot}: ${name?.name||`bank ${slot.bank}, position ${slot.ordinal+1}`} | ${slot.status} | ${slot.level_db}dB | pan ${slot.pan}`;el('cabMixer').append(row);
  }
}
function renderHistory(data){
  el('historyDesign').replaceChildren(new Option(tcText("Choose a design for the current preset"),''));
  for(const item of data.designs){
    const option=new Option(`${item.preset}: ${item.name} | ${new Date(item.created).toLocaleString()}`,item.id);
    option.disabled=item.preset!==state?.preset;el('historyDesign').append(option);
  }
  el('historyTarget').checked=el('historyMute').checked=false;
  el('historyStatus').textContent=tcText("{{v0}} designs found{{v1}}. Resuming sends no stored parameter actions.", {v0:(data.designs.length), v1:(data.unreadable?tcText("; {{v0}} unreadable records skipped", {v0:(data.unreadable)}):'')});
  historyControls();
}
function historyControls(){
  for(const id of ['historyRefresh','historyDesign','historyTarget','historyMute'])el(id).disabled=busy||!state?.design_history_supported;
  el('historyResume').disabled=busy||!state?.design_history_supported||!!proposal||!el('historyDesign').value||!el('historyTarget').checked||!el('historyMute').checked;
}
el('historyDesign').onchange=()=>{el('historyTarget').checked=el('historyMute').checked=false;historyControls();};
for(const id of ['historyTarget','historyMute'])el(id).onchange=historyControls;
el('historyRefresh').onclick=async()=>{
  if(busy)return;busy=true;controls();historyControls();
  try{renderHistory(await api('history'));}catch(error){el('historyStatus').textContent=error.message;}
  finally{busy=false;controls();historyControls();}
};
el('historyResume').onclick=()=>run(async()=>{
  const draft=el('prompt').value;
  const result=await api('history/resume',{record_id:el('historyDesign').value,expected_preset:state.preset,
    external_audio_muted:el('historyMute').checked,target_confirmed:el('historyTarget').checked});
  await refresh();
  refineContext={token:result.refine_token,count:result.scenes.length,preset:result.preset,mode:result.mode};
  enterRefinement();el('prompt').value=draft;
  el('historyStatus').textContent=result.warning;
  note(tcText("Design checked again. Select scenes and describe your adjustment; nothing stored."));
});
el('cabSearch').oninput=renderCabs;
function cabDescription(cab){
  if(!cab.irs)return `${cab.name} | Factory 2 slot ${cab.slot} / ${cab.channel}`;
  const solo=cab.irs.some(ir=>ir.mode==='solo');
  return `${cab.channel}: `+cab.irs.map(ir=>{
    const membership=ir.mode==='mute'?'MUTED':solo&&ir.mode!=='solo'?'EXCLUDED BY SOLO':ir.mode==='solo'?'SOLO':'IN MIX';
    return `IR${ir.ir} ${ir.name} [bank ${ir.bank}, slot ${ir.slot}] ${membership}, ${ir.level_db}dB, pan ${ir.pan}`;
  }).join(' | ');
}
ampRefreshButton.onclick=async()=>{
  if(busy||!state?.connected)return;
  busy=true;controls();ampRefreshStatus.textContent='Checking firmware and the local model list...';ampChanges.replaceChildren();ampChanges.hidden=true;
  try{
    const result=await api('amps/refresh',{expected_firmware:state.firmware});
    renderAmps(result.inventory);ampRefreshStatus.textContent=result.message;
    ampRefreshStatus.className=result.status==='up_to_date'?'':'warning';
    for(const [key,label] of [['added','New, still blocked'],['changed','Changed, still blocked'],['removed','Missing from local cache']]){
      for(const model of result[key]){const row=document.createElement('li');row.textContent=`${label}: ${model.name}${model.verified_name?' (geverifieerd: '+model.verified_name+')':''}`;ampChanges.append(row);}
    }
    ampChanges.hidden=!ampChanges.childElementCount;
  }catch(error){ampRefreshStatus.className='warning';ampRefreshStatus.textContent=error.message;}
  finally{busy=false;controls();}
};
async function refresh(){
  resetIntake();
  const priorState=state,priorRoute=el('buildRoute').value,priorScenes=el('scenes').value;
  navigationPreview=null;el('navigationDialog').close();
  clearRouteExploration();invalidate();clearNamSlots();state=null;state=await api('state');
  if(!adjusting&&priorState?.connected&&state.connected&&priorState.preset===state.preset&&priorState.firmware===state.firmware&&priorState.profile?.variant===state.profile?.variant&&priorRoute){
    el('buildRoute').value=priorRoute;el('scenes').value=priorScenes;
    el('routeReason').textContent=tcText("Build route and scene count preserved. Explore routes again before creating a new plan; nothing was sent.");
  }
  if(refineContext&&state.preset!==refineContext.preset){refineContext=null;adjusting=false;adjustPanel.hidden=true;el('generate').textContent='GENERATE PLAN';clearRouteExploration();}
  el('workspaceIdentity').textContent='TC FX3'+(state.workspace?.revision?' '+state.workspace.revision:'');
  el('workspaceIdentity').title=state.workspace?`${state.workspace.source_root} | PID ${state.workspace.pid}`:tcText("Workspace identity unavailable; check your start script.");
  el('target').textContent=state.connected?`Preset ${state.preset}: ${state.name} \u25be`:tcText("Connect through Connection & controllers first.");
  el('target').title=state.connected?tcText("Axe-Fx III | {{v0}} | Preset {{v1}}: {{v2}} | Scene {{v3}}. Click to choose a preset.", {v0:(state.firmware), v1:(state.preset), v2:(state.name), v3:(state.scene)}):tcText("Connect through Connection & controllers first.");
  el('connectDevice').title=state.connected?`Axe-Fx III | ${state.firmware}`:tcText("Connect to the Fractal");
  el('cabCount').textContent=state.connected?`${state.cab_count} geimporteerde naamposities. ${state.cab_metadata_note||''} ${state.cab_selection_note||''}`:'';
  renderAmps(state.amp_inventory);ampRefreshStatus.textContent='';ampChanges.replaceChildren();ampChanges.hidden=true;
  renderCabs();
  el('historyPanel').hidden=!state.design_history_supported;
  if(state.design_history_supported){
    try{renderHistory(await api('history'));}catch(error){el('historyStatus').textContent=error.message;}
  }
  historyControls();
  el('variant').value=state.profile?.variant||'';
  el('memoryWarning').textContent=state.profile?.warning||tcText("Choose MK1 or MK2 to show the correct memory layout.");
  if(state.nam_selection_supported){
    const selected=captureSlot.value;
    captureSlot.replaceChildren(new Option(tcText("Current NAM {{v0}} preserved", {v0:(String(state.nam?.slot||1).padStart(3,'0'))}),''));
    for(const row of namSlots||[])if(row.occupied)captureSlot.append(new Option(`${String(row.slot).padStart(3,'0')} | ${row.name}`,String(row.slot)));
    if([...captureSlot.options].some(o=>o.value===selected))captureSlot.value=selected;
  }
  el('liveRoute').replaceChildren();
  if(state.route?.length){for(const [i,label] of state.route.entries()){
    if(i)el('liveRoute').append(document.createTextNode(' → '));
    const actual=state.route_blocks?.[i];
    const block=document.createElement('span');block.className='chain-block'+(actual?.bypassed?' bypassed':'');block.textContent=label;
    if(actual){const channel=document.createElement('span');channel.className='chain-channel';channel.textContent=actual.channel;block.append(channel);block.title=actual.bypassed?'Bypassed':'Actief';}
    el('liveRoute').append(block);
  }}else el('liveRoute').textContent=state.route_problem||tcText("Empty or unread chain");
  el('sceneRack').replaceChildren();
  for(let i=0;i<8;i++){
    const raw=state.scene_names?.[i],label=Array.isArray(raw)?raw[1]:(raw||'');
    const scene=document.createElement('button');scene.type='button';scene.className='sc'+(state.connected&&state.scene===i+1?' on':'');
    scene.dataset.scene=String(i+1);scene.disabled=busy||!state.navigation_supported;
    scene.setAttribute('aria-label',`Scene ${i+1}: ${label||tcText("unnamed")}`);scene.setAttribute('aria-pressed',String(state.scene===i+1));
    const num=document.createElement('span');num.className='n';num.textContent=String(i+1);
    const name=document.createElement('span');name.className='nm';name.textContent=label;scene.append(num,name);el('sceneRack').append(scene);
  }
  if(el('namPanel').open)await accountStatus();
  note(state.route_problem||(state.connected?tcText("State read. Nothing sent."):tcText("Not connected yet.")));
}
el('refresh').onclick=()=>run(refresh);
function renderPresets(){
  const query=el('presetSearch').value.trim().toLowerCase();el('presetChoices').replaceChildren();
  for(const row of presetLibrary.filter(r=>`${String(r.number).padStart(4,'0')} ${r.number} ${r.name}`.toLowerCase().includes(query))){
    const button=document.createElement('button');button.type='button';button.dataset.preset=String(row.number);
    button.textContent=`${String(row.number).padStart(3,'0')} | ${row.name}`;
    button.onclick=()=>{el('presetDialog').close();prepareNavigation('preset',row.number);};el('presetChoices').append(button);
  }
}
el('presetSearch').oninput=renderPresets;
el('presetClose').onclick=()=>el('presetDialog').close();
el('target').onclick=()=>run(async()=>{
  el('presetSearch').value='';presetLibrary=[];el('presetChoices').replaceChildren();el('presetDialog').showModal();
  el('presetScanStatus').textContent=tcText("Reading preset names 000-511. Nothing is selected...");
  let result;
  try{result=await api('navigation/presets');}
  catch(error){el('presetScanStatus').textContent=error.message;throw error;}
  presetLibrary=result.slots;renderPresets();
  el('presetScanStatus').textContent=tcText("{{v0}} preset names read. Click a preset to confirm the switch.", {v0:(presetLibrary.length)});
});
function prepareNavigation(kind,value){return run(async()=>{
  navigationPreview=null;el('navigationMute').checked=el('navigationDiscard').checked=false;
  const preview=await api('navigation/prepare',{kind,value,expected_preset:state.preset,expected_scene:state.scene});
  navigationPreview=preview;el('navigationTitle').textContent=kind==='preset'?'PRESET SELECTEREN':'SCENE SELECTEREN';
  el('navigationDestination').textContent=`${kind==='preset'?'Preset':'Scene'} ${preview.destination.number}: ${preview.destination.name||tcText("unnamed")}`;
  el('navigationWarning').textContent=kind==='preset'?tcText("This switch discards unsaved changes on the Fractal. Your request text is preserved; an existing plan becomes invalid."):tcText("This switch changes the active sound. Keep external audio muted during the test switch. An existing plan becomes invalid.");
  el('navigationDiscardLabel').hidden=kind!=='preset';el('navigationDialog').showModal();
});}
el('sceneRack').onclick=event=>{const button=event.target.closest('button[data-scene]');if(button&&!button.disabled)prepareNavigation('scene',Number(button.dataset.scene));};
el('navigationMute').onchange=el('navigationDiscard').onchange=controls;
el('navigationCancel').onclick=()=>{navigationPreview=null;el('navigationDialog').close();controls();};
el('navigationDialog').addEventListener('cancel',()=>{navigationPreview=null;controls();});
el('navigationSelect').onclick=()=>run(async()=>{
  const preview=navigationPreview;if(!preview)throw new Error(tcText("Confirm selection again."));
  navigationPreview=null;el('navigationDialog').close();
  const result=await api('navigation/select',{token:preview.token,external_audio_muted:el('navigationMute').checked,confirm_discard_edits:el('navigationDiscard').checked});
  el('navigationDialog').close();await refresh();note(tcText("{{v0}} selected and read back from the Fractal. Nothing stored.", {v0:(result.kind==='preset'?'Preset':'Scene')}));
});
for(const id of ['prompt','scenes','wah','wahMode'])el(id).addEventListener('input',invalidate);
el('prompt').addEventListener('input',()=>{resetIntake();clearRouteExploration();controls();});
el('scenes').addEventListener('change',()=>{resetDialogue();intakeResolution.scene_count_override=true;intakeSceneCount=Number(el('scenes').value);});
el('audioFile').addEventListener('input',()=>{resetDialogue();clearRouteExploration();controls();});
el('buildRoute').onchange=()=>{if(lastDialogueRoute&&lastDialogueRoute!==el('buildRoute').value)resetDialogue();lastDialogueRoute=el('buildRoute').value;
  intakeResolution.accepted_omissions=[];intakePanel.hidden=true;invalidate();const choice=routeExploration?.routes.find(r=>r.mode===el('buildRoute').value);
  el('routeReason').textContent=choice?choice.reason:tcText("Choose NAM or AMP/CAB yourself.");controls();};
async function exploreRequestRoutes(){
  if(!el('prompt').value.trim())throw new Error(tcText("Describe the desired sound or add a link first."));
  if(!await ensureIntake('auto'))return;
  clearRouteExploration();invalidate();await api('discard',{});
  note(tcText("TC is exploring your request and available build routes. Nothing is sent to the Fractal..."));
  if(sourceKind.value==='rig'&&el('audioFile').files.length)throw new Error(tcText("Rig explanations use text or a YouTube link. Remove the audio file or choose sound reference."));
  audioReference=sourceKind.value==='rig'?null:await analyseRequestAudio();
  const result=await api('options',{prompt:el('prompt').value,expected_preset:state.preset,audio_reference:audioReference,source_kind:sourceKind.value,
    ...dialoguePayload(),
    ...(state.request_intake_supported?{resolution:intakeResolution,scenes:Number(el('scenes').value)}:{})});
  receiveDialogue(result);
  if(result.needs_clarification){showIntake(result.intake);return;}
  routeExploration=result;el('routeOptionsPanel').open=true;
  el('routeReason').textContent=tcText("Advice: {{v0}}. Choose your build route; executable options are listed below.", {v0:(result.comparison.recommended==='amp'?'AMP/CAB':result.comparison.recommended==='nam'?'NAM':tcText("both routes possible"))});
  for(const route of result.routes){const p=document.createElement('p');
    p.textContent=`${route.label}: ${route.enabled?tcText("executable with the currently verified controls"):tcText("musical option, not yet executable on this profile")}. ${route.reason}`;el('routeOptions').append(p);}
  const evidence=document.createElement('details'),summary=document.createElement('summary');
  summary.textContent=tcText("Why this advice? Amp direction and possible effects");evidence.append(summary);
  const reason=document.createElement('p');reason.textContent=result.comparison.reason;evidence.append(reason);
  const detail=document.createElement('p');detail.textContent=tcText("Amp direction: {{v0}}. NAM search term: {{v1}}. Possible effects: {{v2}}. These are interpretations, not promised parameter writes.", {v0:(result.comparison.amp_direction), v1:(result.comparison.nam_query), v2:(result.comparison.pedals.join(', ')||tcText("no extra effects needed"))});evidence.append(detail);el('routeOptions').append(evidence);
  el('namQuery').value=result.comparison.nam_query;
  if(result.nam_candidates?.length){await showAccountTones(result.nam_candidates);el('namPanel').open=true;}
  if(result.nam_search_warning){const warning=document.createElement('p');warning.textContent=result.nam_search_warning;el('routeOptions').append(warning);}
  el('routeOptionsPanel').scrollIntoView({block:'nearest'});
  note(tcText("Routes explored. Choose NAM or AMP/CAB; nothing selected, installed or sent."));
}
el('exploreRoutes').onclick=()=>run(exploreRequestRoutes);
el('confirmed').onchange=el('muted').onchange=controls;
function navigate(index){
  if(busy||(index>0&&index<4&&!proposal)||(index===4&&!el('resultText').textContent))return;
  stage(index);controls();el(stagePanes[index]).focus();
}
document.querySelectorAll('#rail .stg').forEach(button=>{button.onclick=()=>navigate(Number(button.dataset.step));});
el('toReview').onclick=()=>navigate(2);el('backPlan').onclick=()=>navigate(1);
el('toConfirm').onclick=()=>navigate(3);el('backReview').onclick=()=>navigate(2);
el('editRequest').onclick=()=>{navigate(0);el('requestPanel').open=true;el('prompt').focus();};
el('returnRequest').onclick=()=>navigate(0);
el('storePrepare').onclick=()=>run(async()=>{
  await api('discard',{});storePreview=await api('store/prepare',{expected_preset:state.preset});
  el('storeMute').checked=el('storeFlash').checked=false;
  el('storeSummary').textContent=tcText("Preset {{v0}}: {{v1}} -> {{v2}}. Permanent. Nothing stored yet. {{v3}}", {v0:(storePreview.preset), v1:(storePreview.replaces), v2:(storePreview.name), v3:(storePreview.verification_note||'')});
});
el('storeMute').onchange=el('storeFlash').onchange=controls;
el('storeCommit').onclick=()=>run(async()=>{
  const token=storePreview?.token;
  if(!token||!el('storeMute').checked||!el('storeFlash').checked)throw new Error(tcText("Confirm the storage target and external audio muting."));
  storePreview=null;
  const result=await api('store',{token,external_audio_muted:true,confirm_permanent_write:true});
  el('storeSummary').textContent=tcText("Stored: preset {{v0}} {{v1}}. No reload or listening test performed.", {v0:(result.preset), v1:(result.name)});
});
el('deviceChoice').onchange=()=>{invalidate();note(tcText("Confirm your device choice with the top-right button. Until then the MIDI connection stays unchanged."));};
el('variant').onchange=()=>run(async()=>{
  invalidate();if(!el('variant').value)return;
  await api('profile',{variant:el('variant').value});await refresh();
});
el('connectDevice').onclick=()=>run(async()=>{
  const fm9=el('deviceChoice').value==='fm9';
  if(fm9&&(el('prompt').value||proposal)&&!confirm(tcText("Open the FM9 interface? The request text will not be transferred. The Fractal is not stored or reloaded.")))return;
  await api(fm9?'disconnect':'connect',{},'/api/controllers/');
  if(fm9){location.href='/';return;}await refresh();
});
el('newDesign').onclick=()=>run(async()=>{
  if((el('prompt').value||proposal)&&!confirm(tcText("Start a new design? This clears the request and proposal, not the Fractal.")))return;
  await api('discard',{});invalidate();el('prompt').value='';audioReference=null;el('audioFile').value='';
  resetIntake();
  el('audioStart').value='0';el('audioLength').value='60';audioReferenceKey='';
  el('recordingFile').value='';clearAudioComparison();
  el('historyTarget').checked=el('historyMute').checked=false;
  refineContext=null;adjusting=false;adjustPanel.hidden=true;el('generate').textContent='GENERATE PLAN';
  clearRouteExploration();
  el('conversationPanel').hidden=true;el('requestPanel').open=true;el('requestPreview').hidden=true;
  el('requestOptions').open=false;el('routeOptionsPanel').open=false;
  el('emptyConversation').hidden=false;el('resultText').textContent='';stage(0);
  el('result').hidden=true;el('audioStatus').textContent=tcText("A link in the request is used automatically.");
  // Focus after the busy guard releases the input.
  setTimeout(()=>el('prompt').focus(),0);note(tcText("New design. Fractal unchanged."));
});
function showCaptures(result){
  el('namResults').replaceChildren();
  for(const candidate of result.candidates||[]){
    const a=document.createElement('a');a.textContent=candidate.title+' | '+candidate.creator;
    // Only server-generated TONE3000 detail links, never arbitrary metadata URLs.
    a.href='https://www.tone3000.com/tones/'+Number(candidate.id);a.target='_blank';a.rel='noopener noreferrer';
    el('namResults').append(a);
  }
  if(!result.candidates?.length)el('namResults').textContent=tcText("No candidates found. TC does not invent a capture.");
}
async function accountStatus(){
  namAccount=await api('tone3000/status');namSelection=namAccount.selected;
  el('namStatus').textContent=namAccount.connected?'Account verbonden. '+(namAccount.reason||''):namAccount.configured?tcText("Key saved. Click SIGN IN."):tcText("Enter your publishable client key first.");
  el('namSelected').textContent=namSelection?.model?tcText("Selected: {{v0}}. Selection is not installation.", {v0:(namSelection.model.name)}):tcText("No NAM model selected yet.");
  controls();
}
function clearNamPreview(){namPreview=null;el('namInstallPanel').hidden=true;
  for(const id of ['namInstallMute','namInstallFlash','namInstallOverwrite'])el(id).checked=false;}
function clearNamSlots(){namSlots=null;el('namSlot').replaceChildren(new Option(tcText("Read the slots first"),''));
  captureSlot.replaceChildren(new Option(tcText("Current NAM {{v0}} preserved", {v0:(String(state?.nam?.slot||1).padStart(3,'0'))}),''));
  el('namSlotsHint').textContent=tcText("Read the NAM slots and choose where to place the download. Nothing is installed automatically.");}
el('namSlotsRefresh').onclick=()=>run(async()=>{
  clearNamPreview();clearNamSlots();
  const result=await api('tone3000/slots');
  if(!result.complete||result.slots?.length!==256)throw new Error(tcText("The NAM slot list is incomplete. No slot is assumed empty."));
  namSlots=result.slots;el('namSlot').replaceChildren();
  captureSlot.replaceChildren(new Option(tcText("Current NAM {{v0}} preserved", {v0:(String(state?.nam?.slot||1).padStart(3,'0'))}),''));
  for(const row of namSlots)if(row.occupied)captureSlot.append(new Option(`${String(row.slot).padStart(3,'0')} | ${row.name}`,String(row.slot)));
  for(const row of namSlots){const value=String(row.slot).padStart(3,'0');
    el('namSlot').append(new Option(`${value} | ${row.occupied?tcText("OCCUPIED: ")+row.name:tcText("EMPTY")}`,String(row.slot)));}
  el('namSlot').value=result.first_available?String(result.first_available):'';
  if(!result.first_available)el('namSlot').prepend(new Option(tcText("All slots occupied: choose a slot deliberately"),'',true,true));
  el('namSlotsHint').textContent=result.first_available?
    tcText("First empty slot: {{v0}}. Place the download here? Choose this or another slot and review the preview.", {v0:(String(result.first_available).padStart(3,'0'))}):
    tcText("No empty slots. Choose an occupied slot only if you deliberately want to replace the existing NAM.");
  el('namSlotsHint').textContent+=tcText(" Occupied slots can also be selected under Installed NAM for your preset design. Installation and preset selection are separate steps.");
});
el('namSlot').onchange=()=>{clearNamPreview();controls();};
async function showAccountTones(tones){
  el('namResults').replaceChildren();
  for(const tone of tones){
    const button=document.createElement('button');button.textContent=`${tone.title} | ${tone.creator?.username||'creator'}`;
    button.onclick=()=>run(async()=>{
      const detail=await api('tone3000/tones/'+Number(tone.id));el('namResults').replaceChildren();
      const claim=document.createElement('p');claim.textContent=tcText("{{v0}}: {{v1}} (creator claim, not measured)", {v0:(detail.tone?.title||tone.title), v1:(detail.tone?.description||'')});el('namResults').append(claim);
      for(const model of detail.models||[]){const choose=document.createElement('button');choose.textContent='SELECT '+model.name;
        choose.onclick=()=>run(async()=>{invalidate();clearNamPreview();await api('tone3000/select',{tone_id:Number(tone.id),model_id:Number(model.id)});await accountStatus();});el('namResults').append(choose);}
    });el('namResults').append(button);
  }
  if(!tones.length)el('namResults').textContent=tcText("No candidates found. Try an amp name or another search term.");
}
el('namPanel').addEventListener('toggle',()=>{if(el('namPanel').open&&!busy)run(accountStatus);});
el('namSaveKey').onclick=()=>run(async()=>{await api('tone3000/config',{client_id:el('namKey').value.trim()});el('namKey').value='';await accountStatus();});
el('namDisconnect').onclick=()=>run(async()=>{clearNamPreview();await api('tone3000/disconnect',{});await accountStatus();});
el('namSearch').onclick=()=>run(async()=>{
  if(el('namFormat').value==='ir'){showCaptures(await api('search',{query:el('namQuery').value,format:'ir'}));return;}
  const result=await api('tone3000/tones?query='+encodeURIComponent(el('namQuery').value));await showAccountTones(result.data||[]);
});
el('namSuggest').onclick=()=>run(async()=>{const result=await api('tone3000/suggest',{query:el('namQuery').value,prompt:el('prompt').value.slice(0,4000)});
  await showAccountTones(result.tone?[result.tone]:[]);note(result.reason+tcText(" Nothing selected or installed yet."));});
el('namLogin').onclick=()=>run(async()=>{
  const d=await api('tone3000/auth/start',{mode:'signin'});
  const url=new URL(d.url);
  if(url.origin!=='https://www.tone3000.com')throw new Error(tcText("Invalid sign-in link."));
  location.href=url.href;
});
el('namInstallPrepare').onclick=()=>run(async()=>{
  const slot=Number(el('namSlot').value);
  if(!namSelection?.model||!state?.connected||!namSlots||!Number.isInteger(slot)||slot<1||slot>256)throw new Error(tcText("Select a model, read the NAM slots and choose your target slot."));
  invalidate();clearNamPreview();await api('discard',{});
  namPreview=await api('tone3000/install/prepare',{model_id:namSelection.model.id,expected_preset:state.preset,slot});
  if(namPreview.slot!==slot)throw new Error(tcText("The installation preview names a different NAM slot. Do not install anything."));
  const destination=String(slot).padStart(3,'0');
  el('namInstallSummary').textContent=tcText("NAM {{v0}}: {{v1}} -> {{v2}}. Permanent; recovery backup is checked before installation. Preset {{v3}} is not stored.", {v0:(destination), v1:(namPreview.existing_name), v2:(namPreview.name), v3:(namPreview.expected_preset)});
    if(namPreview.name_adjusted)el('namInstallSummary').textContent+=tcText(" Catalog name: {{v0}}. Only the Fractal name was shortened to at most 27 ASCII characters; the model is unchanged.", {v0:(namPreview.source_name)});
  el('namInstallWarning').textContent=namPreview.existing_occupied?
    tcText("THIS SLOT IS OCCUPIED. Replacement also changes other presets using this NAM slot. TC does not inventory those references; an empty target preset does not prevent this."):
    tcText("This slot was verified empty again. TC checks it once more before writing. The NAM is not automatically selected in a preset.");
  el('namSlotConsent').textContent=namPreview.existing_occupied?
    tcText("I confirm overwriting NAM slot {{v0}}, including other presets that use it.", {v0:(destination)}):
    tcText("I choose NAM slot {{v0}} for this download.", {v0:(destination)});
  el('namInstallCommit').textContent=tcText("INSTALL IN NAM {{slot}}",{slot:destination});
  el('namInstallPanel').hidden=false;
});
for(const id of ['namInstallMute','namInstallFlash','namInstallOverwrite'])el(id).onchange=controls;
el('namInstallCommit').onclick=()=>run(async()=>{
  const token=namPreview?.prepared_id;if(!token||!el('namInstallMute').checked||!el('namInstallFlash').checked||!el('namInstallOverwrite').checked)throw new Error(tcText("Confirm all three installation conditions."));
  clearNamPreview();invalidate();
  const result=await api('tone3000/install',{prepared_id:token,external_audio_muted:true,confirm_permanent_write:true,confirm_overwrite:true});
  await accountStatus();await refresh();note(tcText("{{v0}} NAM bytes verified. No preset stored; audio remains muted.", {v0:(result.bytes_verified)}));
});
for(const id of ['namQuery','namWithRequest'])el(id).addEventListener('input',invalidate);
el('audioFile').addEventListener('input',()=>{audioReference=null;clearAudioComparison();invalidate();});
for(const id of ['audioStart','audioLength'])el(id).addEventListener('input',()=>{
  resetDialogue();audioReference=null;audioReferenceKey='';clearAudioComparison();invalidate();clearRouteExploration();
});
function requestLinks(text){return [...new Set((text.match(/https?:\/\/[^\s<>"\]]+/g)||[]).map(x=>x.replace(/[).,;]+$/,'')))];}
function spectrum(samples,rate){
  const size=2048,real=new Float64Array(size),imag=new Float64Array(size);
  for(let i=0;i<size;i++)real[i]=(samples[i]||0)*(.5-.5*Math.cos(2*Math.PI*i/(size-1)));
  for(let i=1,j=0;i<size;i++){let bit=size>>1;for(;j&bit;bit>>=1)j^=bit;j^=bit;if(i<j)[real[i],real[j]]=[real[j],real[i]];}
  for(let n=2;n<=size;n*=2){for(let start=0;start<size;start+=n){for(let j=0;j<n/2;j++){
    const angle=-2*Math.PI*j/n,c=Math.cos(angle),s=Math.sin(angle),a=start+j,b=a+n/2;
    const r=real[b]*c-imag[b]*s,v=real[b]*s+imag[b]*c;
    real[b]=real[a]-r;imag[b]=imag[a]-v;real[a]+=r;imag[a]+=v;
  }}}
  let total=0,weighted=0;const bands=[0,0,0,0,0];
  for(let i=1;i<size/2;i++){const hz=i*rate/size,power=real[i]**2+imag[i]**2;
    const band=hz<250?0:hz<600?1:hz<2000?2:hz<5000?3:4;bands[band]+=power;total+=power;weighted+=hz*power;}
  return {centroid:total?weighted/total:0,bands:bands.map(x=>total?x/total:0),total,weighted,band_power:bands};
}
async function measureWindowV2(buffer,first,limit){
  const channels=buffer.numberOfChannels,rate=16000;
  if(!Number.isInteger(first)||!Number.isInteger(limit)||first<0||first+limit>buffer.length||channels<1||channels>8||limit<buffer.sampleRate*.25||limit>buffer.sampleRate*60)
    throw new Error(tcText("Choose 0.25 to 60 seconds of audio with up to eight channels."));
  let power=0,peak=0;
  // Meter original samples per channel: opposite phases must not cancel and
  // filtering/downsampling must not hide the original file's sample peaks.
  for(let ch=0;ch<channels;ch++){
    const data=buffer.getChannelData(ch);
    for(let i=first;i<first+limit;i++){
      const x=data[i];if(!Number.isFinite(x))throw new Error(tcText("Audio contains invalid samples."));
      power+=x*x;peak=Math.max(peak,Math.abs(x));
    }
    await new Promise(resolve=>setTimeout(resolve,0));
  }
  if(peak<1e-7)throw new Error(tcText("The audio segment contains no measurable signal."));
  // Explicit phase-table, Blackman-windowed sinc resampling. Browser
  // interpolation alone did NOT reject a12kHz alias in the real Chrome test.
  // Original samples remain untouched; no audio is played or uploaded.
  const cutoff=Math.min(7000,buffer.sampleRate*.45),phases=512;
  const radius=Math.min(256,Math.max(32,Math.ceil(buffer.sampleRate/700))),taps=radius*2+1;
  const kernels=Array.from({length:phases},(_,p)=>{
    const kernel=new Float64Array(taps),fraction=p/phases;let sum=0;
    for(let k=0;k<taps;k++){
      const x=k-radius-fraction;
      if(Math.abs(x)>radius)continue;
      const lowpass=Math.abs(x)<1e-12?2*cutoff/buffer.sampleRate:Math.sin(2*Math.PI*cutoff/buffer.sampleRate*x)/(Math.PI*x);
      kernel[k]=lowpass*(.42+.5*Math.cos(Math.PI*x/radius)+.08*Math.cos(2*Math.PI*x/radius));sum+=kernel[k];
    }
    for(let k=0;k<taps;k++)kernel[k]/=sum;
    return kernel;
  });
  const length=Math.floor(limit/buffer.sampleRate*rate),count=Math.min(512,Math.max(1,Math.ceil(length/2048)));
  let total=0,weighted=0;const bands=[0,0,0,0,0];
  for(let ch=0;ch<channels;ch++){
    const original=buffer.getChannelData(ch),data=new Float32Array(length);
    for(let i=0;i<length;i++){
      const position=i*buffer.sampleRate/rate;let center=Math.floor(position),phase=Math.round((position-center)*phases);
      if(phase===phases){center++;phase=0;}
      const kernel=kernels[phase];let value=0;
      for(let k=0;k<taps;k++){
        const index=center+k-radius;
        if(index>=0&&index<limit)value+=original[first+index]*kernel[k];
      }
      data[i]=value;
      if(i%8192===8191)await new Promise(resolve=>setTimeout(resolve,0));
    }
    for(let i=0;i<count;i++){
      const offset=Math.floor(i*Math.max(0,data.length-2048)/Math.max(1,count-1));
      const frame=spectrum(data.subarray(offset,offset+2048),rate);
      total+=frame.total;weighted+=frame.weighted;
      for(let b=0;b<5;b++)bands[b]+=frame.band_power[b];
    }
  }
  const db=x=>20*Math.log10(Math.max(x,1e-7)),rms=Math.sqrt(power/(channels*limit));
  return {rms_dbfs:db(rms),peak_dbfs:db(peak),crest_db:db(peak)-db(rms),
    centroid_hz:total?weighted/total:0,band_energy:bands.map(x=>total?x/total:0),
    analysis_method:'channel-power-v2',analysis_rate_hz:rate,analysis_cutoff_hz:cutoff,analysis_channels:channels,analysis_frames:count};
}
async function analyseRequestAudio(){
  const urls=requestLinks(el('prompt').value),file=el('audioFile').files[0];
  if(urls.length>1)throw new Error(tcText("Use one audio link per request."));
  if(file&&urls.length)throw new Error(tcText("Use an audio link OR a file, not both."));
  if(!file&&!urls.length)return null;
  if(file&&file.size>40*1024*1024)throw new Error(tcText("Audio must be at most 40 MiB."));
  const start=Number(el('audioStart').value),length=Number(el('audioLength').value);
  if(!Number.isFinite(start)||start<0||start>86400||!Number.isFinite(length)||length<.25||length>60)
    throw new Error(tcText("Choose a valid start time and a segment length of 0.25 to 60 seconds."));
  const key=JSON.stringify([file?[file.name,file.size,file.lastModified]:urls[0],start,length,state?.audio_analysis_version||1]);
  if(audioReference&&audioReferenceKey===key){
    el('audioStatus').textContent=tcText("Previously measured local sound reference reused; no second download.");
    return audioReference;
  }
  el('audioStatus').textContent='Audio ophalen en lokaal analyseren...';
  let bytes;
  if(file)bytes=await file.arrayBuffer();
  else{
    const response=await fetch('/api/axefx3/audio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:urls[0]})});
    if(!response.ok)throw new Error((await response.json()).detail||'Audio ophalen mislukt.');
    bytes=await response.arrayBuffer();
  }
  const context=new AudioContext();
  try{
    const buffer=await context.decodeAudioData(bytes),first=Math.floor(start*buffer.sampleRate);
    if(!Number.isFinite(buffer.duration)||buffer.duration>86400||first>=buffer.length)
      throw new Error(tcText("The start time is outside the audio file or the source is too long."));
    const limit=Math.min(buffer.length-first,Math.floor(buffer.sampleRate*length));
    if(limit<buffer.sampleRate*.25)throw new Error('Het gekozen fragment is korter dan 0,25 seconde.');
    let metrics;
    if(state?.audio_analysis_version===2)metrics=await measureWindowV2(buffer,first,limit);
    else{
    const step=Math.max(1,Math.floor(buffer.sampleRate/16000)),mono=new Float32Array(Math.ceil(limit/step));
    for(let ch=0;ch<buffer.numberOfChannels;ch++){const data=buffer.getChannelData(ch);for(let i=0,j=0;i<limit;i+=step,j++)mono[j]+=data[first+i]/buffer.numberOfChannels;}
    let power=0,peak=0;for(const x of mono){power+=x*x;peak=Math.max(peak,Math.abs(x));}
    if(peak<1e-7)throw new Error(tcText("The audio segment contains no measurable signal."));
    const rms=Math.sqrt(power/mono.length),db=x=>20*Math.log10(Math.max(x,1e-7));
    const count=Math.min(32,Math.max(1,Math.floor(mono.length/2048))),bands=[0,0,0,0,0];let centroid=0;
    for(let i=0;i<count;i++){const offset=Math.floor(i*(mono.length-2048)/Math.max(1,count-1));
      const frame=spectrum(mono.subarray(Math.max(0,offset),Math.max(0,offset)+2048),buffer.sampleRate/step);
      centroid+=frame.centroid/count;for(let b=0;b<5;b++)bands[b]+=frame.bands[b]/count;
    }
    metrics={rms_dbfs:db(rms),peak_dbfs:db(peak),crest_db:db(peak)-db(rms),centroid_hz:centroid,band_energy:bands};
    }
    const measured={url:urls[0]||null,file_name:file?.name?.slice(0,180)||null,sample_seconds:limit/buffer.sampleRate,
      start_seconds:first/buffer.sampleRate,source_seconds:buffer.duration,...metrics};
    el('audioStatus').textContent=tcText("Segment {{v0}}-{{v1}} s measured locally, RMS {{v2}} dBFS. {{v3}}No guitar isolation or direct AI listening.", {v0:(measured.start_seconds.toFixed(2)), v1:((measured.start_seconds+measured.sample_seconds).toFixed(2)), v2:(measured.rms_dbfs.toFixed(1)), v3:(metrics.analysis_method?tcText("Channel energy measured separately; spectrum uses a {{v0}} kHz anti-alias filter. ", {v0:(metrics.analysis_cutoff_hz/1000)}):'')});
    audioReferenceKey=key;
    return measured;
  }finally{await context.close();}
}
el('compareAudio').onclick=async()=>{
  if(busy)return;
  busy=true;controls();clearAudioComparison();
  try{
    if(state?.audio_analysis_version!==2)throw new Error(tcText("This backend does not support the new local analysis yet."));
    if(sourceKind.value==='rig')throw new Error(tcText("Choose a sound reference, not a spoken equipment explanation."));
    const file=el('recordingFile').files[0],start=Number(el('recordingStart').value),length=Number(el('recordingLength').value);
    if(!file||file.size>40*1024*1024)throw new Error(tcText("Choose your own audio recording, up to 40 MiB."));
    if(!Number.isFinite(start)||start<0||start>86400||!Number.isFinite(length)||length<.25||length>60)
      throw new Error(tcText("Choose a valid recording start and a length of 0.25 to 60 seconds."));
    audioReference=await analyseRequestAudio();
    if(!audioReference)throw new Error(tcText("Add the sound reference in SONG / AUDIO or your request first."));
    const context=new AudioContext();let recording;
    try{
      const buffer=await context.decodeAudioData(await file.arrayBuffer()),first=Math.floor(start*buffer.sampleRate);
      if(buffer.duration>86400||first>=buffer.length)throw new Error(tcText("The start time is outside the recording."));
      const count=Math.min(buffer.length-first,Math.floor(length*buffer.sampleRate));
      recording={sample_seconds:count/buffer.sampleRate,start_seconds:first/buffer.sampleRate,source_seconds:buffer.duration,
        ...await measureWindowV2(buffer,first,count)};
    }finally{await context.close();}
    const result=await api('audio/compare',{reference:audioReference,recording});
    const d=result.differences,root=el('comparisonResults');
    for(const text of [tcText("Recording minus reference: RMS {{rms}} dB, peak {{peak}} dB, crest {{crest}} dB.", {rms:d.rms_db.toFixed(1),peak:d.peak_db.toFixed(1),crest:d.crest_db.toFixed(1)}),
        tcText("Spectral centroid: {{delta}} Hz difference.", {delta:d.centroid_hz.toFixed(0)}),
        ...d.band_energy.map(b=>tcText("{{band}}: {{delta}} percentage points energy difference{{relative}}.", {band:b.band,delta:(100*b.delta_fraction).toFixed(1),relative:b.relative_db===null?'':tcText(", {{value}} dB relative",{value:b.relative_db.toFixed(1)})})),result.note]){
      const p=document.createElement('p');p.textContent=text;root.append(p);
    }
    el('comparisonStatus').textContent=tcText("Comparison complete. No preset, AI plan or settings changed; nothing played or sent to the Fractal.");
  }catch(error){el('comparisonStatus').textContent=error.message;}
  finally{busy=false;controls();}
};
function showSceneComparison(plan){
  for(const panel of comparisonPanels){
    panel.replaceChildren();panel.hidden=!plan.scene_comparison;
    if(panel.hidden)continue;
    const audit=plan.scene_comparison;
    const heading=document.createElement('h3');heading.textContent=tcText("TONE DIFFERENCES AND REUSE");panel.append(heading);
    const note=document.createElement('p');note.className='hint';note.textContent=audit.notice;panel.append(note);
    if(audit.contract){
      const brief=document.createElement('details'),title=document.createElement('summary');
      title.textContent=tcText("Tone goals recorded for the design");brief.append(title);
      for(const scene of audit.contract.scenes){
        const p=document.createElement('p');p.textContent=`${scene.scene}. ${scene.role}: ${scene.target}. ${scene.reason}`;brief.append(p);
      }panel.append(brief);
    }
    for(const scene of audit.rows){
      const p=document.createElement('p'),title=document.createElement('strong');title.textContent=`${scene.scene}. ${scene.name}: `;p.append(title);
      const description=scene.same_as.length?tcText("Same programmed tone as scene {{v0}}. {{v1}}", {v0:(scene.same_as.join(', ')), v1:(scene.reuse_reason||tcText("Not previously recorded as intentional reuse."))}):
        scene.reference_scene?tcText("Compared with scene {{v0}}: {{v1}}", {v0:(scene.reference_scene), v1:(scene.changes.join('; ')||tcText("No different tonal character; only other settings."))}):tcText("Base tone for this design.");
      p.append(document.createTextNode(description));
      if(scene.small_variation){const warning=document.createElement('span');warning.className='warning';warning.textContent=tcText(" Small parameter change, not proven audible contrast.");p.append(warning);}
      const cab=document.createElement('span');cab.className='hint';cab.textContent=tcText(" Active IR: ")+scene.cab_names.join(' + ');p.append(cab);panel.append(p);
    }
  }
}
function showDesign(plan){
  showSceneComparison(plan);
  intentPanel.replaceChildren();intentPanel.hidden=!plan.scene_intent?.goals?.length;
  if(!intentPanel.hidden){
    const heading=document.createElement('h3');heading.textContent=tcText("TONE TARGET PER SCENE");intentPanel.append(heading);
    for(const goal of plan.scene_intent.goals){
      const p=document.createElement('p'),title=document.createElement('strong');title.textContent=`${goal.scene}. ${goal.role}: `;
      p.append(title,document.createTextNode(goal.target));const detail=document.createElement('div');detail.textContent=goal.realization;p.append(detail);intentPanel.append(p);
    }
    const hint=document.createElement('p');hint.textContent=tcText("Design check, not listening evidence. ")+(plan.adjustment?tcText("Adjusted: {{v0}}. Protected: {{v1}}. The full design is reapplied with verification, not a minimal live patch.", {v0:(plan.adjustment.changed_scenes.join(', ')), v1:(plan.adjustment.preserved_scenes.join(', ')||tcText("none"))}):tcText("After SEND, check tone and balance at low physical volume."));intentPanel.append(hint);
  }
  const design=plan.design, controller=plan.controller;
  if(plan.mode==='album'){
    el('toneChoice').textContent=tcText("Up to four amp voicings and four cab channels A-D, with explicit assignments per scene; Output A -18dB.");
    el('controllerChoice').textContent=controller?.source?tcText("Wah A: {{v0}} | Auto Engage: {{v1}}. Global CC mapping unchanged.", {v0:(controller.source), v1:(controller.auto_engage||tcText("preserved"))}):tcText("Only configured effects are active; the existing wah binding is preserved. No NAM.");
    el('planWarnings').replaceChildren();for(const warning of plan.warnings||[]){const li=document.createElement('li');li.textContent=warning;el('planWarnings').append(li);}
    el('sceneTable').hidden=false;el('sceneRows').replaceChildren();
    const layout=design.scene_layout||design.albums.flatMap((a,c)=>[a.lead,a.solo].map(role=>({...role,amp_channel:c,cab_channel:c})));
    for(const [index,role] of layout.entries()){
      const album=design.albums[role.amp_channel],cab=plan.cab_choices[role.cab_channel],row=document.createElement('tr');
      const voice=album.drive;
      const drive=voice?tcText("Drive: {{v0}} | {{v1}} / {{v2}} | gain {{v3}}, tone {{v4}}, level knob {{v5}}/10, mix {{v6}}%", {v0:(role.drive?tcText("on"):tcText("off")), v1:(voice.model), v2:('ABCD'[role.amp_channel]), v3:(voice.gain), v4:(voice.tone), v5:(voice.level), v6:(voice.mix)}):tcText("Drive: off (no voicing)");
      const comp=album.compressor,eq=album.geq;
      const auxiliary=[drive,comp?`Compressor: ${role.compressor?tcText("on"):tcText("off")} / ${'ABCD'[role.amp_channel]} | ${comp.model}, threshold ${comp.threshold}dB, ratio ${comp.ratio}, attack ${comp.attack_ms}ms, release ${comp.release_ms}ms, mix ${comp.mix}%, level ${comp.level}dB, auto OFF`:tcText("Compressor: off (no voicing)"),
        eq?tcText("GEQ: {{v0}} / {{v1}} | {{v2}}, bands {{v3}}dB, Q {{v4}}, level {{v5}}dB", {v0:(role.geq?tcText("on"):tcText("off")), v1:('ABCD'[role.amp_channel]), v2:(eq.model), v3:(eq.gains.join('/')), v4:(eq.q), v5:(eq.level)}):tcText("GEQ: off (no voicing)")].join('\n');
      const wah=design.wah?`${role.wah?tcText("On"):tcText("Off")} | ${design.wah.model} (A), ${design.wah.frequency_min}-${design.wah.frequency_max}Hz`:tcText("Off");
      for(const value of [`${index+1}. ${role.name} / ${'ABCD'[role.amp_channel]}`,`${album.amp_model} | gain ${album.amp.gain} | EQ ${album.amp.bass}/${album.amp.mid}/${album.amp.treble} | ${album.amp.level}dB${album.amp.master===undefined?'':` | master ${album.amp.master}, depth ${album.amp.depth}, presence ${album.amp.presence}`}`,wah,role.chorus?tcText("{{v0}}Hz / {{v1}}% (shared A)", {v0:(design.chorus.rate_hz), v1:(design.chorus.mix)}):tcText("Off"),role.delay?tcText("{{v0}}ms / {{v1}}% / {{v2}}% (shared A)", {v0:(design.delay.time_ms), v1:(design.delay.feedback), v2:(design.delay.mix)}):tcText("Off"),tcText("Not in route"),`${auxiliary}\n${cabDescription(cab)} | Output A -18dB`]){const td=document.createElement('td');td.textContent=value;row.append(td);}
      el('sceneRows').append(row);
    }return;
  }
  if(plan.mode==='serial'){
    el('toneChoice').textContent=tcText("Measured AMP/CAB test chain: existing/default models retained, no model or IR selection.");
    el('controllerChoice').textContent=tcText("Wah and other reserve blocks bypassed; no new controller binding.");
    el('planWarnings').replaceChildren();for(const warning of plan.warnings||[]){const li=document.createElement('li');li.textContent=warning;el('planWarnings').append(li);}
    el('sceneTable').hidden=false;el('sceneRows').replaceChildren();
    const row=document.createElement('tr');
    for(const value of [`1. ${design.scene_name} / A`,`${design.amp.gain} / ${design.amp.level} dB`,tcText("Off"),design.chorus.active?`${design.chorus.rate_hz} Hz / mix ${design.chorus.mix}%`:tcText("Off"),design.delay.active?`${design.delay.time_ms} ms / feedback ${design.delay.feedback}% / mix ${design.delay.mix}%`:tcText("Off"),tcText("Not in route"),'Reserveblokken bypassed']){const td=document.createElement('td');td.textContent=value;row.append(td);}
    el('sceneRows').append(row);return;
  }
  if(plan.mode==='nam'){
    el('toneChoice').textContent=`NAM ${String(plan.capture.slot||1).padStart(3,'0')}: ${plan.capture.name} | Cab ${design.cab_active?tcText("existing retained"):'bypassed'}`;
    el('controllerChoice').textContent=tcText("FW33 controller writes not measured; no new binding.");
    el('planWarnings').replaceChildren();for(const warning of plan.warnings||[]){const li=document.createElement('li');li.textContent=warning;el('planWarnings').append(li);}
    el('sceneTable').hidden=false;el('sceneRows').replaceChildren();
    for(const [i,scene] of design.scenes.entries()){const tr=document.createElement('tr');
      for(const value of [`${i+1}. ${scene.name} / ${'AB'[i]}`,`NAM input ${scene.nam.input_gain} dB / level ${scene.nam.level} dB`,tcText("Not in route"),scene.chorus?tcText("On (shared A)"):tcText("Off"),scene.delay?tcText("{{v0}} ms (shared A)", {v0:(design.delay.time_ms)}):tcText("Off"),scene.reverb?tcText("On (shared A)"):tcText("Off"),tcText("No unverified extra pedals")]){const td=document.createElement('td');td.textContent=value;tr.append(td);}el('sceneRows').append(tr);
    }return;
  }
  const cabs=(plan.cab_choices||[]).map(cab=>`${cab.side}: ${cab.name} (${cab.position})`).join(' | ');
  el('toneChoice').textContent=cabs?`Amp: ${design?.amp_model||'?'} | ${cabs}`:design?`Amp: ${design.amp_model} | IR1: wire-bank ${design.cab_left.bank}, slot ${design.cab_left.slot}`+
    (design.cab_right?` | IR2: bank ${design.cab_right.bank}, slot ${design.cab_right.slot}`:' | IR2-4 gedempt'):'';
  if(design?.scenes.some(scene=>scene.amp_model||scene.cab_left))el('toneChoice').textContent=tcText("Amp and cab choices per scene: see the scene table for model, IR name, bank and channel.");
  el('controllerChoice').textContent=controller?.source?`Wah: ${controller.source} | Auto Engage: ${controller.auto_engage||tcText("existing mode preserved")}`:tcText("Wah controller: existing binding preserved.");
  el('planWarnings').replaceChildren();
  for(const warning of plan.warnings||[]){const li=document.createElement('li');li.textContent=warning;el('planWarnings').append(li);}
  el('sceneRows').replaceChildren();el('sceneTable').hidden=!design;
  for(const [i,scene] of (design?.scenes||[]).entries()){
    const tr=document.createElement('tr');
    const delay=scene.delay.active?`${scene.delay.time_ms} ms | feedback ${scene.delay.feedback}% | mix ${scene.delay.mix}%`:tcText("Off");
    const reverb=scene.reverb.active?`${scene.reverb.time_s} s | mix ${scene.reverb.mix}%`:tcText("Off");
    const chorus=scene.chorus?(scene.chorus.active?`${design.chorus_model||'Analog Stereo'} | ${scene.chorus.rate_hz} Hz | depth ${scene.chorus.depth}% | mix ${scene.chorus.mix}%`:tcText("Off")):
      plan.actions.some(a=>a.kind==='add_block'&&String(a.block).toUpperCase()==='CHORUS')?tcText("Off (not requested)"):tcText("Existing retained");
    const extras=[];
    for(const [key,label] of [['drive','Drive'],['compressor','Compressor'],['geq','GEQ'],['peq','PEQ']]){
      const config=scene[key];
      if(!config){
        const family={drive:'FUZZ',compressor:'COMP',geq:'GEQ',peq:'PEQ'}[key];
        if(plan.actions.some(a=>a.kind==='add_block'&&String(a.block).toUpperCase()===family))extras.push(tcText("{{v0}}: off (not requested)", {v0:(label)}));
        continue;
      }
      const model=config.model?` | ${config.model}`:'';
      if(!config.active){extras.push(tcText("{{v0}}: off{{v1}}", {v0:(label), v1:(model)}));continue;}
      const value=key==='drive'?`gain ${config.drive}, tone ${config.tone}, level ${config.level}/10, mix ${config.mix}%`:
        key==='compressor'?`threshold ${config.threshold} dB, ratio ${config.ratio}, attack ${config.attack_ms} ms, release ${config.release_ms} ms, mix ${config.mix}%, level ${config.level} dB`:
        key==='geq'?tcText("10 bands {{v0}} dB, level {{v1}} dB", {v0:config.gains.join('/'),v1:config.level}):
        tcText("bands {{v0}}, Q preserved, level {{v1}} dB", {v0:(config.bands.map(b=>`${b.frequency_hz} Hz/${b.gain} dB`).join(', ')), v1:(config.level)});
      extras.push(`${label}: ${value}${model}`);
    }
    const channels=plan.scene_channels;
    const ampChannel=channels?.DISTORT?.[i]??i;
    const mapping=channels?Object.entries(channels).filter(([family])=>!['FUZZ','COMP','GEQ','PEQ'].includes(family)||scene[{FUZZ:'drive',COMP:'compressor',GEQ:'geq',PEQ:'peq'}[family]]).map(([family,values])=>`${family} ${'ABCD'[values[i]]}`).join(' | '):'';
    const cabInfo=plan.scene_cabs?.[i]?.choices.map(cab=>`${cab.side}: ${cab.name} (${cab.position})`).join(' | ');
    const label=`${i+1}. ${scene.name} / ${'ABCD'[ampChannel]}`;
    for(const value of [label,`${scene.amp_model||design.amp_model} | gain ${scene.amp.gain} / ${scene.amp.level} dB | Output ${scene.output_level??-6} dB`,scene.wah?tcText("On"):tcText("Off"),chorus,delay,reverb,[extras.join('\n')||tcText("Existing retained"),cabInfo,mapping].filter(Boolean).join('\n')]){
      const td=document.createElement('td');td.textContent=value;tr.append(td);
    }
    el('sceneRows').append(tr);
  }
}
el('generate').onclick=()=>run(async()=>{
  if(!el('prompt').value.trim())throw new Error(tcText("Describe the desired sound or add a link first."));
  if(state.route_options_supported&&!adjusting){
    if(!routeExploration){await exploreRequestRoutes();return;}
    if(!routeExploration.routes.some(r=>r.mode===el('buildRoute').value&&r.enabled)){
      el('routeOptionsPanel').open=true;setTimeout(()=>el('buildRoute').focus(),0);
      note(tcText("Choose an executable build route. No proposal has been made and nothing has been sent yet."));return;
    }
  }
  if(!await ensureIntake(el('buildRoute').value||'auto'))return;
  invalidate();el('result').hidden=true;
  note(state.scene_contract_supported&&el('buildRoute').value==='amp'&&Number(el('scenes').value)>1&&!adjusting?tcText("TC records musical scene differences first, then develops the settings. Nothing is sent..."):tcText("AI is developing the proposal. Nothing is sent to the Fractal yet..."));
  stage(1);
  if(el('namWithRequest').checked&&!el('namQuery').value.trim())throw new Error(tcText("Enter a Tone3000 search term or disable search for this proposal."));
  const adjustTargets=[...adjustPanel.querySelectorAll('input:checked')].map(input=>Number(input.value));
  if(adjusting&&(!adjustTargets.length||!el('prompt').value.trim()))throw new Error(tcText("Choose scenes and describe your listening feedback."));
  if(sourceKind.value==='rig'&&el('audioFile').files.length)throw new Error(tcText("Rig explanations use text or a YouTube link. Remove the audio file or choose sound reference."));
  audioReference=sourceKind.value==='rig'?null:await analyseRequestAudio();
  proposal=await api('plan',{prompt:el('prompt').value,expected_preset:state.preset,scenes:Number(el('scenes').value),wah_source:el('wah').value||null,
    wah_auto_engage:el('wah').value?(el('wahMode').value||null):null,audio_reference:audioReference,
    ...(state.route_options_supported?{mode:el('buildRoute').value}:{}),
    ...(state.scene_contract_supported?{scene_contract:el('buildRoute').value==='amp'&&Number(el('scenes').value)>1&&!adjusting}:{}),
    nam_query:el('namWithRequest').checked?(el('namQuery').value||null):null,
    ...(adjusting?{refine_token:refineContext.token,adjust_scenes:adjustTargets}:{}),
    ...(state.request_intake_supported?{resolution:intakeResolution}:{}),
    ...dialoguePayload(),
    ...(state.nam_selection_supported&&(!state.route_options_supported||el('buildRoute').value==='nam')?{nam_slot:captureSlot.value?Number(captureSlot.value):null}:{}),
    ...(state.source_support?.rig_reader?{source_kind:sourceKind.value,rig_mode:rigMode.value}:{})});
  receiveDialogue(proposal);
  if(proposal.needs_clarification){const clarification=proposal.intake;proposal=null;showIntake(clarification);return;}
  el('conversation').textContent=proposal.summary;el('conversationPanel').hidden=false;
  el('emptyConversation').hidden=true;
  if(proposal.capture_search)showCaptures(proposal.capture_search);
  el('summary').textContent=proposal.summary;el('planName').textContent=proposal.name;
  el('who').textContent=tcText("AI: {{v0}} / {{v1}} | Target: preset {{v2}} | Proposal valid for 10 minutes", {v0:(proposal.backend||tcText("unknown")), v1:(proposal.model||tcText("unknown")), v2:(proposal.target.preset)})+
    (proposal.capture?` | NAM ${String(proposal.capture.slot).padStart(3,'0')}: ${proposal.capture.name}`:'');
  el('sceneNames').textContent=proposal.scenes.map((name,i)=>`${i+1}. ${name}`).join('\n');
  showDesign(proposal);
  el('rigReport').hidden=!proposal.rig_report;el('rigComponents').replaceChildren();
  if(proposal.rig_report){
    el('sourceTitle').textContent=tcText("{{v0}} | {{v1}} | reader: {{v2}}", {v0:(proposal.source?.title||tcText("Pasted rig explanation")), v1:(proposal.rig_report.mode), v2:(proposal.source?.spec?.reader?.backend||tcText("unknown"))});
    for(const entry of Object.values(proposal.rig_report.status.nodes)){
      const li=document.createElement('li');li.textContent=`${entry.label}: ${entry.state} (${entry.provenance}) - ${entry.reason}`;el('rigComponents').append(li);
    }
    for(const entry of Object.values(proposal.rig_report.status.edges)){
      if(entry.state==='not_reproduced'){const li=document.createElement('li');li.textContent=tcText("Connection: {{v0}}", {v0:(entry.reason)});el('rigComponents').append(li);}
    }
  }
  el('route').textContent=proposal.required_route.join(' → ');
  el('actionCount').textContent=tcText("View all {{v0}} changes", {v0:(proposal.actions.length)});
  el('actions').replaceChildren();
  for(const action of proposal.actions){const li=document.createElement('li');li.textContent=JSON.stringify(action);el('actions').append(li);}
  el('requestPreview').textContent=el('prompt').value.slice(0,160)+(el('prompt').value.length>160?'...':'');
  el('requestPreview').hidden=false;el('requestPanel').open=false;
  el('confirmTarget').textContent=`Preset ${proposal.target.preset}: ${proposal.name}`;
  el('confirmScope').textContent=tcText("{{v0}} changes; {{v1}} configured scenes. Shared channels may affect other scenes.", {v0:(proposal.actions.length), v1:(proposal.scenes.length)});
  stage(1);el('planPanel').focus();note(tcText("Proposal ready. Use REVIEW CHANGES to review and confirm."));
});
el('discard').onclick=()=>run(async()=>{invalidate();await api('discard',{});note(tcText("Proposal discarded. Nothing sent."));});
el('cabImport').onclick=()=>run(async()=>{
  const file=el('cabFile').files[0];if(!file)throw new Error(tcText("Choose a cab name list."));
  if(file.size>2*1024*1024)throw new Error(tcText("Up to 2 MiB of text."));
  invalidate();const result=await api('cabs',{kind:el('cabKind').value,text:await file.text()});
  await refresh();note(tcText("{{v0}} names imported{{v1}}. No IR audio or hardware changed. {{v2}}", {v0:(result.imported), v1:(result.locally_saved?tcText(" and saved locally"):tcText(" for this connection")), v2:(result.note||'')}));
});
el('send').onclick=()=>run(async()=>{
  if(!proposal||!el('confirmed').checked||!el('muted').checked)throw new Error(tcText("Confirm the target and external audio muting first."));
  if(currentStage!==3)throw new Error(tcText("Go to CONFIRM first."));
  const sentPlan=proposal,token=proposal.token;refineContext=null;adjusting=false;
  adjustPanel.hidden=true;el('generate').textContent='GENERATE PLAN';
  invalidate();note(tcText("Sending with verification. Keep external audio muted."));
  stage(4);
  let result;
  try{result=await api('send',{token,target_confirmed:true,external_audio_muted:true});}
  catch(e){throw new Error(tcText("Transmission not confirmed. Keep audio muted; do not automatically resend. ")+e.message);}
  refineContext=result.ok&&result.refine_token?{token:result.refine_token,count:sentPlan.scenes.length,mode:sentPlan.mode==='album'?'amp':sentPlan.mode||'amp',preset:state.preset}:null;
  adjusting=false;adjustPanel.hidden=true;el('generate').textContent='GENERATE PLAN';
  el('resultTitle').textContent=result.ok?tcText("Writes read back and confirmed"):tcText("Transmission stopped");
  el('resultText').textContent=tcText("{{v0}} actions confirmed; {{v1}} skipped.\n", {v0:(result.results.filter(r=>r.ok).length), v1:(result.skipped)})+
    (result.detail||'')+'\n'+result.results.filter(r=>!r.ok).map(r=>r.detail).join('\n')+
    tcText("\nNothing permanently stored. Check physical pedals, tone and balance separately at low physical volume.");
  await refresh();stage(4);el('result').focus();
  note(result.ok?tcText("Build complete; no audible result measured."):tcText("Stopped. Partial changes may remain; keep audio muted."));
});
run(refresh);
