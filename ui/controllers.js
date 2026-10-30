'use strict';
const tcText=(key,values={})=>window.TCLanguage?.t(key,values)??key.replace(/\{\{(\w+)\}\}/g,(_,name)=>String(values[name]??''));
const el = id => document.getElementById(id);
let current = null, review = null, busy = false;

async function api(path, body) {
  const response = await fetch('/api/controllers/' + path, body === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : (data.error || tcText("Request refused. Read state again.")));
  return data;
}
function message(text) { el('status').textContent = text; }
function invalidate() {
  review = null; el('review').hidden = true;
  el('targetConfirmed').checked = el('muted').checked = false;
  controls();
}
function controls() {
  const linked = !!current?.connected;
  const selected = linked || !!current?.controller_selected;
  el('connect').disabled = busy || linked;
  el('disconnect').disabled = busy || !selected;
  el('refresh').disabled = busy || !linked;
  el('back').hidden = selected;
  el('send').disabled = busy || !review || !el('targetConfirmed').checked || !el('muted').checked;
  el('cancel').disabled = busy;
  document.querySelectorAll('#rows button,#rows select').forEach(node => {
    node.disabled = busy || !!current?.gig_locked || node.dataset.blocked === 'true';
  });
}
async function run(action) {
  if (busy) return;
  busy = true; controls(); message(tcText("Working..."));
  try { await action(); }
  catch (error) { invalidate(); message(error.message); }
  finally { busy = false; controls(); }
}
function option(select, value, label) {
  const node = document.createElement('option'); node.value = value; node.textContent = label; select.append(node);
}
function labeledSelect(label, id) {
  const wrap = document.createElement('label'); wrap.textContent = label;
  const select = document.createElement('select'); select.id = id; wrap.append(select);
  return [wrap, select];
}
async function load() {
  invalidate();
  current = await api('state');
  el('targets').hidden = !current.connected;
  el('connection').textContent = current.connected
    ? `Axe-Fx III | FW ${current.firmware} | Preset ${current.preset}: ${current.preset_name} | Scene ${current.scene}`
    : tcText("Not connected yet. Close Axe-Edit and other TC sessions before connecting.");
  el('rows').replaceChildren();
  for (const target of current.targets || []) {
    const row = document.createElement('div'); row.className = 'row';
    const title = document.createElement('div'); const heading = document.createElement('h3'); heading.textContent = target.label;
    const before = document.createElement('p'); before.textContent = tcText("Now: {{v0}} | Auto Engage: {{v1}}", {v0:(target.source_name), v1:(target.auto_engage || tcText("not set"))});
    title.append(heading, before);
    const [sourceLabel, source] = labeledSelect('Controller', 'source-' + target.effect_id);
    option(source, '', target.source ? tcText("Keep current binding") : tcText("Do not bind"));
    for (const item of current.sources) option(source, item.value, item.label);
    const [modeLabel, mode] = labeledSelect('Auto Engage', 'mode-' + target.effect_id);
    option(mode, '', tcText("Preserve (new: Off)"));
    for (const item of target.modes) option(mode, item, item);
    if ([102,110].includes(target.effect_id)) { mode.value = 'Off'; mode.dataset.blocked = 'true'; }
    source.dataset.blocked = String(!target.writable);
    if (!target.writable) mode.dataset.blocked = 'true';
    const button = document.createElement('button'); button.textContent = tcText("Review");
    button.dataset.blocked = 'true';
    const changed = () => {
      invalidate();
      button.dataset.blocked = String(!target.writable || (!source.value && !mode.value));
      // Fixed Off is not itself a source-selection request.
      if ([102,110].includes(target.effect_id) && !source.value) button.dataset.blocked = 'true';
      controls();
    };
    source.onchange = mode.onchange = changed;
    button.onclick = () => run(async () => {
      invalidate(); el('result').hidden = true;
      const chosen = source.value ? Number(source.value) : target.source;
      if (![12,13].includes(chosen)) throw new Error(tcText("Choose External 1 or External 2 first."));
      review = await api('review', {effect_id:target.effect_id, source:chosen, auto_engage:mode.value || null});
      el('reviewDetails').replaceChildren();
      for (const [key, value] of [
        ['Preset', `${review.preset}: ${review.preset_name}`], [tcText("Target"), review.target],
        ['Controller', `${review.before_source} → ${review.after_source}`],
        ['Auto Engage', `${review.before_auto || tcText("not set")} → ${review.after_auto}`],
        [tcText("Binding"), review.new_binding ? tcText("New, with device curve") : tcText("Existing curve preserved")]
      ]) {
        const dt = document.createElement('dt'), dd = document.createElement('dd');
        dt.textContent = key; dd.textContent = value; el('reviewDetails').append(dt,dd);
      }
      el('reviewScope').textContent = review.operation === 'pitch_setup'
        ? review.setup
        : tcText("This changes only the controller binding in the edit buffer, not global MIDI-CC assignment. It can affect multiple scenes or channels using this modifier.");
      el('reviewExpiry').textContent = tcText("This review expires after {{seconds}} seconds or when device state changes.", {seconds:review.expires_in || 300});
      el('send').textContent = review.operation === 'pitch_setup' ? tcText("Send Pitch setup") : tcText("Send binding");
      el('review').hidden = false; el('review').focus(); message(tcText("Proposal ready. Nothing sent yet."));
    });
    row.append(title,sourceLabel,modeLabel,button);
    if (target.notice) { const p=document.createElement('p'); p.className='reason'; p.textContent=target.notice; row.append(p); }
    if (target.reason) { const p=document.createElement('p'); p.className='reason'; p.textContent=target.reason; row.append(p); }
    el('rows').append(row);
  }
  el('empty').hidden = !!current.targets?.length;
  message(current.gig_locked ? tcText("GIG LOCK is on; changes are blocked.") : tcText("State read. Reading changed nothing."));
}
el('connect').onclick = () => run(async () => {
  try { await api('connect', {}); }
  catch(error) { await load(); throw error; }
  await load();
});
el('refresh').onclick = () => run(load);
el('disconnect').onclick = () => run(async () => { await api('disconnect', {}); await load(); });
el('cancel').onclick = () => run(async () => { invalidate(); await api('discard', {}); message(tcText("Proposal canceled. Nothing sent.")); });
el('targetConfirmed').onchange = el('muted').onchange = controls;
el('send').onclick = () => run(async () => {
  const token = review?.token;
  const confirmed = el('targetConfirmed').checked, muted = el('muted').checked;
  if (!token || !confirmed || !muted) throw new Error(tcText("Review the proposal and confirm both checkboxes first."));
  invalidate();
  let result;
  try { result = await api('send', {token, target_confirmed:confirmed, external_audio_muted:muted}); }
  catch(error) {
    throw new Error(tcText("Transmission not confirmed. Keep audio muted and read state again before continuing. No automatic retry. ") + error.message);
  }
  el('resultTitle').textContent = result.ok ? (result.operation === 'pitch_setup'
    ? tcText("Pitch setup read back and confirmed") : tcText("Binding read back and confirmed")) : tcText("Transmission stopped");
  el('resultText').textContent = (result.ok
    ? tcText("The modifier was checked on the Fractal. Test the physical pedal; readback does not prove an audible result.")
    : result.results.map(r=>r.detail).join('\n') + tcText(" Partial changes may remain; keep audio muted."))
    + tcText(" Nothing permanently stored. No automatic Undo.");
  el('result').hidden = false; el('result').focus();
  await load();
  message(result.ok ? tcText("Transmission complete. Check physical controls and loudness separately.") : tcText("Stopped. Do not automatically resend."));
});
run(load);
document.getElementById('bootfail')?.remove();
