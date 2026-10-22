// Real Chrome, local shipped assets, mocked APIs. No MIDI, network AI or server required.
const {chromium}=require(process.env.TC_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

(async()=>{
  const browser=await chromium.launch({headless:true,
    ...(process.env.TC_BROWSER_EXECUTABLE?{executablePath:process.env.TC_BROWSER_EXECUTABLE}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[],plans=[],sends=[],requestAttempts=[];
    let audioFetches=0,sourceBackendReady=true,routeOptionsReady=false,navigationReady=false,serialReady=false,multiSceneReady=false,albumReady=false;
    let currentPreset=325,currentScene=1,navigationRequest=null;
    let albumCounts=[8],wahReady=false,contractReady=false;
    let intakeReady=false,planNeedsClarification=false;const intakes=[];
    let aiDialogueReady=false,staleDialogue=false;const dialogueTurns=[];
    let audioV2Ready=false;
    const serialRoute=['Input 1','Wah 1','Drive 1','Amp 1','Cab 1','Chorus 1','Compressor 1','Delay 1','Enhancer 1','Filter 1','Flanger 1','GEQ 1','PEQ 2','Output 1'];
    const navigationSelections=[];
    const explorations=[],audioComparisons=[];
    let ampRefreshMode='same';const ampRefreshes=[];
    page.on('pageerror',e=>errors.push(e.message));
    let failPlan=false,failSend=false,failRead=false,addedExtras=false;
    let disconnected=false,routeProblem='',failedTransport='',invalidPlanReply=false,largePlan=false,holdPlan=null;
    let variant=null,fw33=false,namRoute=false,selected=null,slotsFull=false,slotsFail=false;
    const installs=[],stores=[],previews=[],historyResumes=[];
    await page.route('**/*',async route=>{
      const req=route.request(),url=new URL(req.url()),name=url.pathname.split('/').pop();
      if(url.pathname.startsWith('/language/'))return route.fulfill({contentType:name.endsWith('.json')?'application/json':'text/javascript',body:fs.readFileSync(path.join(__dirname,'../ui/languages',name))});
      if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:'<title>FM9 test workspace</title>'});
      if(url.pathname==='/api/controllers/disconnect'){
        requestAttempts.push({path:url.pathname,method:req.method()});
        return route.fulfill({contentType:'application/json',body:JSON.stringify({connected:false})});
      }
      if(url.pathname==='/logo.png')return route.fulfill({contentType:'image/png',body:fs.readFileSync(path.join(__dirname,'../ui/logo.png'))});
      if(url.pathname==='/axefx3.css'){
        const source=fs.readFileSync(path.join(__dirname,'../ui/index.html'),'utf8');
        return route.fulfill({contentType:'text/css',body:source.split('<style>')[1].split('</style>')[0]});
      }
      if(url.pathname==='/axefx3'||url.pathname==='/axefx3.js'){
        return route.fulfill({contentType:name.endsWith('.js')?'text/javascript':'text/html',
          body:fs.readFileSync(path.join(__dirname,'../ui',name==='axefx3'?'axefx3.html':name),'utf8')});
      }
      if(!url.pathname.startsWith('/api/axefx3/'))return route.fulfill({status:404,body:''});
      requestAttempts.push({path:url.pathname,method:req.method()});
      if(name===failedTransport)return route.abort('failed');
      if(name==='plan'&&invalidPlanReply)return route.fulfill({status:502,contentType:'text/html',body:'<h1>Bad gateway</h1>'});
      if(name==='plan'&&holdPlan)await holdPlan;
      let status=200,result={};
      if(url.pathname==='/api/axefx3/amps/refresh'){
        ampRefreshes.push(req.postDataJSON());
        const names=JSON.parse(fs.readFileSync(path.join(__dirname,'../devices/axefx3/data/fw33_amp_models.json'),'utf8')).models;
        result={inventory:{count:336,models:Object.entries(names).map(([ordinal,name])=>({ordinal:Number(ordinal),name}))},
          status:ampRefreshMode==='new'?'verification_required':'up_to_date',message:ampRefreshMode==='new'?'Nieuw model, eerst verificatie vereist':'Actueel: 336 modellen',
          added:ampRefreshMode==='new'?[{ordinal:336,name:'<img src=x onerror=alert(1)> New amp'}]:[],changed:[],removed:[]};
        if(ampRefreshMode==='error'){status=409;result={detail:'Firmware changed; RESCAN first'};}
      }
      if(url.pathname==='/api/axefx3/tone3000/status')result={configured:true,connected:true,selected,installation_supported:fw33&&variant==='mk2'};
      if(url.pathname==='/api/axefx3/tone3000/tones')result={data:[{id:42,title:'<img src=x onerror=alert(1)> Plexi',creator:{username:'test'}}]};
      if(url.pathname==='/api/axefx3/tone3000/tones/42')result={tone:{title:'Capture',description:'Untrusted creator claim'},models:[{id:7,name:'Synthetic A2'}]};
      if(url.pathname==='/api/axefx3/tone3000/select'){selected={model:{id:7,name:'Synthetic A2'}};result={selected};}
      if(url.pathname==='/api/axefx3/tone3000/slots'){
        result={complete:true,first_available:slotsFull?null:2,slots:Array.from({length:256},(_,i)=>({slot:i+1,name:i===0||slotsFull?'Old capture':'<EMPTY>',occupied:i===0||slotsFull}))};
        if(slotsFail){status=409;result={detail:'NAM inventory incomplete'};}
      }
      if(url.pathname==='/api/axefx3/tone3000/install/prepare'){
        const body=req.postDataJSON();previews.push(body);
        result={prepared_id:'install-ticket',name:'Synthetic A2',slot:body.slot,existing_name:body.slot===1||slotsFull?'Old capture':'<EMPTY>',existing_occupied:body.slot===1||slotsFull,expected_preset:325};
      }
      if(url.pathname==='/api/axefx3/tone3000/install'){installs.push(req.postDataJSON());result={bytes_verified:65536};}
      if(url.pathname==='/api/axefx3/store/prepare')result={token:'store-ticket',preset:325,name:'AI-Test NAM',replaces:'Old stored preset'};
      if(url.pathname==='/api/axefx3/store'){stores.push(req.postDataJSON());result={ok:true,stored:true,preset:325,name:'AI-Test NAM'};}
      if(url.pathname==='/api/axefx3/navigation/presets')result={readonly:true,slots:[{number:325,name:'Test'},{number:326,name:'<img src=x> Damage INC'}]};
      if(url.pathname==='/api/axefx3/navigation/prepare'){
        navigationRequest=req.postDataJSON();result={token:'navigation-test-ticket',kind:navigationRequest.kind,destination:{number:navigationRequest.value,name:'Selected'}};
      }
      if(url.pathname==='/api/axefx3/navigation/select'){
        navigationSelections.push(req.postDataJSON());
        if(navigationRequest.kind==='preset')currentPreset=navigationRequest.value;else currentScene=navigationRequest.value;
        result={ok:true,kind:navigationRequest.kind,selected:navigationRequest.value,stored:false};
      }
      if(name==='state'){
        result={connected:!disconnected,preset:currentPreset,name:'Test',scene:currentScene,firmware:fw33?'33.00-beta.20261006':'32.06',cab_count:fw33?0:20,
          source_support:{rig_reader:true,modes:['closest','faithful','simplified']},
          nam_selection_supported:fw33,nam:fw33?{slot:1,name:'Old capture'}:null,
          profile:{variant,warning:'Memory policy from declared variant',user2_cabs:true}};
        if(routeProblem)result.route_problem=routeProblem;
        if(!sourceBackendReady)delete result.source_support;
        if(audioV2Ready)result.audio_analysis_version=2;
        if(serialReady)result.serial_build_supported=true;
        if(albumReady){result.album_build_supported=true;result.amp_refresh_supported=true;result.design_history_supported=true;
          result.wah_planning_supported=wahReady;
          result.scene_contract_supported=contractReady;
          result.album_scene_counts=albumCounts;
          const models=JSON.parse(fs.readFileSync(path.join(__dirname,'../devices/axefx3/data/fw33_amp_models.json'),'utf8')).models;
          result.amp_inventory={count:336,models:Object.entries(models).map(([ordinal,name])=>({ordinal:Number(ordinal),name}))};
          result.workspace={revision:'abc1234',source_root:'C:/test/current-checkout',pid:1234};
          result.cab_selection_note='Usercabselectie via actuele metadata; geen IR-installatie.';
          const banks=JSON.parse(fs.readFileSync(path.join(__dirname,'../devices/axefx3/data/fw33_cab_models.json'),'utf8')).banks;
          result.cab_inventory=Object.entries(banks).flatMap(([bank,names])=>Object.entries(names).map(([ordinal,name])=>({bank:Number(bank),slot:Number(ordinal)+1,name,position:`FACTORY ${Number(bank)+1} slot ${Number(ordinal)+1}`})));
          result.cab_inventory.push({bank:3,slot:1024,name:'<img src=x onerror=alert(1)> User cab',position:'USER 2 slot 1024'});
          result.cab_mix={supported:true,channel:0,slots:[{slot:1,bank:3,ordinal:1023,status:'IN MIX',level_db:-6.1,pan:-70},{slot:2,bank:1,ordinal:515,status:'MUTED',level_db:-6.1,pan:70}]};}
        if(multiSceneReady){result.multiscene_planning_supported=!fw33;result.request_scene_limit=8;}
        if(routeOptionsReady)result.route_options_supported=true;
        if(intakeReady)result.request_intake_supported=true;
        if(aiDialogueReady)result.ai_clarification_supported=true;
        if(navigationReady){result.navigation_supported=true;result.scene_names=Array.from({length:8},(_,i)=>[i+1,i?'Solo':'Rhythm']);}
        if(fw33)result.route=namRoute?['Input 1','NAM 1','Cab 1','Delay 1','Chorus 1','Reverb 1','Output 1']:[];
        if(serialReady){result.route=serialRoute;result.route_blocks=result.route.map((label,i)=>({label,channel:'A',bypassed:[1,2,6,8,9,10,11,12].includes(i)}));}
        if(failRead){status=409;result={detail:'Read failed'};}
      }
      if(name==='intake'){
        const body=req.postDataJSON();intakes.push(body);
        const answer=body.resolution||{},questions=[];
        const count=answer.scene_count_override?body.scenes:4;
        if(!answer.pitch_meaning)questions.push({id:'pitch_meaning',kind:'choice',text:'Hogere wah-filterstand of echte pitchverhoging?',options:[{value:'filter',label:'Hogere wah-filterstand'},{value:'pitch',label:'Echte pitchverhoging'}]});
        if(body.mode!=='auto'&&!answer.accepted_omissions?.includes('wah_controller'))questions.push({id:'wah_controller',kind:'omission',text:'External 2 met Auto Engage is niet geverifieerd. Dit onderdeel uitstellen?'});
        if(body.mode!=='auto'&&answer.pitch_meaning==='pitch'&&!answer.accepted_omissions?.includes('pitch'))questions.push({id:'pitch',kind:'omission',text:'Pitchverhoging niet geverifieerd. Uitstellen?'});
        if(body.mode==='nam'&&count>2)questions.push({id:'route_scenes',kind:'scenes',text:'Kies AMP/CAB voor vier scenes, of bewust minder scenes.'});
        result={ready:!questions.length,scenes:count,questions,approved_omissions:answer.accepted_omissions||[],readonly:true,hardware_written:false};
        if(!/Steve vai/i.test(body.prompt))result={ready:true,scenes:/4 scenes/.test(body.prompt)?4:body.scenes,questions:[],readonly:true,hardware_written:false};
      }
      if(name==='options'){
        explorations.push(req.postDataJSON());
        result={readonly:true,hardware_written:false,
          comparison:{recommended:'amp',reason:'Compare both, no automatic selection',amp_direction:'Brit crunch',nam_query:'Whole Lotta Love',pedals:['<img src=x> Delay']},
          routes:[{mode:'amp',label:'AMP / CAB + pedals',enabled:!fw33||albumReady,reason:'Model selection requires measured firmware'},
                  {mode:'nam',label:"NAM + suitable effects",enabled:fw33,reason:'Installed compatible capture required'}],nam_candidates:[]};
        if(serialReady)result.routes.push({mode:'serial',label:'AMP / CAB: gemeten testketen',enabled:true,reason:'Vaste14-blokkenketen, modellen behouden.'});
      }
      if(name==='history')result={designs:[{id:'a'.repeat(32),preset:currentPreset,name:'<img src=x> Saved design',created:'2026-10-16T12:00:00Z'}],unreadable:0,hardware_written:false};
      if(url.pathname==='/api/axefx3/history/resume'){
        historyResumes.push(req.postDataJSON());currentScene=1;
        result={ok:true,refine_token:'new-history-refine-token',preset:currentPreset,scene:1,
          scenes:Array.from({length:8},(_,i)=>'Scene'+(i+1)),mode:'amp',warning:'Alle acht scenes opnieuw gecontroleerd; geen parameters geschreven.'};
      }
      if(name==='plan'){
        plans.push(req.postDataJSON());
        result={token:'one-use',name:'AI-Test',summary:'<img src=x onerror=alert(1)>',backend:'codex',model:'test',
          target:{preset:325},scenes:['Clean','Crunch','Heavy','Lead'],
          required_route:['Input 1','Wah 1','Amp 1','Cab 1','Output 1'],
          actions:[{kind:'set_param',param:'DISTORT_DRIVE',value:5}]};
        result.controller={source:req.postDataJSON().wah_source,auto_engage:req.postDataJSON().wah_auto_engage};
        result.warnings=['<img src=x onerror=alert(1)> Wah bypass warning'];
        result.cab_choices=[{side:'IR1',name:'Test Greenback',position:'USER 1 slot 28'}];
        result.design={amp_model:'Test Plexi',chorus_model:'Analog Stereo',cab_left:{bank:2,slot:28},cab_right:null,
          scenes:['Intro','Main','Heavy','Lead'].map((name,i)=>({name,amp:{gain:i+3,level:-15},wah:i===0||i===3,
            delay:{active:i===0||i===3,time_ms:280+i*30,feedback:20,mix:15},reverb:{active:true,time_s:1.2,mix:8},
            chorus:i===2?null:{active:i!==1,rate_hz:.3,depth:25,mix:20},
            drive:i===0?{model:'T808 Mod',active:true,drive:6,tone:4,level:2,mix:100}:null,
            compressor:i===1?{model:'Classic VCA Compressor',active:true,threshold:-30,ratio:4,attack_ms:5,release_ms:250,mix:75,level:-12}:null,
            geq:i===2?{active:true,gains:Array(10).fill(-3),level:-6}:null,
            peq:i===3?{active:true,bands:[200,400,800,1600,3200].map(frequency_hz=>({frequency_hz,gain:-3})),level:-6}:null}))};
        if(addedExtras){
          result.actions.push({kind:'add_block',block:'FUZZ'},{kind:'add_block',block:'COMP'});
          result.required_route=['Input 1','Wah 1','Drive 1','Compressor 1','Amp 1','Cab 1','Output 1'];
        }
        if(multiSceneReady&&!fw33){
          const original=result.design.scenes;
          result.design.scenes=original.flatMap((scene,i)=>['Lead','Solo'].map((role,j)=>({...scene,name:`Album ${i+1} ${role}`,output_level:j?-6:-9})));
          result.scenes=result.design.scenes.map(s=>s.name);result.name='AI-Metallica albums';
          result.scene_channels={DISTORT:[0,0,1,1,2,2,3,3],CABINET:[0,0,1,1,2,2,3,3],OUTPUT:[0,1,0,1,0,1,0,1]};
          result.scene_cabs=result.scenes.map((name,i)=>({scene:i+1,channel:'ABCD'[Math.floor(i/2)],choices:[{side:'IR1',name:`Album cab ${Math.floor(i/2)+1}`,position:'USER 1 slot 28'}]}));
        }
        if(fw33){
          result.mode='nam';result.capture={name:'Synthetic A2',slot:req.postDataJSON().nam_slot||1,bytes:65536,sha256:'a'.repeat(64)};
          result.required_route=['Input 1','NAM 1','Cab 1','Delay 1','Chorus 1','Reverb 1','Output 1'];
          result.scenes=['Rhythm','Solo'].slice(0,req.postDataJSON().scenes);
          result.design={cab_active:false,delay:{time_ms:350},scenes:result.scenes.map(name=>({name,nam:{input_gain:0,level:-16},chorus:true,delay:true,reverb:true}))};
        }
        if(req.postDataJSON().mode==='serial'){
          result.mode='serial';delete result.capture;result.scenes=['Crunch'];
          result.design={scene_name:'Crunch',amp:{gain:5.5,level:-18},delay:{active:true,time_ms:320,feedback:20,mix:18},chorus:{active:true,rate_hz:.7,mix:12}};
          result.required_route=['Input 1','Wah 1','Drive 1','Amp 1','Cab 1','Chorus 1','Compressor 1','Delay 1','Enhancer 1','Filter 1','Flanger 1','GEQ 1','PEQ 2','Output 1'];
        }
        if(albumReady&&req.postDataJSON().mode==='amp'){
          result.mode='album';delete result.capture;result.required_route=serialRoute;
          result.design={albums:Array.from({length:4},(_,c)=>({amp_model:c?'USA JP IIC+ Yellow':'Brit 800 2204 High',amp:{gain:5+c,bass:4,mid:5,treble:6,level:-18},lead:{name:`Album ${c+1} Lead`,delay:false,chorus:false},solo:{name:`Album ${c+1} Solo`,delay:true,chorus:true}})),delay:{time_ms:350,feedback:25,mix:18},chorus:{rate_hz:.7,mix:10}};
          for(const [c,album] of result.design.albums.entries())album.drive={model:'T808 Mod',gain:c,tone:5,level:1.5,mix:100};
          result.scenes=result.design.albums.flatMap(a=>[a.lead.name,a.solo.name]);
          result.design.scene_layout=result.scenes.map((name,i)=>({name,amp_channel:i%4,cab_channel:[0,3,2,1,0,1,2,3][i],delay:i%2===1,chorus:i===7}));
          for(const [i,role] of result.design.scene_layout.entries())role.drive=i%2===1;
          if(wahReady&&req.postDataJSON().wah_source){result.design.wah={model:'Cry Babe',frequency_min:350,frequency_max:3000};
            for(const [i,role] of result.design.scene_layout.entries())role.wah=i%2===1;}
          if(contractReady){
            result.scene_comparison={contract:{scenes:[{scene:1,role:'Theme',target:'Expressieve lead',reason:'Muzikale uitgangsklank.'}]},
              rows:Array.from({length:req.postDataJSON().scenes},(_,i)=>({scene:i+1,name:i===3?'Outro':'Scene '+(i+1),
                reference_scene:i?1:null,same_as:i===3?[1]:[],reuse_reason:i===3?'De gebruiker vraagt dezelfde themaklank.':null,
                changes:i?['gain: 5 -> 7','Andere actieve cab-IR of IR-mix']:[],small_variation:i===2,
                cab_names:['2x12 Leggy 57 <img src=x>']})),
              notice:'Vergelijking van geplande instellingen, geen luistertest.'};
          }
          result.cab_choices=Array.from({length:4},(_,c)=>({channel:'ABCD'[c],slot:c?800:516,name:c?'4x12 Recto57A':'4x12 Brit70s GB57A'}));
          result.cab_choices[0]={channel:'A',irs:[{ir:1,bank:3,slot:1024,name:'<img src=x> User cab',mode:'normal',level_db:-6.1,pan:-70},{ir:2,bank:1,slot:516,name:'Selected but muted cab',mode:'mute',level_db:-6.1,pan:70}]};
        }
        if(req.postDataJSON().source_kind==='rig'){
          result.source={title:'<img src=x onerror=alert(1)> Explained rig',spec:{reader:{backend:'codex'}}};
          result.rig_report={mode:req.postDataJSON().rig_mode,status:{nodes:{amp:{label:'<img src=x> Amp',state:'changed',provenance:'observed',reason:'Installed capture interpretation'},wah:{label:'Wah',state:'not_reproduced',provenance:'observed',reason:'Not measured'}},edges:{pedal:{state:'not_reproduced',reason:'No verified controller mapping'}}}};
        }
        if(failPlan){status=409;result={detail:'AI output refused'};}
        if(!failPlan)result.scene_intent={goals:result.scenes.map((name,i)=>({scene:i+1,target:'<img src=x> Requested tone',role:name,realization:'Settings follow the requested sound.'})),audible_match_verified:false};
        if(largePlan){result.summary='Een uitgebreid voorstel met uitleg per album, scene en beschikbaar effect. '.repeat(100);
          result.actions=Array.from({length:200},(_,i)=>({kind:'set_param',param:'DISTORT_MID',value:5,reason:`Controleer wijziging ${i+1}`}));}
        if(intakeReady){result.scenes=result.scenes.slice(0,req.postDataJSON().scenes);
          if(result.design.scene_layout)result.design.scene_layout=result.design.scene_layout.slice(0,req.postDataJSON().scenes);
          result.warnings.push('Expliciet uitgesteld, NIET uitgevoerd: wah-controller en Auto Engage.');}
        if(planNeedsClarification)result={needs_clarification:true,hardware_written:false,intake:{ready:false,scenes:4,questions:[{id:'design_requirement',kind:'message',text:'Ontwerp niet uitvoerbaar, geen AI-verbindingsfout.'}]}};
      }
      if(name==='send'){
        sends.push(req.postDataJSON());
        result={ok:!failSend,skipped:failSend?100:0,stored:false,
          ...(failSend?{}:{refine_token:'verified-sound-design-token'}),
          results:[{ok:!failSend,detail:failSend?'Readback mismatch':'Verified'}]};
        if(fw33&&!failSend)namRoute=true;
      }
      if(name==='cabs')result={imported:20};
      if(name==='profile'){variant=req.postDataJSON().variant;result={profile:{variant},hardware_written:false};}
      if(name==='search')result={candidates:[{id:42,title:'<img src=x onerror=alert(1)> Plexi',creator:'test'}]};
      if(name==='audio'){
        audioFetches++;
        const size=32000,buf=Buffer.alloc(44+size*2);
        buf.write('RIFF');buf.writeUInt32LE(buf.length-8,4);buf.write('WAVEfmt ',8);buf.writeUInt32LE(16,16);
        buf.writeUInt16LE(1,20);buf.writeUInt16LE(1,22);buf.writeUInt32LE(16000,24);buf.writeUInt32LE(32000,28);
        buf.writeUInt16LE(2,32);buf.writeUInt16LE(16,34);buf.write('data',36);buf.writeUInt32LE(size*2,40);
        for(let i=0;i<size;i++)buf.writeInt16LE(Math.round(8000*Math.sin(2*Math.PI*440*i/16000)),44+2*i);
        return route.fulfill({contentType:'audio/wav',body:buf});
      }
      if(url.pathname==='/api/axefx3/audio/compare'){
        audioComparisons.push(req.postDataJSON());
        result={hardware_written:false,differences:{rms_db:0,peak_db:0,crest_db:0,centroid_hz:0,
          band_energy:[{band:'250-600 Hz',delta_fraction:0,relative_db:0}]},
          note:'<img src=x onerror=alert(1)> Geen bewijs van klankmatch of luidheid.'};
      }
      if(aiDialogueReady&&(name==='options'||name==='plan')){
        const body=req.postDataJSON();dialogueTurns.push({phase:name,...body});
        const options=name==='options',id=options?'width':'role';
        const question={id,text:options?'Bedoel je stereobreedte, voller of harder?':'Is de klank voor ritme of solo?',suggestions:options?['Stereobreedte','Voller','Harder']:['Ritme','Solo']};
        const pending=options?'ai-question-options-ticket':'ai-question-plan-ticket';
        const history=[{message:'De breedte vraagt verduidelijking.',questions:[{id:'width',text:'Welke breedte?'}],answers:[{id:'width',text:'<img src=x onerror=alert(1)> Breder stereo, niet harder'}]}];
        if(!body.answers?.length){
          result={needs_clarification:true,hardware_written:false,dialogue_token:pending,dialogue_history:options?[]:history,
            intake:{ready:false,scenes:4,message:'TC vraagt alleen wat nog onduidelijk is.',questions:[{...question,kind:'answer'}]}};
        }else{
          result.dialogue_token=options?'ai-options-ready-ticket':'ai-design-ready-ticket';
          result.dialogue_history=options?history:[...history,{message:'Rol bepalen.',questions:[question],answers:body.answers}];
        }
        if(staleDialogue){status=409;result={detail:{code:'dialogue_stale',message:'Het gesprek is verlopen. Klik opnieuw; je verzoek blijft behouden.'}};}
      }
      await route.fulfill({status,contentType:'application/json',body:JSON.stringify(result)});
    });
    async function review(){
      await page.click('#engage');await page.locator('#pane-plan:not([hidden])').waitFor();
      assert(await page.locator('#pane-review').isHidden());
      assert(await page.locator('#pane-confirm').isHidden());
      await page.click('#reviewbtn');await page.locator('#pane-review:not([hidden])').waitFor();
    }
    async function request(){
      await page.click('#rail [data-step="0"]');
      if((await page.locator('#requestPanel').getAttribute('open'))===null)await page.click('#requestPanel summary');
      if((await page.locator('#requestOptions').getAttribute('open'))===null)await page.click('#requestOptions summary');
    }
    async function confirmSend(){
      await page.click('#toconfirm');
      assert(await page.locator('#pane-review').isHidden());
      assert(await page.locator('#apply').isDisabled());
      await page.check('#confirmed');assert(await page.locator('#apply').isDisabled());
      await page.check('#muted');assert(await page.locator('#apply').isEnabled());
      await page.click('#apply');
    }
    await page.goto('http://tc.test/axefx3');await page.locator('#engage:not([disabled])').waitFor();
    const dsp=await page.evaluate(async()=>{
      const rate=44100;
      const stereo=new AudioBuffer({numberOfChannels:2,length:rate,sampleRate:rate});
      const a=stereo.getChannelData(0),b=stereo.getChannelData(1);
      for(let i=0;i<rate;i++){a[i]=.25*Math.sin(2*Math.PI*440*i/rate);b[i]=-a[i];}
      const opposite=await measureWindowV2(stereo,0,rate);
      const mixed=new AudioBuffer({numberOfChannels:1,length:rate,sampleRate:rate}),samples=mixed.getChannelData(0);
      for(let i=0;i<rate;i++)samples[i]=.25*(Math.sin(2*Math.PI*440*i/rate)+Math.sin(2*Math.PI*12000*i/rate));
      const antialias=await measureWindowV2(mixed,0,rate);
      let silence=false,invalid=false;const validationErrors=[];
      try{await measureWindowV2(new AudioBuffer({numberOfChannels:1,length:16000,sampleRate:16000}),0,16000);}catch(e){validationErrors.push(e.message);silence=/no measurable/.test(e.message);}
      samples[0]=NaN;try{await measureWindowV2(mixed,0,rate);}catch(e){validationErrors.push(e.message);invalid=/invalid samples/.test(e.message);}
      return {opposite,antialias,silence,invalid,validationErrors};
    });
    assert.equal(dsp.opposite.analysis_channels,2);assert.equal(dsp.opposite.analysis_rate_hz,16000);
    assert(Math.abs(dsp.opposite.rms_dbfs-(-15.0515))<.06);
    assert(Math.abs(dsp.opposite.centroid_hz-440)<40);assert(dsp.opposite.band_energy[1]>.98);
    assert(Math.abs(dsp.antialias.centroid_hz-440)<60,JSON.stringify(dsp.antialias));assert(dsp.antialias.band_energy[1]>.95);
    assert(Math.abs(dsp.antialias.rms_dbfs-(-12.0412))<.06);assert(dsp.antialias.peak_dbfs>-6.2);
    assert(dsp.silence&&dsp.invalid,JSON.stringify(dsp.validationErrors));
    assert.equal(await page.locator('#rail .stg').count(),5);
    assert.equal(await page.locator('#sceneRack .sc').count(),8);
    assert(await page.locator('#scenes option').nth(4).evaluate(o=>o.disabled));
    assert.equal(await page.locator('#shell').evaluate(x=>getComputedStyle(x).display),'flex');
    assert.equal(await page.locator('#hwbar h1').evaluate(x=>getComputedStyle(x).color),'rgb(47, 230, 255)');
    assert.equal(await page.locator('#requestOptions').getAttribute('open'),null);
    if(process.env.TC_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.TC_SCREENSHOT_DIR,'fm9-layout-request.png')});
    for(const width of [1440,1280,1180]){
      await page.setViewportSize({width,height:1000});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      for(const id of ['hwbar','context','workspace','shelf','engage']){
        assert(await page.locator('#'+id).evaluate(x=>{
          const r=x.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;
        }),id+' must fit at '+width);
      }
    }
    await page.setViewportSize({width:1440,height:1000});
    await page.fill('#prompt','Maak vier scenes');await page.press('#prompt','End');await page.press('#prompt','Enter');
    assert.equal(plans.length,0);assert((await page.inputValue('#prompt')).endsWith('\n'));
    await page.click('#requestOptions summary');
    await page.selectOption('#wah','External 1');await page.selectOption('#wahMode','Off');
    await review();
    assert.equal(plans[0].wah_source,'External 1');assert.equal(plans[0].expected_preset,325);
    assert.equal(plans[0].wah_auto_engage,'Off');
    assert.equal(await page.locator('#sceneRows tr').count(),4);
    for(const value of ['280 ms','Analog Stereo','T808 Mod','Classic VCA Compressor','GEQ: 10 bands','Q preserved']){
      assert((await page.textContent('#sceneRows')).includes(value));
    }
    assert.equal(await page.locator('#sceneRows tr').first().locator('td').count(),7);
    assert.equal(await page.locator('#planWarnings img').count(),0);
    assert.equal(await page.locator('#requestPanel').getAttribute('open'),null);
    await request();assert.equal(await page.inputValue('#prompt'),'Maak vier scenes\n');
    assert.equal(await page.locator('#conversation img').count(),0);
    await page.click('#rail [data-step="2"]');
    if(process.env.TC_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.TC_SCREENSHOT_DIR,'fm9-layout-review.png')});
    await page.click('#toconfirm');
    await page.check('#confirmed');await page.check('#muted');
    assert((await page.textContent('#confirmTarget')).includes('325'));
    await request();await page.fill('#prompt','Different sound');
    assert(await page.locator('#pane-review').isHidden());assert.equal(sends.length,0);
    assert(!(await page.isChecked('#confirmed')));
    addedExtras=true;await review();
    assert.match(await page.textContent('#sceneRows tr:nth-child(1)'),/Compressor: off/);
    await confirmSend();await page.locator('#pane-send:not([hidden])').waitFor();
    await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(sends.length,1);assert.equal(sends[0].external_audio_muted,true);
    assert.match(await page.textContent('#resultText'),/Nothing permanently stored/);
    await request();failPlan=true;await page.click('#engage');
    await page.waitForFunction(()=>document.getElementById('status').textContent==='AI output refused');
    assert(await page.locator('#pane-request').isVisible());assert(await page.locator('#engage').isEnabled());
    failPlan=false;failSend=true;await review();await confirmSend();
    await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Stopped.'));
    assert.equal(sends.length,2);assert.match(await page.textContent('#resultText'),/Readback mismatch/);
    failRead=true;await page.click('#refresh');
    await page.waitForFunction(()=>document.getElementById('status').textContent==='Read failed');
    assert(await page.locator('#engage').isDisabled());
    failRead=false;await page.click('#refresh');await page.locator('#engage:not([disabled])').waitFor({state:'attached'});
    await request();await page.selectOption('#wahMode','Fast Pos');await review();await request();
    await page.selectOption('#wahMode','Off');assert(await page.locator('#pane-review').isHidden());
    await page.selectOption('#wah','');assert(await page.locator('#wahMode').isDisabled());
    await page.setViewportSize({width:390,height:844});
    assert(await page.locator('#unsupported').isVisible());assert(await page.locator('#shell').isHidden());
    await page.setViewportSize({width:1440,height:1000});
    await page.selectOption('#variant','mk2');await page.locator('#variant:not([disabled])').waitFor();
    assert.equal(await page.inputValue('#variant'),'mk2');
    await page.click('#namPanel summary');await page.fill('#namQuery','Marshall Plexi');await page.click('#namSearch');
    await page.locator('#namResults button').waitFor();
    assert.equal(await page.locator('#namResults img').count(),0);
    assert.match(await page.locator('#namResults button').textContent(),/Plexi/);
    page.once('dialog',dialog=>dialog.accept());await page.click('#newDesign');
    await page.locator('#prompt:not([disabled])').waitFor();assert.equal(await page.inputValue('#prompt'),'');
    await page.fill('#prompt','Maak de klank van https://youtu.be/test');await review();
    const measurement=plans.at(-1).audio_reference;
    assert.equal(measurement.url,'https://youtu.be/test');assert(Math.abs(measurement.centroid_hz-440)<30);
    assert(measurement.sample_seconds>1.9&&measurement.sample_seconds<=2);
    assert.equal(sends.length,2);
    assert.equal(measurement.start_seconds,0);assert.equal(measurement.source_seconds,2);
    await request();await page.locator('#audioPanel summary').click();
    await page.fill('#audioStart','1');await page.fill('#audioLength','0.5');
    assert(await page.locator('#pane-review').isHidden());
    const fetchesBeforeWindow=audioFetches;
    await review();
    const selectedWindow=plans.at(-1).audio_reference;
    assert.equal(selectedWindow.start_seconds,1);assert.equal(selectedWindow.sample_seconds,0.5);
    assert(Math.abs(selectedWindow.centroid_hz-440)<40);assert.equal(audioFetches,fetchesBeforeWindow+1);
    await request();await page.fill('#audioStart','5');
    const plansBeforeInvalidWindow=plans.length;await page.click('#engage');
    await page.locator('#engage:not([disabled])').waitFor();
    assert.equal(plans.length,plansBeforeInvalidWindow);assert.match(await page.textContent('#status'),/start time is outside/);
    await page.fill('#audioStart','0');await page.fill('#audioLength','60');
    await page.locator('#audioPanel summary').click();
    // The FW33 foundation cannot select unverified scenes or Wah bindings.
    fw33=true;failSend=false;await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(await page.inputValue('#scenes'),'1');assert(await page.locator('#wah').isDisabled());
    assert(await page.locator('#scenes option').nth(1).evaluate(option=>option.disabled));
    await page.click('#namResults button');await page.locator('#namResults button').waitFor();
    await page.click('#namResults button');await page.locator('#namSlotsRefresh:not([disabled])').waitFor();
    assert(await page.locator('#namInstallPrepare').isDisabled());
    await page.click('#namSlotsRefresh');await page.locator('#namSlot:not([disabled])').waitFor();
    assert.equal(await page.locator('#namSlot option').count(),256);
    assert.equal(await page.inputValue('#namSlot'),'2');assert.equal(previews.length,0);assert.equal(installs.length,0);
    assert.match(await page.textContent('#namSlotsHint'),/First empty slot: 002/);
    await page.selectOption('#namSlot','250');
    await page.click('#namInstallPrepare');await page.locator('#namInstallPanel:not([hidden])').waitFor();
    assert.equal(previews.at(-1).slot,250);assert.match(await page.textContent('#namSlotConsent'),/NAM slot 250/);
    assert.match(await page.textContent('#namInstallWarning'),/verified empty again/);
    assert.equal(installs.length,0);assert(await page.locator('#namInstallCommit').isDisabled());
    await page.check('#namInstallMute');await page.check('#namInstallFlash');
    assert(await page.locator('#namInstallCommit').isDisabled());
    await page.check('#namInstallOverwrite');assert(await page.locator('#namInstallCommit').isEnabled());
    // A refresh invalidates a prepared permanent installation.
    await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#namInstallPanel').isHidden());assert.equal(installs.length,0);
    assert(await page.locator('#namInstallPrepare').isDisabled());
    await page.click('#namSlotsRefresh');await page.locator('#namSlot:not([disabled])').waitFor();
    await page.selectOption('#namSlot','1');
    await page.click('#namInstallPrepare');await page.locator('#namInstallPanel:not([hidden])').waitFor();
    assert.match(await page.textContent('#namInstallWarning'),/THIS SLOT IS OCCUPIED/);
    assert.match(await page.textContent('#namSlotConsent'),/overwriting NAM slot 001/);
    await page.selectOption('#namSlot','256');assert(await page.locator('#namInstallPanel').isHidden());
    await page.click('#namInstallPrepare');await page.locator('#namInstallPanel:not([hidden])').waitFor();
    assert.equal(previews.at(-1).slot,256);assert.equal(await page.textContent('#namInstallCommit'),'INSTALL IN NAM 256');
    for(const id of ['namInstallMute','namInstallFlash','namInstallOverwrite'])await page.check('#'+id);
    await page.click('#namInstallCommit');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(installs.length,1);assert.deepEqual(installs[0],{prepared_id:'install-ticket',external_audio_muted:true,confirm_permanent_write:true,confirm_overwrite:true});
    assert(await page.locator('#namInstallPrepare').isDisabled());
    slotsFull=true;await page.click('#namSlotsRefresh');await page.locator('#namSlot:not([disabled])').waitFor();
    assert.equal(await page.inputValue('#namSlot'),'');assert(await page.locator('#namInstallPrepare').isDisabled());
    assert.equal(await page.locator('#namBuildSlot option').count(),257);
    assert.match(await page.textContent('#namSlotsHint'),/No empty slots/);
    await page.selectOption('#namSlot','250');assert(await page.locator('#namInstallPrepare').isEnabled());
    slotsFail=true;await page.click('#namSlotsRefresh');await page.locator('#namSlotsRefresh:not([disabled])').waitFor();
    assert(await page.locator('#namSlot').isDisabled());assert(await page.locator('#namInstallPrepare').isDisabled());
    assert.equal(installs.length,1);assert.match(await page.textContent('#status'),/NAM inventory incomplete/);
    assert.equal(await page.locator('#namBuildSlot option').count(),1);
    slotsFail=false;slotsFull=true;
    await page.click('#namSlotsRefresh');await page.locator('#namSlot:not([disabled])').waitFor();
    slotsFull=false;
    await request();await page.selectOption('#namBuildSlot','250');
    await page.fill('#prompt','Make a NAM rhythm foundation');await review();
    assert.equal(plans.at(-1).nam_slot,250);assert.match(await page.textContent('#toneChoice'),/NAM 250:/);
    assert.equal(plans.at(-1).scenes,1);assert.equal(await page.locator('#sceneRows tr').count(),1);
    assert.match(await page.textContent('#sceneRows'),/NAM input/);assert.equal(stores.length,0);
    await confirmSend();await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(sends.length,3);assert.equal(await page.inputValue('#scenes'),'1');
    assert(!(await page.locator('#scenes option').nth(1).evaluate(option=>option.disabled)));
    assert(await page.locator('#scenes option').nth(2).evaluate(option=>option.disabled));
    await page.click('#storePanel summary');await page.click('#storePrepare');await page.locator('#storePrepare:not([disabled])').waitFor();
    assert.match(await page.textContent('#storeSummary'),/Old stored preset/);assert(await page.locator('#storeCommit').isDisabled());
    await page.check('#storeMute');assert(await page.locator('#storeCommit').isDisabled());
    await page.check('#storeFlash');await page.click('#storeCommit');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(stores.length,1);assert.deepEqual(stores[0],{token:'store-ticket',external_audio_muted:true,confirm_permanent_write:true});
    assert(await page.locator('#storeCommit').isDisabled());
    await request();await page.selectOption('#scenes','2');await review();
    assert.equal(plans.at(-1).scenes,2);assert.equal(await page.locator('#sceneRows tr').count(),2);
    await request();
    const beforeAudio=audioFetches,beforeSends=sends.length;
    await page.fill('#prompt','Maak de uitgelegde rig van https://youtu.be/Plwb_gfmSc4');
    await page.selectOption('#sourceKind','rig');await page.selectOption('#rigMode','closest');
    await review();
    assert.equal(plans.at(-1).source_kind,'rig');assert.equal(plans.at(-1).audio_reference,null);
    assert.equal(audioFetches,beforeAudio);assert.equal(sends.length,beforeSends);
    await page.click('#rail [data-step="1"]');
    assert(await page.locator('#rigReport').isVisible());
    await page.click('#rigReport summary');
    assert.match(await page.textContent('#rigComponents'),/Wah: not_reproduced/);
    assert.match(await page.textContent('#sourceTitle'),/codex/);
    assert.equal(await page.locator('#rigReport img').count(),0);
    await request();await page.selectOption('#rigMode','faithful');
    assert(await page.locator('#rigReport').isHidden());
    assert(!(await page.isChecked('#confirmed')));
    await review();assert.equal(plans.at(-1).rig_mode,'faithful');
    await request();sourceBackendReady=false;await page.click('#refresh');
    await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#sourceKind').isHidden());
    await page.fill('#prompt','Gewoon verzoek met een oudere backend');await review();
    assert(!Object.hasOwn(plans.at(-1),'source_kind'));
    assert(!Object.hasOwn(plans.at(-1),'rig_mode'));
    // A new backend exposes both strategies, with no automatic NAM selection.
    await request();routeOptionsReady=true;sourceBackendReady=true;
    await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    await page.setInputFiles('#audioFile',[]);await page.selectOption('#sourceKind','tone');
    await page.fill('#prompt','Maak de klank van https://example.com/reference.wav');
    assert.equal(await page.locator('#routeOptionsPanel').getAttribute('open'),null);
    assert(await page.locator('#engage').isEnabled());
    assert.match(await page.textContent('#requestNext'),/GENERATE PLAN/);
    const beforeExplore={audio:audioFetches,sends:sends.length,installs:installs.length,plans:plans.length};
    await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(audioFetches,beforeExplore.audio+1);
    assert.equal(explorations.at(-1).audio_reference.url,'https://example.com/reference.wav');
    assert.equal(explorations.at(-1).expected_preset,325);
    assert.equal(await page.inputValue('#buildRoute'),'');
    assert.match(await page.textContent('#routeOptions'),/AMP \/ CAB/);
    assert.match(await page.textContent('#routeOptions'),/NAM \+ suitable effects/);
    assert.equal(await page.locator('#routeOptions details').getAttribute('open'),null);
    assert.match(await page.locator('#routeOptions details summary').textContent(),/Why this advice/);
    assert.equal(await page.locator('#routeOptions img').count(),0);
    assert.equal(sends.length,beforeExplore.sends);assert.equal(installs.length,beforeExplore.installs);
    assert.equal(plans.length,beforeExplore.plans);
    assert.equal(await page.textContent('#engage'),'CHOOSE ROUTE');
    const beforeChoice=explorations.length;
    await page.click('#engage');
    assert.equal(explorations.length,beforeChoice);assert.equal(plans.length,beforeExplore.plans);
    await page.waitForFunction(()=>document.activeElement===document.getElementById('buildRoute'));
    await page.selectOption('#buildRoute','amp');assert(await page.locator('#engage').isDisabled());
    await page.selectOption('#buildRoute','nam');assert(await page.locator('#engage').isEnabled());
    if((await page.locator('#namPanel').getAttribute('open'))===null)await page.click('#namPanel summary');
    await page.fill('#namQuery','Marshall JTM45');
    await review();assert.equal(plans.at(-1).mode,'nam');
    assert.equal(audioFetches,beforeExplore.audio+1);
    await request();await page.fill('#prompt','Werk deze twee scenes verder uit van https://example.com/reference.wav');
    assert.equal(await page.inputValue('#buildRoute'),'');assert(await page.locator('#engage').isEnabled());
    await page.click('#exploreRoutes');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(audioFetches,beforeExplore.audio+1);
    await page.selectOption('#buildRoute','nam');await review();
    assert.equal(audioFetches,beforeExplore.audio+1);
    await request();await page.fill('#prompt','Andere referentie https://example.com/changed.wav');
    await page.click('#exploreRoutes');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(audioFetches,beforeExplore.audio+2);
    assert.equal(explorations.at(-1).audio_reference.url,'https://example.com/changed.wav');
    assert.equal(sends.length,beforeExplore.sends);assert.equal(installs.length,beforeExplore.installs);
    // A measured serial template is explicit, one scene, and not a NAM selection.
    await request();serialReady=true;await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(await page.locator('#liveRoute .chain-channel').count(),14);
    assert.equal(await page.locator('#liveRoute .bypassed .chain-channel').count(),8);
    assert.equal(await page.locator('#liveRoute .bypassed').first().evaluate(x=>getComputedStyle(x).color),'rgb(255, 255, 255)');
    for(const width of [1180,1280,1440]){
      await page.setViewportSize({width,height:1000});
      assert(await page.locator('#liveRoute').evaluate(e=>{
        e.scrollLeft=0;const start=e.firstElementChild.getBoundingClientRect().left>=e.getBoundingClientRect().left;
        e.scrollLeft=e.scrollWidth;const end=e.lastElementChild.getBoundingClientRect().right<=e.getBoundingClientRect().right;
        e.scrollLeft=0;return start&&end;
      }),'Both ends of the long chain must remain reachable');
    }
    await page.fill('#prompt','Een scene crunch met delay en chorus, modellen behouden');
    await page.click('#exploreRoutes');await page.locator('#refresh:not([disabled])').waitFor();
    await page.selectOption('#buildRoute','serial');
    assert.equal(await page.inputValue('#scenes'),'1');
    assert(await page.locator('#namBuildSlot').isHidden());
    assert(await page.locator('#scenes option').nth(1).evaluate(option=>option.disabled));
    await review();assert.equal(plans.at(-1).mode,'serial');
    assert(!Object.hasOwn(plans.at(-1),'nam_slot'));
    assert.match(await page.textContent('#toneChoice'),/no model or IR selection/);
    assert.match(await page.textContent('#sceneRows'),/320 ms.*feedback 20%/);
    assert.equal(await page.locator('#sceneRows tr').count(),1);
    await request();
    // Preset names are read-only; explicit selection needs mute and discard consent.
    navigationReady=true;await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(await page.textContent('#connectDevice'),'CONNECTED');assert(await page.locator('#connectDevice').isDisabled());
    assert.match(await page.textContent('#target'),/^Preset 325:/);
    assert.match(await page.locator('#target').getAttribute('title'),/Axe-Fx III/);
    assert.equal(await page.locator('#sceneRack button').count(),8);assert.match(await page.textContent('#sceneRack button:first-child'),/Rhythm/);
    assert(!(await page.textContent('#sceneRack button:first-child')).includes('1,Rhythm'));
    await page.click('#sceneRack button[data-scene="2"]');await page.locator('#navigationDialog[open]').waitFor();
    assert.equal(navigationSelections.length,0);assert(await page.locator('#navigationSelect').isDisabled());
    await page.click('#navigationCancel');assert.equal(navigationSelections.length,0);
    await page.click('#sceneRack button[data-scene="2"]');await page.locator('#navigationDialog[open]').waitFor();
    await page.check('#navigationMute');await page.click('#navigationSelect');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(navigationSelections.length,1);assert.equal(currentScene,2);
    assert.equal(await page.locator('#sceneRack button[data-scene="2"]').getAttribute('aria-pressed'),'true');
    const retained=await page.inputValue('#prompt');await page.click('#target');await page.locator('#presetChoices button').first().waitFor();
    assert.equal(navigationSelections.length,1);assert.equal(await page.locator('#presetChoices img').count(),0);
    await page.fill('#presetSearch','0326');assert.equal(await page.locator('#presetChoices button').count(),1);
    await page.click('#presetChoices button');await page.locator('#navigationDialog[open]').waitFor();
    assert.match(await page.textContent('#navigationWarning'),/unsaved/);
    await page.check('#navigationMute');assert(await page.locator('#navigationSelect').isDisabled());
    await page.check('#navigationDiscard');await page.click('#navigationSelect');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(currentPreset,326);assert.equal(navigationSelections.length,2);
    assert.equal(await page.inputValue('#prompt'),retained);
    assert.deepEqual(navigationSelections.at(-1),{token:'navigation-test-ticket',external_audio_muted:true,confirm_discard_edits:true});
    assert.equal(sends.length,beforeExplore.sends);assert.equal(installs.length,beforeExplore.installs);
    // Eight-scene capability is negotiated, not inferred from eight scene buttons.
    await request();fw33=false;serialReady=false;routeOptionsReady=false;multiSceneReady=true;
    await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    await page.setInputFiles('#audioFile',[]);await page.selectOption('#sourceKind','tone');
    await page.fill('#prompt','Metallica albums met acht scenes, vier albumparen');
    await page.selectOption('#scenes','8');
    await review();assert.equal(plans.at(-1).scenes,8);
    assert.equal(await page.locator('#sceneRows tr').count(),8);
    const names=await page.locator('#sceneRows tr td:first-child').allTextContents();
    assert.match(names[4],/5\. Album 3 Lead \/ C/);assert.match(names[7],/8\. Album 4 Solo \/ D/);
    assert(!names.join(' ').includes('undefined'));
    assert.match(await page.textContent('#sceneRows'),/Output -9 dB/);
    assert.match(await page.textContent('#sceneRows'),/Output -6 dB/);
    assert.match(await page.textContent('#sceneRows'),/Album cab 4/);
    assert.match(await page.textContent('#sceneRows'),/CABINET D/);
    await request();fw33=true;await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#scenes option').nth(7).evaluate(o=>o.disabled));
    // FW33 album capability is separate from NAM and from legacy eight-scene support.
    albumReady=true;serialReady=true;routeOptionsReady=true;currentScene=1;
    await page.fill('#prompt','Metallica vier albums lead en solo met AMP CAB');
    await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    await page.click('#exploreRoutes');await page.locator('#exploreRoutes:not([disabled])').waitFor();
    await page.selectOption('#buildRoute','amp');
    assert.equal(await page.textContent('#workspaceIdentity'),'TC FX3 abc1234');
    assert.match(await page.locator('#workspaceIdentity').getAttribute('title'),/current-checkout.*PID 1234/);
    assert.match(await page.textContent('#cabCount'),/Usercabselectie/);
    assert.match(await page.textContent('#ampCount'),/336 models/);
    assert.equal(await page.locator('#ampModels li').count(),336);
    assert.equal(await page.locator('#ampModels li').first().textContent(),'59 Bassguy Bright');
    assert.equal(await page.locator('#ampModels li').last().textContent(),'Brit JVM Crunch Red');
    await page.locator('#cabPanel > summary').click();
    assert.match(await page.textContent('#cabInventoryCount'),/2049 non-empty/);
    assert.equal(await page.locator('#cabNames li').count(),100);
    const cabPlansBefore=plans.length,cabSendsBefore=sends.length;
    await page.fill('#cabSearch','USER 2');
    assert.equal(await page.locator('#cabNames li').count(),1);
    assert.match(await page.textContent('#cabNames'),/slot 1024/);
    assert.equal(await page.locator('#cabNames img').count(),0);
    await page.locator('#cabPanel details summary').click();
    assert.match(await page.textContent('#cabMixer'),/MUTED.*-6.1dB.*pan 70/);
    assert.equal(await page.locator('#cabMixer img').count(),0);
    assert.equal(plans.length,cabPlansBefore);assert.equal(sends.length,cabSendsBefore);
    await page.locator('#cabPanel > summary').click();
    await page.locator('#ampPanel summary').click();
    assert(await page.locator('#ampModels').isVisible());
    const draftBeforeRefresh=await page.inputValue('#prompt');
    await page.click('#ampRefresh');await page.locator('#ampRefresh:not([disabled])').waitFor();
    assert.match(await page.textContent('#ampRefreshStatus'),/Actueel: 336/);
    assert.equal(await page.inputValue('#prompt'),draftBeforeRefresh);
    assert.equal(ampRefreshes.at(-1).expected_firmware,'33.00-beta.20261006');
    ampRefreshMode='new';await page.click('#ampRefresh');await page.locator('#ampRefresh:not([disabled])').waitFor();
    assert.match(await page.textContent('#ampChanges'),/New, still blocked/);
    assert.equal(await page.locator('#ampChanges img').count(),0);
    assert.equal(await page.locator('#ampModels li').count(),336);
    ampRefreshMode='error';await page.click('#ampRefresh');await page.locator('#ampRefresh:not([disabled])').waitFor();
    assert.match(await page.textContent('#ampRefreshStatus'),/Firmware changed/);
    assert.equal(await page.inputValue('#prompt'),draftBeforeRefresh);
    ampRefreshMode='same';
    await page.locator('#ampPanel summary').click();
    assert.equal(await page.inputValue('#scenes'),'8');
    assert(!await page.locator('#namBuildSlot').isVisible());
    await review();assert.equal(plans.at(-1).scenes,8);assert.equal(plans.at(-1).mode,'amp');
    assert(!Object.hasOwn(plans.at(-1),'nam_slot'));
    assert.equal(await page.locator('#sceneRows tr').count(),8);
    await page.locator('#ampPanel summary').click();
    const plansBeforeRefresh=plans.length,sendsBeforeRefresh=sends.length;
    await page.click('#ampRefresh');await page.locator('#ampRefresh:not([disabled])').waitFor();
    assert.equal(await page.locator('#sceneRows tr').count(),8);
    assert.equal(plans.length,plansBeforeRefresh);assert.equal(sends.length,sendsBeforeRefresh);
    await page.locator('#ampPanel summary').click();
    assert.match(await page.textContent('#sceneRows'),/8\. Album 4 Solo \/ D/);
    assert.match(await page.textContent('#sceneRows'),/Factory 2 slot 800 \/ D/);
    assert.match(await page.textContent('#sceneRows'),/Output A -18dB/);
    assert.match(await page.locator('#sceneRows tr').first().textContent(),/IR1.*User cab.*IN MIX.*IR2.*MUTED/);
    assert.equal(await page.locator('#sceneRows img').count(),0);
    assert.match(await page.locator('#sceneRows tr').nth(1).textContent(),/2\. Album 1 Solo \/ B/);
    assert.match(await page.locator('#sceneRows tr').nth(1).textContent(),/Factory 2 slot 800 \/ D/);
    assert.match(await page.locator('#sceneRows tr').first().textContent(),/Drive: off.*T808 Mod \/ A.*level knob 1.5\/10/);
    assert.match(await page.locator('#sceneRows tr').nth(1).textContent(),/Drive: on.*T808 Mod \/ B.*gain 1.*mix 100%/);
    await page.click('#backPlan');
    assert.match(await page.textContent('#sceneIntent'),/TONE TARGET PER SCENE/);
    assert.equal(await page.locator('#sceneIntent img').count(),0);
    await page.click('#reviewbtn');await confirmSend();await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#refineSound').isVisible());
    await page.click('#refineSound');
    assert.equal(await page.inputValue('#prompt'),'');
    assert.equal(await page.locator('#adjustScenes input').count(),8);
    assert(await page.locator('#scenes').isDisabled());
    await page.fill('#prompt','Scene 3 mist punch, behoud alle andere scenes');
    await page.check('#adjustScenes input[value="3"]');
    await review();
    assert.deepEqual(plans.at(-1).adjust_scenes,[3]);
    assert.equal(plans.at(-1).refine_token,'verified-sound-design-token');
    assert.equal(plans.at(-1).mode,'amp');
    // Leave adjustment mode through the explicit new-design workflow.
    await request();
    page.once('dialog',dialog=>dialog.accept());await page.click('#newDesign');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#adjustScenes').isHidden());
    await page.locator('#historyPanel summary').click();
    assert.equal(await page.locator('#historyDesign option').count(),2);
    assert.equal(await page.locator('#historyDesign img').count(),0);
    await page.selectOption('#historyDesign','a'.repeat(32));
    assert(await page.locator('#historyResume').isDisabled());
    await page.check('#historyTarget');assert(await page.locator('#historyResume').isDisabled());
    await page.check('#historyMute');assert(await page.locator('#historyResume').isEnabled());
    await page.fill('#prompt','Scene 3 graag meer punch');
    const plansBeforeResume=plans.length,sendsBeforeResume=sends.length;
    await page.click('#historyResume');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(historyResumes.length,1);
    assert.equal(historyResumes[0].external_audio_muted,true);assert.equal(historyResumes[0].target_confirmed,true);
    assert.equal(plans.length,plansBeforeResume);assert.equal(sends.length,sendsBeforeResume);
    assert.equal(await page.inputValue('#prompt'),'Scene 3 graag meer punch');
    assert.equal(await page.locator('#adjustScenes input').count(),8);
    assert.match(await page.textContent('#historyStatus'),/geen parameters geschreven/);
    page.once('dialog',dialog=>dialog.accept());await page.click('#newDesign');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#adjustScenes').isHidden());
    await request();await page.fill('#prompt','Nieuw verzoek met NAM');
    await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    await page.selectOption('#buildRoute','nam');
    assert(await page.locator('#scenes option').nth(7).evaluate(o=>o.disabled));
    // Only the backend's released scene counts are selectable. Preserve an
    // explicit choice when controls refresh; never force every AMP request8.
    await request();albumCounts=[1,2,3,4,5,6,7,8];
    await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    await page.click('#exploreRoutes');await page.locator('#refresh:not([disabled])').waitFor();
    await page.selectOption('#buildRoute','amp');
    await page.selectOption('#scenes','3');
    const countPlans=plans.length,countSends=sends.length;
    await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(await page.inputValue('#scenes'),'3');
    assert(await page.locator('#scenes option').evaluateAll(options=>options.every(o=>!o.disabled)));
    assert.equal(plans.length,countPlans);assert.equal(sends.length,countSends);
    albumCounts=[8];await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(await page.inputValue('#scenes'),'8');
    assert(await page.locator('#scenes option').first().evaluate(o=>o.disabled));
    // New provenance is sent only when the backend explicitly advertises v2.
    audioV2Ready=true;await request();await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    await page.fill('#prompt','Klank van https://example.com/v2.wav');
    if((await page.locator('#audioPanel').getAttribute('open'))===null)await page.locator('#audioPanel summary').click();
    await page.fill('#audioStart','0');await page.fill('#audioLength','1');
    await page.click('#exploreRoutes');await page.locator('#refresh:not([disabled])').waitFor();
    const v2=explorations.at(-1).audio_reference;
    assert.equal(v2.analysis_method,'channel-power-v2');assert.equal(v2.analysis_rate_hz,16000);
    assert.equal(v2.analysis_channels,1);assert.equal(v2.analysis_frames,8);
    assert(Math.abs(v2.centroid_hz-440)<40);
    assert.match(await page.textContent('#audioStatus'),/Channel energy measured separately/);
    await page.locator('#audioComparePanel summary').click();
    const ownSize=16000,own=Buffer.alloc(44+ownSize*2);
    own.write('RIFF');own.writeUInt32LE(own.length-8,4);own.write('WAVEfmt ',8);own.writeUInt32LE(16,16);
    own.writeUInt16LE(1,20);own.writeUInt16LE(1,22);own.writeUInt32LE(16000,24);own.writeUInt32LE(32000,28);
    own.writeUInt16LE(2,32);own.writeUInt16LE(16,34);own.write('data',36);own.writeUInt32LE(ownSize*2,40);
    for(let i=0;i<ownSize;i++)own.writeInt16LE(Math.round(8000*Math.sin(2*Math.PI*440*i/16000)),44+2*i);
    await page.setInputFiles('#recordingFile',{name:'own-private.wav',mimeType:'audio/wav',buffer:own});
    await page.fill('#recordingLength','1');
    const comparisonPlans=plans.length,comparisonSends=sends.length;
    await page.click('#compareAudio');await page.locator('#compareAudio:not([disabled])').waitFor();
    assert.equal(audioComparisons.length,1);assert.equal(plans.length,comparisonPlans);assert.equal(sends.length,comparisonSends);
    assert.equal(audioComparisons[0].recording.analysis_method,'channel-power-v2');
    assert(!Object.hasOwn(audioComparisons[0].recording,'file_name'));
    assert.match(await page.textContent('#comparisonStatus'),/nothing played/);
    assert.match(await page.textContent('#comparisonResults'),/Recording minus reference/);
    assert.equal(await page.locator('#comparisonResults img').count(),0);
    await page.fill('#recordingStart','99');
    assert.equal(await page.textContent('#comparisonResults'),'');
    await page.click('#compareAudio');await page.locator('#compareAudio:not([disabled])').waitFor();
    assert.equal(audioComparisons.length,1);assert.match(await page.textContent('#comparisonStatus'),/outside the recording/);
    // Additional user-test preflight: no real hardware or AI is involved.
    await request();await page.setInputFiles('#audioFile',[]);await page.fill('#prompt','Metallica albums met acht duidelijk verschillende scenes. '.repeat(25));
    await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    await page.selectOption('#buildRoute','amp');await page.selectOption('#scenes','8');
    const longDraft=await page.inputValue('#prompt');
    await page.locator('#requestOptions summary').focus();await page.keyboard.press('Enter');
    assert.equal(await page.locator('#requestOptions').getAttribute('open'),null);
    await page.locator('#requestPanel > summary').focus();await page.keyboard.press('Enter');
    assert.equal(await page.locator('#requestPanel').getAttribute('open'),null);
    await page.keyboard.press('Enter');assert.equal(await page.inputValue('#prompt'),longDraft);
    await page.locator('#prompt').focus();await page.keyboard.press('Tab');
    assert(await page.locator('#engage').evaluate(e=>document.activeElement===e));
    for(const viewport of [{width:1180,height:720},{width:1280,height:720},{width:1440,height:900},{width:1920,height:1080}]){
      await page.setViewportSize(viewport);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      const noOverlap=await page.evaluate(()=>{
        const ids=['chat','routeOptionsPanel','requestPanel'];
        const boxes=ids.map(id=>document.getElementById(id).getBoundingClientRect());
        return boxes.every((r,i)=>!i||boxes[i-1].bottom<=r.top+1);
      });
      assert(noOverlap,'Conversation, route choice and request must not overlap at '+JSON.stringify(viewport));
      await page.locator('#engage').scrollIntoViewIfNeeded();
      assert(await page.locator('#engage').evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}));
      if(process.env.TC_SCREENSHOT_DIR&&viewport.width===1180)await page.screenshot({path:path.join(process.env.TC_SCREENSHOT_DIR,'ux-long-request-1180x720.png')});
    }
    await page.setViewportSize({width:1440,height:900});
    largePlan=true;await review();assert.equal(await page.locator('#sceneRows tr').count(),8);
    await page.locator('#actionCount').click();await page.locator('#actions li').last().scrollIntoViewIfNeeded();
    assert.equal(await page.locator('#actions li').count(),200);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.click('#toconfirm');await page.check('#confirmed');await page.check('#muted');
    const attemptsBefore={plans:plans.length,sends:sends.length,installs:installs.length,stores:stores.length};
    await request();failedTransport='plan';await page.click('#engage');
    await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#workflowError').isVisible());
    assert.match(await page.textContent('#workflowError'),/No response from TC/);
    assert.equal(await page.inputValue('#prompt'),longDraft);
    assert(!(await page.isChecked('#confirmed'))&&!(await page.isChecked('#muted')));
    assert(await page.locator('#apply').isDisabled());
    assert.deepEqual({plans:plans.length,sends:sends.length,installs:installs.length,stores:stores.length},attemptsBefore);
    failedTransport='';await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#workflowError').isHidden());
    await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();await page.selectOption('#buildRoute','amp');
    invalidPlanReply=true;await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert.match(await page.textContent('#workflowError'),/invalid response/);assert.equal(await page.inputValue('#prompt'),longDraft);
    invalidPlanReply=false;await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    disconnected=true;await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#engage').isDisabled());assert.match(await page.textContent('#requestNext'),/Connect the Fractal first/);
    assert.equal(await page.inputValue('#prompt'),longDraft);
    disconnected=false;routeProblem='Route niet verifieerbaar; niets verzonden.';
    await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#engage').isDisabled());assert.match(await page.textContent('#requestNext'),/Route niet verifieerbaar/);
    routeProblem='';await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    await page.selectOption('#deviceChoice','fm9');
    assert(await page.locator('#connectDevice').isEnabled());assert.match(await page.textContent('#connectDevice'),/FM9/);
    await page.selectOption('#deviceChoice','axefx3');
    assert(await page.locator('#connectDevice').isDisabled());
    await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();await page.selectOption('#buildRoute','amp');
    let releasePlan;holdPlan=new Promise(resolve=>{releasePlan=resolve;});
    await page.click('#engage');await page.locator('#pane-plan:not([hidden])').waitFor();
    assert(await page.locator('#newDesign').isDisabled());assert(await page.locator('#prompt').isDisabled());
    assert(await page.locator('#rail [data-step="0"]').isDisabled());assert.equal(await page.inputValue('#prompt'),longDraft);
    releasePlan();holdPlan=null;await page.locator('#reviewbtn:not([disabled])').waitFor();
    assert.equal(sends.length,attemptsBefore.sends);assert.equal(installs.length,attemptsBefore.installs);assert.equal(stores.length,attemptsBefore.stores);
    await page.click('#reviewbtn');
    const sendAttemptsBefore=requestAttempts.filter(r=>r.path.endsWith('/send')).length;
    failedTransport='send';await confirmSend();await page.locator('#refresh:not([disabled])').waitFor();
    assert.match(await page.textContent('#workflowError'),/Transmission not confirmed.*not automatically resend/);
    assert(await page.locator('#apply').isDisabled());assert.equal(await page.inputValue('#prompt'),longDraft);
    await page.setViewportSize({width:1180,height:720});
    await request();await page.locator('#prompt').scrollIntoViewIfNeeded();
    assert(await page.locator('#workflowError').evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}));
    assert(await page.locator('#shell').evaluate(e=>e.scrollTop===0));
    assert.equal(await page.locator('#pane-request').evaluate(e=>getComputedStyle(e).overflowY),'auto');
    const requestScroll=await page.locator('#pane-request').evaluate(e=>{e.scrollTop=e.scrollHeight;return e.scrollTop;});
    if(requestScroll>0){
      const box=await page.locator('#pane-request').boundingBox();
      await page.mouse.move(box.x+4,box.y+12);await page.mouse.wheel(0,-1200);
      await page.waitForFunction(limit=>document.getElementById('pane-request').scrollTop<limit,requestScroll);
    }
    if(process.env.TC_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.TC_SCREENSHOT_DIR,'ux-send-connection-error-1180x720.png')});
    assert.equal(requestAttempts.filter(r=>r.path.endsWith('/send')).length,sendAttemptsBefore+1);
    assert.equal(stores.length,attemptsBefore.stores);assert.equal(installs.length,attemptsBefore.installs);
    // Exact user regression: text count, ambiguity, explicit omission, no writes.
    failedTransport='';intakeReady=true;largePlan=false;fw33=true;albumReady=true;albumCounts=[1,2,3,4,5,6,7,8];currentScene=1;
    await page.setViewportSize({width:1440,height:900});
    await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    const vai='Steve vai for the love of god. graag 4 scenes waarbij het liedje volledig kan worden doorlopen. gebruik de juiste AMP / CAB combinatie en ook de wah zou een high pitch moeten geven als ik toe down doe. wah moet auto engaged worden op external 2.';
    await page.locator('#requestPanel').evaluate(e=>e.open=true);await page.fill('#prompt',vai);
    const beforeIntake={plans:plans.length,explorations:explorations.length,sends:sends.length,stores:stores.length,installs:installs.length};
    await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#requestQuestions').isVisible());assert.equal(await page.inputValue('#scenes'),'4');
    assert.equal(explorations.length,beforeIntake.explorations);assert.equal(plans.length,beforeIntake.plans);
    await page.selectOption('[data-intake="pitch_meaning"]','filter');
    await page.locator('#requestQuestions button').click();await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(explorations.length,beforeIntake.explorations+1);assert.equal(plans.length,beforeIntake.plans);
    assert.equal(explorations.at(-1).resolution.pitch_meaning,'filter');assert.equal(explorations.at(-1).scenes,4);
    await page.selectOption('#buildRoute','amp');await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('[data-intake="wah_controller"]').isVisible());assert.equal(plans.length,beforeIntake.plans);
    if(process.env.TC_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.TC_SCREENSHOT_DIR,'ux-request-clarification.png')});
    // No checkbox means no partial plan; repeated click cannot bypass consent.
    await page.locator('#requestQuestions button').click();await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(plans.length,beforeIntake.plans);assert.equal(await page.inputValue('#prompt'),vai);
    await page.check('[data-intake="wah_controller"]');await page.locator('#requestQuestions button').click();
    await page.locator('#reviewbtn:not([disabled])').waitFor();
    assert.equal(plans.at(-1).scenes,4);assert.deepEqual(plans.at(-1).resolution.accepted_omissions,['wah_controller']);
    assert.equal(await page.locator('#sceneRows tr').count(),4);assert.match(await page.textContent('#planWarnings'),/NIET uitgevoerd/);
    await request();await page.fill('#prompt',vai+' Extra sustain.');await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(await page.inputValue('[data-intake="pitch_meaning"]'),'');assert.deepEqual(intakes.at(-1).resolution,{});
    await page.selectOption('[data-intake="pitch_meaning"]','pitch');await page.locator('#requestQuestions button').click();await page.locator('#refresh:not([disabled])').waitFor();
    await page.selectOption('#buildRoute','amp');await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('[data-intake="pitch"]').isVisible());assert(await page.locator('[data-intake="wah_controller"]').isVisible());
    await page.check('[data-intake="pitch"]');await page.check('[data-intake="wah_controller"]');
    planNeedsClarification=true;await page.locator('#requestQuestions button').click();await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('#requestQuestions').isVisible());assert.match(await page.textContent('#requestQuestions'),/geen AI-verbindingsfout/);
    assert(await page.locator('#apply').isDisabled());assert(await page.locator('#workflowError').isHidden());
    await page.selectOption('#buildRoute','nam');await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(await page.inputValue('#scenes'),'4');assert(await page.locator('[data-intake="scene_count"]').isVisible());
    assert(!await page.isChecked('[data-intake="wah_controller"]'));
    await page.selectOption('[data-intake="scene_count"]','2');
    await page.check('[data-intake="wah_controller"]');await page.check('[data-intake="pitch"]');
    await page.locator('#requestQuestions button').click();await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(intakes.at(-1).scenes,2);assert.equal(intakes.at(-1).resolution.scene_count_override,true);
    await page.selectOption('#buildRoute','amp');await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert(!await page.isChecked('[data-intake="wah_controller"]'));
    assert.equal(sends.length,beforeIntake.sends);assert.equal(stores.length,beforeIntake.stores);assert.equal(installs.length,beforeIntake.installs);
    assert.equal(errors.length,0);
    planNeedsClarification=false;
    // General AI conversation: questions before route advice and during design.
    page.once('dialog',dialog=>dialog.accept());await page.click('#newDesign');await page.locator('#refresh:not([disabled])').waitFor();
    aiDialogueReady=true;await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    const generalPrompt='Meer volume in de breedte voor een gitaarpreset met 4 scenes.';
    await page.fill('#prompt',generalPrompt);const beforeDialogue={sends:sends.length,stores:stores.length,installs:installs.length};
    await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert(await page.locator('[data-ai-answer="width"]').isVisible());assert.equal(await page.inputValue('[data-ai-answer="width"]'),'');
    assert.equal(await page.inputValue('#prompt'),generalPrompt);assert(await page.locator('#apply').isDisabled());
    const optionsBeforeAnswer=explorations.length;
    await page.locator('#requestQuestions > button').click();await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(explorations.length,optionsBeforeAnswer);
    await page.fill('[data-ai-answer="width"]','Breder stereo');await page.locator('[data-ai-answer="width"]').press('Enter');
    assert.equal(await page.inputValue('[data-ai-answer="width"]'),'Breder stereo\n');assert.equal(explorations.length,optionsBeforeAnswer);
    const freeAnswer='<img src=x onerror=alert(1)> Breder stereo, niet harder';
    await page.fill('[data-ai-answer="width"]',freeAnswer);await page.locator('#requestQuestions > button').click();await page.locator('#refresh:not([disabled])').waitFor();
    assert.deepEqual(dialogueTurns.at(-1).answers,[{id:'width',text:freeAnswer}]);assert.equal(dialogueTurns.at(-1).dialogue_token,'ai-question-options-ticket');
    assert(await page.locator('#dialogueHistory').isVisible());assert.match(await page.textContent('#dialogueHistory'),/Breder stereo/);
    assert.equal(await page.locator('#dialogueHistory img').count(),0);
    await page.selectOption('#buildRoute','amp');await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(dialogueTurns.at(-1).dialogue_token,'ai-options-ready-ticket');assert.deepEqual(dialogueTurns.at(-1).answers,[]);
    assert(await page.locator('[data-ai-answer="role"]').isVisible());assert.equal(await page.inputValue('[data-ai-answer="role"]'),'');
    if(process.env.TC_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.TC_SCREENSHOT_DIR,'ux-ai-question-and-history.png')});
    await page.locator('#requestQuestions button').filter({hasText:/^Solo$/}).click();
    assert.equal(await page.inputValue('[data-ai-answer="role"]'),'Solo');
    await page.locator('#requestQuestions > button').click();await page.locator('#refresh:not([disabled])').waitFor();
    assert.deepEqual(dialogueTurns.at(-1).answers,[{id:'role',text:'Solo'}]);assert.equal(dialogueTurns.at(-1).dialogue_token,'ai-question-plan-ticket');
    assert(await page.locator('#pane-plan').isVisible());assert.equal(await page.locator('#sceneRows tr').count(),4);
    await request();assert.match(await page.textContent('#dialogueHistory'),/Solo/);assert.equal(await page.inputValue('#prompt'),generalPrompt);
    assert.equal(sends.length,beforeDialogue.sends);assert.equal(stores.length,beforeDialogue.stores);assert.equal(installs.length,beforeDialogue.installs);
    if(process.env.TC_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.TC_SCREENSHOT_DIR,'ux-ai-design-conversation.png')});
    await page.fill('#prompt',generalPrompt+' Nieuwe versie.');
    await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(dialogueTurns.at(-1).dialogue_token,null);assert.deepEqual(dialogueTurns.at(-1).answers,[]);
    assert.equal(await page.inputValue('[data-ai-answer="width"]'),'');
    await page.fill('[data-ai-answer="width"]','Bewaar dit antwoord');staleDialogue=true;
    const beforeStale=dialogueTurns.length;
    await page.locator('#requestQuestions > button').click();await page.locator('#refresh:not([disabled])').waitFor();
    assert.match(await page.textContent('#workflowError'),/gesprek is verlopen/);assert.match(await page.textContent('#dialogueHistory'),/Bewaar dit antwoord/);
    assert.equal(dialogueTurns.length,beforeStale+1);assert.equal(await page.inputValue('#prompt'),generalPrompt+' Nieuwe versie.');
    staleDialogue=false;await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    assert.equal(dialogueTurns.at(-1).dialogue_token,null);assert.deepEqual(dialogueTurns.at(-1).answers,[]);
    aiDialogueReady=false;wahReady=true;contractReady=true;
    page.once('dialog',dialog=>dialog.accept());await page.click('#newDesign');await page.locator('#refresh:not([disabled])').waitFor();
    await page.click('#refresh');await page.locator('#refresh:not([disabled])').waitFor();
    await page.fill('#prompt','4 scenes met wah op External 2');
    await page.click('#engage');await page.locator('#refresh:not([disabled])').waitFor();
    await page.selectOption('#buildRoute','amp');
    await page.locator('#requestOptions').evaluate(e=>e.open=true);
    assert.match(await page.textContent('#controllerHint'),/Wah Cry Babe with External 1\/2/);
    assert.match(await page.textContent('#controllerHint'),/Preserve without an existing wah binding means Auto Engage Off/);
    assert(!/no new controllers/i.test(await page.textContent('#controllerHint')));
    assert(await page.locator('#wah').isEnabled());await page.selectOption('#wah','External 2');
    await page.selectOption('#wahMode','Fast Pos');
    const wahSends=sends.length;
    await page.click('#engage');await page.locator('#reviewbtn:not([disabled])').waitFor();
    assert.equal(plans.at(-1).wah_source,'External 2');assert.match(await page.textContent('#controllerChoice'),/External 2.*Fast Pos/);
    assert.equal(plans.at(-1).scene_contract,true);
    assert.match(await page.textContent('#sceneComparison'),/Same programmed tone as scene 1/);
    assert.match(await page.textContent('#sceneComparisonReview'),/gain: 5 -> 7/);
    assert.match(await page.textContent('#sceneComparison'),/Small parameter change/);
    assert.equal(await page.locator('#sceneComparison img').count(),0);
    assert.match(await page.textContent('#sceneRows'),/Cry Babe.*350-3000Hz/);assert.equal(sends.length,wahSends);
    await request();await page.fill('#prompt',longDraft);
    await page.selectOption('#deviceChoice','fm9');
    page.once('dialog',dialog=>dialog.dismiss());await page.click('#connectDevice');
    await page.locator('#connectDevice:not([disabled])').waitFor();
    assert.equal(await page.inputValue('#prompt'),longDraft);assert.equal(new URL(page.url()).pathname,'/axefx3');
    assert.equal(requestAttempts.filter(r=>r.path==='/api/controllers/disconnect').length,0);
    page.once('dialog',dialog=>dialog.accept());await page.click('#connectDevice');await page.waitForURL('http://tc.test/');
    assert.equal(await page.title(),'FM9 test workspace');
    assert.deepEqual(requestAttempts.filter(r=>r.path==='/api/controllers/disconnect'),[{path:'/api/controllers/disconnect',method:'POST'}]);
    assert.deepEqual(errors,[]);
    console.log('AFX3 shared FM9 layout: workflow, fit, consent, reset, MK, audio, XSS; FW33 NAM foundation/two scenes, permanent install and separate Store consent passed');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
