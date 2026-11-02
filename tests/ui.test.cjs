// Exercise actual event handlers without a build step or third-party DOM dependency.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const {randomUUID} = require('node:crypto');

const tick = () => new Promise(resolve => setImmediate(resolve));

async function setup(options={}) {
  const nodes = new Map(), documentEvents = {}, requests = [];
  const storage = {};
  const localStorage = storage;
  Object.defineProperties(localStorage, {getItem:{value:k=>storage[k]??null},
    setItem:{value:(k,v)=>{storage[k]=v;}},removeItem:{value:k=>{delete storage[k];}}});
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {value:'',innerHTML:'',textContent:'',disabled:false,hidden:false,open:false,scrollHeight:100,
      listeners:{},classes:new Set(),attributes:{},classList:{toggle(name,active){if(active)node(id).classes.add(name);else node(id).classes.delete(name);}},setAttribute(name,value){this.attributes[name]=value;},focus(){},setSelectionRange(){},
      insertAdjacentHTML(position,html){this.innerHTML+=html;},showModal(){this.open=true;},close(){this.open=false;},
      addEventListener(event,fn){this.listeners[event]=fn;},
      requestSubmit(){this.listeners.submit({preventDefault(){}});}});
    return nodes.get(id);
  }
  let activeCase = {id:'case-1',channel:'chat',messages:[],events:[],proposals:[],receipts:[],state:{}};
  const profile = {customer:{id:'maya',name:'Maya Chen',preferences:{}},orders:[
    {id:'order-1',status:'shipped',estimated_arrival:'2026-11-03',items:[{title:'The Last Lighthouse',author:'Rowan Ellis',color:'#617f82'}]},
    {id:'order-2',status:'delivered',delivered_at:new Date().toISOString(),items:[{title:'The Midnight Archive',author:'Elena Vale',color:'#374e5e'}]},
  ],cases:options.cases||[],mode:options.mode||'live',provider:'anthropic',model:'test-live-model'};
  let failures=options.failures||0;
  const fetch = async (path,options) => {
    requests.push({path,...options});
    let data;
    if (path==='/api/me') data=profile;
    else if (path==='/api/cases') data=activeCase;
    else if (path==='/api/cases/case-1') data=activeCase;
    else if (path==='/api/cases/case-old') data=setupOptions.savedCase;
    else if (path==='/api/demo/channel-prompts') data={active:'chat',profiles:[
      {channel:'chat',implemented:true,instructions:'Use confirmation cards.'},
      {channel:'sms',implemented:false,instructions:'Use short plain text.'},
      {channel:'voice',implemented:false,instructions:'Use short spoken sentences.'},
    ]};
    else if (path==='/api/demo/reset') {
      activeCase={...activeCase,id:'case-2',messages:[],events:[],state:{}};
      data=activeCase;
    } else if (path.endsWith('/messages')) {
      if(failures-->0)return {ok:false,status:503,json:async()=>({detail:'Try again'})};
      const body=JSON.parse(options.body);
      activeCase={...activeCase,messages:[{role:'user',content:body.text,created_at:'2026-11-01T12:00:00Z'},
        {role:'assistant',content:'**Actual reply**',html:'<p><strong>Actual reply</strong></p>',source:'agent',created_at:'2026-11-01T12:00:01Z'}]};
      if (setupOptions.onMessage) Object.assign(activeCase,setupOptions.onMessage(body,activeCase));
      data=activeCase;
    } else throw new Error('Unexpected request: '+path);
    return {ok:true,json:async()=>JSON.parse(JSON.stringify(data))};
  };
  const setupOptions=options;
  runInNewContext(readFileSync('bookly/static/app.js','utf8'), {
    document:{getElementById:node,querySelectorAll:()=>[],addEventListener:(event,fn)=>{documentEvents[event]=fn;}},
    localStorage,fetch,crypto:{randomUUID},console,
  });
  await tick();
  return {node,requests,storage,
    clickDraft:text=>documentEvents.click({target:{closest:selector=>selector==='[data-prompt]'?{dataset:{prompt:text}}:null}}),
    clickTopic:topic=>documentEvents.click({target:{closest:selector=>selector==='[data-topic]'?{dataset:{topic}}:null}}),
    clickHistory:caseId=>documentEvents.click({target:{closest:selector=>selector==='[data-case-id]'?{dataset:{caseId}}:null}})};
}

test('fresh live conversation has no fabricated assistant messages and shows the model',async()=>{
  const {node,requests}=await setup();
  assert.match(node('messages').innerHTML,/What can we help you with/);
  assert.doesNotMatch(node('messages').innerHTML,/message-avatar|Hi Maya/);
  assert.equal(node('mode-label').textContent,'Live · test-live-model');
  assert.equal(requests.filter(r=>r.path.endsWith('/messages')).length,0);
});

test('suggestions fill an editable draft; only explicit submission sends it',async()=>{
  const {node,requests,clickDraft}=await setup();
  await clickDraft('Where is my order?');
  await tick();
  assert.equal(node('message-input').value,'Where is my order?');
  assert.equal(requests.filter(r=>r.path.endsWith('/messages')).length,0);
  node('message-input').value='My edited question';
  node('composer').requestSubmit();
  await tick();
  const sent=requests.filter(r=>r.path.endsWith('/messages'));
  assert.equal(sent.length,1);
  assert.equal(JSON.parse(sent[0].body).text,'My edited question');
  assert.match(node('messages').innerHTML,/<strong>Actual reply<\/strong>/);
  assert.doesNotMatch(node('messages').innerHTML,/\*\*Actual reply\*\*/);
});

test('Enter sends a draft, while Shift+Enter and composition do not',async()=>{
  const {node,requests,clickDraft}=await setup();
  await clickDraft('A return question');
  const key=(extra={})=>node('message-input').listeners.keydown({key:'Enter',preventDefault(){},...extra});
  key({shiftKey:true});
  key({isComposing:true});
  await tick();
  assert.equal(requests.filter(r=>r.path.endsWith('/messages')).length,0);
  key();
  await tick();
  assert.equal(requests.filter(r=>r.path.endsWith('/messages')).length,1);
});

test('reset requires confirmation and clears the draft and selected case',async()=>{
  const {node,requests,storage,clickDraft}=await setup();
  await clickDraft('Do not send this yet');
  node('reset-demo').onclick();
  assert.equal(node('reset-dialog').open,true);
  assert.equal(requests.filter(r=>r.path==='/api/demo/reset').length,0);
  node('reset-cancel').onclick();
  assert.equal(node('message-input').value,'Do not send this yet');
  node('reset-demo').onclick();
  await node('reset-confirm').onclick();
  assert.equal(node('reset-dialog').open,false);
  assert.equal(node('message-input').value,'');
  assert.equal(storage['bookly-case-maya'],'case-2');
  assert.match(node('messages').innerHTML,/What can we help you with/);
  const reset=requests.find(r=>r.path==='/api/demo/reset');
  assert.equal(JSON.parse(reset.body).confirm,'RESET');
});

test('selecting a topic highlights only that topic and drafts its first turn',async()=>{
  const {node,requests,clickTopic}=await setup();
  assert.equal(node('topic-orders').attributes['aria-pressed'],'false');
  await clickTopic('returns');
  assert.equal(node('topic-returns').attributes['aria-pressed'],'true');
  assert.equal(node('topic-orders').attributes['aria-pressed'],'false');
  assert.equal(node('message-input').value,'I would like to return a book.');
  assert.match(node('example-label').textContent,/Example 1 of 3/);
  await clickTopic('discovery');
  assert.equal(node('topic-returns').attributes['aria-pressed'],'false');
  assert.equal(node('topic-discovery').attributes['aria-pressed'],'true');
  assert.equal(requests.filter(r=>r.path.endsWith('/messages')).length,0);
});

test('follow-up drafts advance after replies, remain editable, and never send themselves',async()=>{
  const {node,requests,clickTopic}=await setup();
  await clickTopic('orders');
  node('composer').requestSubmit();
  await tick();
  assert.equal(node('message-input').value,'I mean The Last Lighthouse.');
  assert.match(node('example-label').textContent,/Example 2 of 3/);
  assert.equal(requests.filter(r=>r.path.endsWith('/messages')).length,1);
  node('message-input').value='Actually, could you check the other book?';
  node('composer').requestSubmit();
  await tick();
  assert.equal(JSON.parse(requests.filter(r=>r.path.endsWith('/messages'))[1].body).text,'Actually, could you check the other book?');
  assert.match(node('message-input').value,/estimated date/);
  node('composer').requestSubmit();
  await tick();
  assert.equal(node('message-input').value,'');
  assert.match(node('example-label').textContent,/Example complete/);
});

test('a failed request preserves the current example step and original draft',async()=>{
  const {node,requests,clickTopic}=await setup({failures:1});
  await clickTopic('returns');
  node('composer').requestSubmit();
  await tick();
  assert.equal(node('message-input').value,'I would like to return a book.');
  assert.match(node('example-label').textContent,/Example 1 of 3/);
  node('composer').requestSubmit();
  await tick();
  assert.equal(node('message-input').value,'I would like to return The Midnight Archive.');
  const calls=requests.filter(r=>r.path.endsWith('/messages'));
  assert.equal(JSON.parse(calls[0].body).request_id,JSON.parse(calls[1].body).request_id);
});

test('the return guide pauses for real confirmation instead of drafting consent',async()=>{
  const {node,requests,clickTopic}=await setup({onMessage:()=>({proposals:[{id:'proposal-1',title:'The Midnight Archive',eligible:true,refund_cents:2400,terms:'Mail the book back.'}]})});
  await clickTopic('returns');
  node('composer').requestSubmit();
  await tick();
  assert.equal(node('message-input').value,'');
  assert.equal(node('example-use').hidden,true);
  assert.match(node('example-note').textContent,/Review the return card/);
  assert.match(node('example-label').textContent,/Review return/);
  assert.equal(requests.filter(r=>r.path.includes('/confirm')).length,0);
});

test('reset clears the selected example, draft, and browser-local guide progress',async()=>{
  const {node,storage,clickTopic}=await setup();
  await clickTopic('returns');
  assert.ok(storage['bookly-guide-case-1']);
  await node('reset-confirm').onclick();
  assert.equal(node('example-guide').hidden,true);
  assert.equal(node('topic-returns').attributes['aria-pressed'],'false');
  assert.equal(storage['bookly-guide-case-1'],undefined);
  assert.equal(node('message-input').value,'');
});

test('SMS preview does not submit a message or change the case channel',async()=>{
  const {node,requests}=await setup();
  const initial=requests.length;
  node('sms-preview').onclick();
  assert.equal(node('sms-dialog').open,true);
  assert.match(node('sms-message').textContent,/Hi Maya/);
  assert.equal(requests.length,initial);
  node('sms-prompts').onclick();
  await tick();
  assert.equal(node('lab').open,true);
  assert.match(node('lab-content').innerHTML,/Prompt example only/);
  assert.equal(requests.filter(r=>r.path.endsWith('/channel') || r.path.endsWith('/messages')).length,0);
});

test('past conversations show recaps and reopen an owned saved case without sending',async()=>{
  const old={id:'case-old',message_count:2,title:'Order question',request:'Where is my book?',
    latest_reply:'Your book has shipped.',text:'Discussed order questions.',status:'open',updated_at:'2026-11-01T12:00:00Z'};
  const savedCase={id:'case-old',channel:'chat',messages:[{role:'user',content:'Where is my book?'}],
    events:[],state:{},proposals:[],receipts:[],summary:old};
  const {node,requests,storage,clickHistory}=await setup({cases:[{id:'case-1',message_count:0},old],savedCase});
  await node('open-history').onclick();
  assert.equal(node('history-dialog').open,true);
  assert.match(node('history-list').innerHTML,/Discussed order questions/);
  assert.match(node('history-list').innerHTML,/Your book has shipped/);
  await clickHistory('case-old');
  assert.equal(node('history-dialog').open,false);
  assert.equal(storage['bookly-case-maya'],'case-old');
  assert.match(node('messages').innerHTML,/Where is my book/);
  assert.equal(requests.filter(r=>r.path.endsWith('/messages')).length,0);
});


test('scripted mode shows a red-state badge and live setup instructions',async()=>{
  const {node}=await setup({mode:'scripted'});
  assert.equal(node('mode-label').textContent,'Scripted · enable live');
  assert.equal(node('open-lab').classes.has('is-scripted'),true);
  assert.equal(node('live-setup').hidden,false);
  assert.match(node('open-lab').attributes.title,/instructions/);
  node('open-lab').onclick();
  assert.equal(node('lab').open,true);
  const html=readFileSync('bookly/static/index.html','utf8');
  assert.match(html,/LLM_PROVIDER=anthropic/);
  assert.match(html,/LLM_MODEL=your-model-id/);
  assert.match(html,/LLM_API_KEY=your-key/);
  assert.match(html,/docker compose up --build -d --force-recreate web --wait/);
  const css=readFileSync('bookly/static/styles.css','utf8');
  assert.match(css,/\.lab-trigger\.is-scripted\{color:#a52d2d/);
});

test('live mode hides setup instructions and clears the scripted badge state',async()=>{
  const {node}=await setup();
  assert.equal(node('live-setup').hidden,true);
  assert.equal(node('open-lab').classes.has('is-scripted'),false);
});

test('general support guide drafts shipping and password questions without sending automatically',async()=>{
  const {node,requests,clickTopic}=await setup();
  await clickTopic('support');
  assert.equal(node('topic-support').attributes['aria-pressed'],'true');
  assert.equal(node('message-input').value,'How much does shipping cost?');
  assert.equal(requests.filter(r=>r.path.endsWith('/messages')).length,0);
  node('composer').requestSubmit();
  await tick();
  assert.equal(node('message-input').value,'How do I reset my password?');
});

test('recommendation cards stay beside their original reply when the topic changes',async()=>{
  const books=[{id:'lantern',title:'The Lantern Club',author:'Ada Moss',color:'#727c50',price_cents:2000,reason:'A warm mystery.'}];
  const earlier={role:'assistant',content:'A reading suggestion.',html:'<p>A reading suggestion.</p>',recommendations:books};
  const {node}=await setup({onMessage:()=>({state:{recommendations:books},messages:[earlier,{role:'user',content:'What is your return policy?'},{role:'assistant',content:'Our return policy.',html:'<p>Our return policy.</p>',recommendations:[]}]})});
  node('message-input').value='What is your return policy?';
  node('composer').requestSubmit();
  await tick();
  const html=node('messages').innerHTML;
  assert.equal((html.match(/class="recommendation-grid"/g)||[]).length,1);
  assert.ok(html.indexOf('The Lantern Club') < html.indexOf('What is your return policy?'));
  assert.ok(html.indexOf('The Lantern Club') < html.indexOf('Our return policy.'));
});

test('completed return receipt stays with the confirmation update rather than later answers',async()=>{
  const receipt={id:'RET-TEST',refund_cents:2400,instructions:'Mail the book back.',terms:'Refund after inspection.'};
  const confirmed={role:'assistant',source:'application',content:'Your return is recorded: RET-TEST.',return_receipt:receipt};
  const {node}=await setup({onMessage:()=>({receipts:[receipt],proposals:[],messages:[confirmed,{role:'user',content:'What is your return policy?'},{role:'assistant',content:'Our return policy.',return_receipt:null}]})});
  node('message-input').value='What is your return policy?';
  node('composer').requestSubmit();
  await tick();
  const html=node('messages').innerHTML;
  assert.equal((html.match(/class="action-card return-receipt"/g)||[]).length,1);
  assert.ok(html.indexOf('Your next step') < html.indexOf('What is your return policy?'));
  assert.ok(html.indexOf('Your next step') < html.indexOf('Our return policy.'));
  assert.match(html,/Bookly update/);
});
