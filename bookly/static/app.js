'use strict';

const $ = id => document.getElementById(id);
let me, current, busy = false, labTab = 'trace';
let pendingSend = null;
let example = null;
let promptProfiles = null;
const money = cents => new Intl.NumberFormat('en-US', {style:'currency',currency:'USD'}).format(cents/100);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time = value => new Date(value).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
const date = value => value ? new Date(value.slice(0,10)+'T12:00:00').toLocaleDateString([], {month:'short',day:'numeric'}) : '';

async function api(path, body) {
  const response = await fetch(path, {method:body === undefined ? 'GET' : 'POST', headers:body === undefined ? {} : {'Content-Type':'application/json'}, body:body === undefined ? undefined : JSON.stringify(body)});
  if (!response.ok) {
    let error;
    try { error = await response.json(); } catch { error = {}; }
    const detail = typeof error.detail === 'string' ? error.detail : 'Something interrupted the request. Please try again.';
    throw Object.assign(new Error(detail), {status:response.status});
  }
  return response.json();
}

function cover(book) {
  // Colors are fixture fields, never model-generated HTML/CSS.
  const color = /^#[0-9a-f]{6}$/i.test(book.color) ? book.color : '#617f82';
  return `<div class="book-cover" style="background:${color}"><span class="cover-title">${escape(book.title)}</span><span class="cover-author">${escape(book.author)}</span></div>`;
}

function setBusy(value) {
  busy = value;
  $('typing').hidden = !value;
  document.querySelectorAll('button:not(#open-lab):not(#close-lab):not(#trace-tab):not(#state-tab):not(#prompts-tab), #customer-select').forEach(b => b.disabled = value);
  $('message-input').disabled = value;
}

function showError(error) {
  $('error').textContent = error.message;
  $('error').hidden = false;
}

function renderProfile() {
  $('customer-name').textContent = me.customer.name;
  $('avatar').textContent = me.customer.name.split(' ').map(x => x[0]).join('');
  $('customer-select').value = me.customer.id;
  const scripted=me.mode === 'scripted';
  $('mode-label').textContent = scripted ? 'Scripted · enable live' : 'Live · '+me.model;
  $('open-lab').classList.toggle('is-scripted',scripted);
  $('open-lab').setAttribute('title',scripted ? 'Scripted mode: click for instructions to enable live LLM replies.' : 'Live LLM: inspect model and tool activity.');
  $('live-setup').hidden = !scripted;
  $('lab-mode').textContent = me.mode === 'scripted' ? 'Scripted fixture model: Pydantic AI tools and real local database writes; language understanding is a limited, deterministic script. No LLM or dataWarehouse call is made.' : `Live LLM · ${me.provider} / ${me.model}. Orders, catalog, returns, and warehouse data remain fictional. No real refund, shipping label, dataWarehouse query, or human contact occurs.`;
  $('preferences').textContent = Object.keys(me.customer.preferences).length ? Object.entries(me.customer.preferences).map(([k,v]) => `${k[0].toUpperCase()+k.slice(1)}: ${v}`).join(' · ') : 'Tell us what you enjoy. We’ll only remember it when you ask us to.';
  $('orders').innerHTML = me.orders.slice(0,2).map(order => {
    const book = order.items[0];
    return `<article class="order-card"><div class="order-top">${cover(book)}<div><h3 class="order-title">${escape(book.title)}</h3><p class="order-author">${escape(book.author)}</p><span class="order-status ${order.status === 'shipped' ? 'shipped' : ''}">${escape(order.status === 'shipped' ? 'On its way' : 'Delivered')}</span></div></div><div class="order-bottom"><span>${order.status === 'shipped' ? 'Est. '+date(order.estimated_arrival) : 'Delivered '+date(order.delivered_at)}</span><button class="order-action" data-prompt="${escape('Help me with '+book.title)}">Get help →</button></div></article>`;
  }).join('');
  renderHistory();
}

function renderCase() {
  $('channel-description').textContent = 'Web chat · conversation saved';
  $('channel-note').textContent = 'Your conversation stays here, even if you step away.';
  $('message-input').placeholder = 'Tell us what’s on your mind…';
  const empty = `<div class="conversation-empty"><span aria-hidden="true">✧</span><h2>What can we help you with?</h2><p>Start in your own words, or choose a starting point and make it yours.</p><div class="welcome-actions"><button class="chip" data-topic="orders">Order question</button><button class="chip" data-topic="returns">Return a book</button><button class="chip" data-topic="discovery">Find my next read</button><button class="chip" data-topic="support">General questions</button></div></div>`;
  let html = current.messages.length ? current.messages.map(messageHtml).join('') : empty;
  for (const proposal of current.proposals) {
    html += `<article class="action-card"><div class="card-eyebrow">YOUR CONFIRMATION · NOTHING SUBMITTED YET</div><h3>Return ${escape(proposal.title)}</h3><p><strong>${money(proposal.refund_cents)}</strong> to your original payment method.</p><p>${escape(proposal.terms)}</p><p>This creates a mock return request. It does not issue an immediate refund.</p>${proposal.expired || !proposal.eligible ? `<p>${escape(proposal.reason || 'This card has expired. Please request a fresh eligibility check.')}</p>` : `<div class="card-buttons"><button class="primary-button" data-action="confirm-return" data-id="${escape(proposal.id)}">Confirm return</button>`}<button class="secondary-button" data-action="dismiss-return" data-id="${escape(proposal.id)}">${proposal.expired || !proposal.eligible ? 'Dismiss' : 'Not now'}</button>${proposal.expired || !proposal.eligible ? '' : '</div>'}</article>`;
  }
  const pref = current.state.pending_preference;
  if (pref) html += `<article class="action-card"><div class="card-eyebrow">ONLY IF YOU’D LIKE US TO REMEMBER</div><h3>${escape(pref.field)}: ${escape(pref.value)}</h3><p>Use this preference in future conversations.</p><button class="primary-button" data-action="save-preference" data-id="${escape(pref.id)}">Save preference</button></article>`;
  if (current.state.expert_request) html += `<article class="action-card"><div class="card-eyebrow">DEMO EXPERT REQUEST</div><h3>A more personal conversation</h3><p>${escape(current.state.expert_request.question)}</p><p>Request recorded locally. No real person has been contacted; scheduling and author availability are not connected.</p></article>`;
  $('messages').innerHTML = html;
  $('messages').scrollTop = $('messages').scrollHeight;
  renderLab();
  renderExample();
  renderHistory();
}

function renderHistory() {
  if (!me) return;
  const past=(me.cases || []).filter(c=>c.message_count>0 && c.id!==current?.id)
    .sort((a,b)=>new Date(b.updated_at)-new Date(a.updated_at));
  $('open-history').textContent=`◷ Past conversations${past.length ? ` (${past.length})` : ''}`;
  $('history-list').innerHTML=past.length ? past.map(c=>`<article class="history-card"><span class="eyebrow">${escape(date(c.updated_at))} · ${escape(c.status.replaceAll('_',' '))}</span><h3>${escape(c.title)}</h3><p>${escape(c.text)}</p><dl><dt>You asked</dt><dd>${escape(c.request)}</dd><dt>Latest reply</dt><dd>${escape(c.latest_reply)}</dd></dl><button class="secondary-button" data-case-id="${escape(c.id)}">Continue conversation →</button></article>`).join('')
    : '<p class="empty-trace">No earlier conversations yet. Starting a fresh conversation keeps this one saved here.</p>';
}

async function openHistory() {
  if (busy || !current) return;
  $('history-list').textContent='Loading saved conversations…';
  $('history-dialog').showModal();
  try { await refreshMe(); renderHistory(); }
  catch(error) { $('history-list').textContent=error.message; }
}

async function resumeConversation(id) {
  if (busy) return;
  setBusy(true);
  try {
    current=await api('/api/cases/'+encodeURIComponent(id));
    pendingSend=null;
    $('message-input').value='';
    localStorage.setItem('bookly-case-'+me.customer.id,current.id);
    restoreExample();
    renderCase();
    $('history-dialog').close();
  } catch(error) { $('history-list').textContent=error.message; }
  finally { setBusy(false); }
}

function previewSms() {
  if (busy || !current) return;
  const recap=current.summary;
  const name=me.customer.name.split(' ')[0];
  $('sms-message').textContent=current.receipts.length
    ? `Hi ${name}, your return request ${current.receipts[0].id} is recorded. The refund has not been issued yet.`
    : current.proposals.length ? `Hi ${name}, your return terms are ready to review. No return has been submitted yet.`
    : `Hi ${name}, this is Bookly. We can pick up from your saved conversation when you’re ready.`;
  $('sms-recap').textContent=recap?.message_count ? 'Saved context: '+recap.text : 'Start a conversation to see its saved context here.';
  $('sms-dialog').showModal();
}

function exampleFlows() {
  const orders = me?.orders || [];
  const arriving = orders.find(o=>o.status==='shipped') || orders[0];
  const delivered = orders.find(o=>o.status==='delivered' && o.delivered_at && Date.now()-new Date(o.delivered_at).getTime() <= 30*86400000)
    || orders.find(o=>o.status==='delivered');
  return {
    orders:{label:'Find my order',steps:['Where is my order?',
      arriving ? `I mean ${arriving.items[0].title}.` : 'I mean my most recent order.',
      'What should I do if it does not arrive by the estimated date?']},
    returns:{label:'Return a book',steps:['I would like to return a book.',
      delivered ? `I would like to return ${delivered.items[0].title}.` : 'I mean my most recently delivered book.',
      "The book wasn't for me."]},
    support:{label:'General questions',steps:['How much does shipping cost?', 'How do I reset my password?', 'What is your return policy?']},
    discovery:{label:'Find my next read',steps:['Can you help me find my next read?',
      'I would like a light mystery under $22.',
      'Which of those would you pick for me, and why?',
      'Could you remember that I prefer lighter mysteries?']},
  };
}

function saveExample() {
  const key = 'bookly-guide-'+current.id;
  if (example) localStorage.setItem(key,JSON.stringify(example));
  else localStorage.removeItem(key);
}

function restoreExample() {
  example = null;
  try {
    const saved = JSON.parse(localStorage.getItem('bookly-guide-'+current.id));
    const flow = saved && exampleFlows()[saved.topic];
    if (flow && saved.caseId===current.id && Number.isInteger(saved.step) && saved.step>=0 && saved.step<=flow.steps.length) example=saved;
  } catch { /* Invalid browser-local guide state never affects the case. */ }
}

function selectTopic(topic) {
  if (busy || !current || !exampleFlows()[topic]) return;
  example={caseId:current.id,topic,step:0,note:''};
  saveExample();
  renderExample();
  useExample();
}

function renderExample() {
  if (example?.caseId!==current?.id) example=null;
  for (const topic of ['orders','returns','discovery','support']) {
    const active=example?.topic===topic;
    $('topic-'+topic).classList.toggle('active',active);
    $('topic-'+topic).setAttribute('aria-pressed',String(active));
  }
  $('example-guide').hidden=!example;
  $('message-input').setAttribute('aria-describedby',example ? 'example-note' : 'channel-note');
  if (!example) return;
  const flow=exampleFlows()[example.topic];
  const done=example.step>=flow.steps.length;
  const waiting=example.topic==='returns' && current.proposals.length>0;
  const saving=example.topic==='discovery' && !!current.state.pending_preference;
  $('example-label').textContent=`${flow.label} · ${waiting ? 'Review return' : saving ? 'Save preference' : done ? 'Example complete' : `Example ${example.step+1} of ${flow.steps.length}`}`;
  $('example-note').textContent=waiting ? 'Review the return card to confirm or decline. You can still ask questions in your own words.'
    : saving ? 'Use Save preference on the card only if you want to remember this. You can also keep chatting.'
    : example.note || (done ? 'Continue in your own words, or choose another example.' : 'Editable example draft. Change it or replace it with your own message; only Send or Enter submits it.');
  $('example-use').hidden=done || waiting || saving || !!example.note;
  $('example-next').hidden=!(example.topic==='returns' && current.receipts.length>0);
}

function useExample() {
  if (busy || !example) return;
  const text=exampleFlows()[example.topic].steps[example.step];
  if (!text || $('example-use').hidden) return;
  draft(text);
  $('message-input').setSelectionRange(0,text.length);
}

function advanceExample(newEvents=[]) {
  if (!example || example.caseId!==current.id) return;
  const flow=exampleFlows()[example.topic];
  example.step=Math.min(example.step+1,flow.steps.length);
  example.note='';
  if (example.topic==='returns') {
    if (current.receipts.length) {
      example.step=flow.steps.length;
      example.note='Return request recorded. You can try book discovery next, or continue in your own words.';
    } else if (newEvents.some(e=>e.name==='returns.check_eligibility' && e.data.eligible===false)) {
      example.step=flow.steps.length;
      example.note='This copy is not eligible for another return. Reset demo data to replay the example, or continue in your own words.';
    }
  }
  saveExample();
  renderExample();
  // Suggested follow-ups never replace a draft the customer has already written.
  if (!$('message-input').value.trim() && !$('example-use').hidden) {
    const text=flow.steps[example.step];
    $('message-input').value=text;
    $('message-input').setSelectionRange(0,text.length);
  }
}

function messageHtml(m) {
  const assistant = m.role === 'assistant';
  const label = assistant ? (m.source === 'application' ? 'Bookly update' : 'Bookly concierge') : escape(me.customer.name.split(' ')[0]);
  // Assistant HTML is rendered server-side with raw HTML and image parsing disabled.
  const content = assistant && typeof m.html === 'string' ? m.html : escape(m.content);
  const recommendations=assistant && m.recommendations?.length ? recommendationHtml(m.recommendations) : '';
  const receipt=assistant && m.return_receipt ? receiptHtml(m.return_receipt) : '';
  return `<div class="message ${assistant ? 'assistant' : 'user'}">${assistant ? '<div class="message-avatar" aria-hidden="true">b.</div>' : ''}<div class="message-body"><div class="message-label">${label}<span class="message-time">${m.created_at ? escape(time(m.created_at)) : 'Sending…'}</span></div><div class="message-content ${assistant ? 'markdown' : ''}">${content}</div>${recommendations}${receipt}</div></div>`;
}

function receiptHtml(receipt) {
  return `<article class="action-card return-receipt"><div class="card-eyebrow">RETURN REQUEST RECORDED · ${escape(receipt.id)}</div><h3>Your next step</h3><p>${escape(receipt.instructions)}</p><p>${money(receipt.refund_cents)} · ${escape(receipt.terms)}</p><button class="chip" data-prompt="Can you help me find another book?">Help me find something different →</button></article>`;
}

function recommendationHtml(books) {
  return `<div class="recommendation-grid">${books.map(b => `<article class="recommendation">${cover(b)}<h3>${escape(b.title)}</h3><p>${escape(b.author)}</p><div class="recommendation-reason">${typeof b.reason_html === 'string' ? b.reason_html : escape(b.reason)}</div><span class="price">${money(b.price_cents)}</span></article>`).join('')}</div>`;
}

function draft(text) {
  if (busy || !current) return;
  $('message-input').value = text;
  $('message-input').focus();
  $('message-input').setSelectionRange(text.length, text.length);
}

function renderLab() {
  $('trace-tab').classList.toggle('selected',labTab==='trace');
  $('state-tab').classList.toggle('selected',labTab==='state');
  $('prompts-tab').classList.toggle('selected',labTab==='prompts');
  if (!current) return;
  if (labTab==='prompts') {
    $('lab-content').innerHTML=promptProfiles ? promptProfiles.profiles.map(p=>`<section class="prompt-profile"><h3>${escape(p.channel==='chat'?'Web chat':p.channel==='sms'?'Text messaging':'Voice')} <span class="demo-tag">${p.implemented?'Active':'Prompt example only'}</span></h3><p>${escape(p.instructions)}</p></section>`).join('') : '<p>Loading channel prompts…</p>';
    return;
  }
  $('lab-content').innerHTML = labTab === 'state' ? `<pre>${escape(JSON.stringify({case_id:current.id,channel:current.channel,customer:me.customer,state:current.state},null,2))}</pre>` : current.events.length ? [...current.events].reverse().map(e => `<details class="trace-event"><summary>${escape(e.name)}<span class="trace-time">${escape(time(e.created_at))}</span></summary><pre>${escape(JSON.stringify(e.data,null,2))}</pre></details>`).join('') : '<p class="empty-trace">Send a message to see actual tool calls and recorded outcomes. No hidden model reasoning is shown.</p>';
}

async function showPrompts() {
  labTab='prompts';
  renderLab();
  try { promptProfiles=await api('/api/demo/channel-prompts'); renderLab(); }
  catch(error) { $('lab-content').textContent=error.message; }
}

async function refreshMe() { me = await api('/api/me'); renderProfile(); }

async function loadCase() {
  const saved = localStorage.getItem('bookly-case-'+me.customer.id);
  const match = me.cases.find(c=>c.id===saved) || me.cases[0];
  current = match ? await api('/api/cases/'+match.id) : await api('/api/cases',{channel:'chat'});
  localStorage.setItem('bookly-case-'+me.customer.id,current.id);
  restoreExample();
  renderCase();
}

async function send(text) {
  if (busy || !text.trim()) return;
  $('error').hidden = true;
  if (!pendingSend || pendingSend.text !== text.trim() || pendingSend.caseId !== current.id) pendingSend = {text:text.trim(),request_id:crypto.randomUUID(),caseId:current.id};
  setBusy(true);
  const eventStart=current.events.length;
  $('message-input').value = '';
  $('messages').insertAdjacentHTML('beforeend', messageHtml({role:'user',content:text}));
  $('messages').scrollTop = $('messages').scrollHeight;
  try {
    current = await api(`/api/cases/${current.id}/messages`,{text:pendingSend.text,request_id:pendingSend.request_id});
    pendingSend = null;
    advanceExample(current.events.slice(eventStart));
    renderCase();
  } catch(error) { renderCase(); $('message-input').value = text; showError(error); }
  finally { setBusy(false); $('message-input').focus(); }
}

function showSource(button, show=true) {
  const popup=button.nextElementSibling;
  if (!show) { popup.hidePopover(); return; }
  document.querySelectorAll('.source-popover:popover-open').forEach(p=>{if(p!==popup)p.hidePopover();});
  popup.showPopover();
  const anchor=button.getBoundingClientRect(), box=popup.getBoundingClientRect();
  popup.style.left=Math.max(8,Math.min(anchor.left,window.innerWidth-box.width-8))+'px';
  const below=anchor.bottom+6;
  popup.style.top=(below+box.height<=window.innerHeight-8 ? below : Math.max(8,anchor.top-box.height-6))+'px';
}

for (const eventName of ['pointerover','focusin']) document.addEventListener(eventName,event=>{
  const button=event.target.closest('.source-trigger');
  if (button) showSource(button);
});
for (const eventName of ['pointerout','focusout']) document.addEventListener(eventName,event=>{
  const reference=event.target.closest('.source-reference');
  if (reference && !reference.contains(event.relatedTarget)) showSource(reference.querySelector('.source-trigger'),false);
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape') document.querySelectorAll('.source-popover:popover-open').forEach(p=>p.hidePopover());
});

document.addEventListener('click', async event => {
  const reference=event.target.closest('.source-trigger');
  if (reference) { showSource(reference); return; }
  const saved=event.target.closest('[data-case-id]');
  if (saved) return resumeConversation(saved.dataset.caseId);
  const topic=event.target.closest('[data-topic]');
  if (topic) return selectTopic(topic.dataset.topic);
  const prompt = event.target.closest('[data-prompt]');
  if (prompt) return draft(prompt.dataset.prompt);
  const button = event.target.closest('[data-action]');
  if (!button || busy) return;
  const paths = {'confirm-return':`returns/${button.dataset.id}/confirm`,'dismiss-return':`returns/${button.dataset.id}/dismiss`,'save-preference':`preferences/${button.dataset.id}/confirm`};
  setBusy(true);
  $('error').hidden = true;
  try { current = await api(`/api/cases/${current.id}/${paths[button.dataset.action]}`,{}); await refreshMe(); advanceExample(); renderCase(); }
  catch(error) { showError(error); }
  finally { setBusy(false); }
});

$('composer').addEventListener('submit', event=>{event.preventDefault();send($('message-input').value);});
$('message-input').addEventListener('keydown', event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('composer').requestSubmit();}});
$('open-lab').onclick=()=>{$('lab').showModal();renderLab();};
$('close-lab').onclick=()=>$('lab').close();
$('trace-tab').onclick=()=>{labTab='trace';renderLab();};
$('state-tab').onclick=()=>{labTab='state';renderLab();};
$('prompts-tab').onclick=showPrompts;
$('open-history').onclick=openHistory;
$('open-history-mobile').onclick=openHistory;
$('close-history').onclick=()=>$('history-dialog').close();
$('sms-preview').onclick=previewSms;
$('close-sms').onclick=()=>$('sms-dialog').close();
$('sms-prompts').onclick=()=>{$('sms-dialog').close();$('lab').showModal();showPrompts();};
$('example-use').onclick=useExample;
$('example-dismiss').onclick=()=>{if(busy)return;example=null;saveExample();renderExample();};
$('customer-select').onchange=async event=>{setBusy(true);try{await api('/api/demo/session',{customer_id:event.target.value});await refreshMe();await loadCase();}catch(error){showError(error);}finally{setBusy(false);}};
$('new-case').onclick=async()=>{if(busy)return;setBusy(true);try{current=await api('/api/cases',{channel:'chat'});localStorage.setItem('bookly-case-'+me.customer.id,current.id);pendingSend=null;example=null;$('message-input').value='';await refreshMe();renderCase();}catch(error){showError(error);}finally{setBusy(false);}};

function openReset() {
  if (busy || !current) return;
  if ($('lab').open) $('lab').close();
  $('reset-error').hidden = true;
  $('reset-dialog').showModal();
}
$('reset-demo').onclick = openReset;
$('reset-demo-lab').onclick = openReset;
$('reset-cancel').onclick = () => $('reset-dialog').close();
$('reset-confirm').onclick = async () => {
  if (busy) return;
  setBusy(true);
  $('reset-error').hidden = true;
  try {
    const fresh = await api('/api/demo/reset', {confirm:'RESET',channel:'chat'});
    for (const key of Object.keys(localStorage)) if (key.startsWith('bookly-case-') || key.startsWith('bookly-guide-')) localStorage.removeItem(key);
    current = fresh;
    pendingSend = null;
    example = null;
    $('message-input').value = '';
    $('error').hidden = true;
    localStorage.setItem('bookly-case-'+me.customer.id, current.id);
    renderCase();
    $('reset-dialog').close();
    await refreshMe();
  } catch(error) {
    if ($('reset-dialog').open) { $('reset-error').textContent = error.message; $('reset-error').hidden = false; }
    else showError(error);
  } finally { setBusy(false); }
};

(async()=>{
  try{
    try { await refreshMe(); } catch(error) { if(error.status!==401)throw error;await api('/api/demo/session',{customer_id:'maya'});await refreshMe(); }
    await loadCase();
  }catch(error){$('boot-error').textContent='Could not connect to Bookly: '+error.message;$('boot-error').hidden=false;}
})();
