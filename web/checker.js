(() => {
  const $ = id => document.getElementById(id);
  const form = $('check-form');
  let running = false, currentResult = null, currentRecord = '', lastKind = 'record', detecting = false;
  function animate(element) {
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) element.animate([{opacity:0,transform:'translateY(8px)'},{opacity:1,transform:'translateY(0)'}],{duration:350,easing:'ease-out'});
  }
  function validUrl() {
    try { const url = new URL($('url').value.trim()); return ['https:','http:'].includes(url.protocol); } catch (_) { return false; }
  }
  document.querySelectorAll('[data-preset]').forEach(button => button.addEventListener('click', () => {
    if(running)return;
    const failure = button.dataset.preset === 'failure';
    $('url').value = failure ? 'https://httpbin.org/status/503' : 'https://example.com';
    $('provider').value='other'; $('bill').value=''; $('uptime').value='';
    $('preset-note').textContent = failure ? 'Controlled test: this endpoint is designed to return HTTP 503. It is not a provider outage.' : 'Healthy control target. Results still depend on the measured response at check time.';
    $('provider-hint').textContent='Test preset selected. Choose a provider only for a relevant service.';
    $('url').focus();
  }));
  $('url').addEventListener('input', () => { $('preset-note').textContent=''; $('provider-hint').textContent='Choose the exact service for a credit estimate.'; });
  $('detect-provider').addEventListener('click', async () => {
    if(detecting||running)return;
    if(!validUrl()){ $('provider-hint').textContent='Enter a valid public HTTP or HTTPS URL first.'; return; }
    detecting=true; const button=$('detect-provider'); button.disabled=true; button.textContent='Detecting…';
    const target=$('url').value.trim(), selectedProvider=$('provider').value;
    $('run').disabled=true;
    try {
      const response=await fetch('/api/detect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:target}),signal:AbortSignal.timeout(12000)});
      const data=await response.json();
      if(!response.ok||!data.ok)throw new Error(data.error||'Detection unavailable');
      if($('url').value.trim()!==target||$('provider').value!==selectedProvider)return;
      if(data.detected){ $('provider').value=data.detected.provider; $('provider-hint').textContent='Suggested: '+(data.detected.provider_name||data.detected.provider)+'. Confirm the exact service; detection is a best guess.'; }
      else $('provider-hint').textContent='No supported provider identified. Select one manually or use Other.';
    }catch(_){if($('url').value.trim()===target&&$('provider').value===selectedProvider)$('provider-hint').textContent='Provider detection is unavailable. You can choose manually.';}
    finally{detecting=false;button.disabled=running;$('run').disabled=running;button.textContent='Detect provider';}
  });
  function setRunning(value) {
    running=value;
    form.querySelectorAll('input,select,button').forEach(el=>el.disabled=value);
    $('run-label').textContent=value?'Verifying endpoint…':'Run verification';
    $('run-output').setAttribute('aria-busy',String(value));
    $('progress').hidden=!value;
    $('run-state').textContent=value?'Probing':'Ready';
    $('run-state').className='status-chip'+(value?' running':'');
  }
  function node(tag, cls, text) { const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el; }
  form.addEventListener('submit', async event => {
    event.preventDefault();if(running||detecting)return;
    $('form-error').hidden=true;
    if(!validUrl()){ $('form-error').textContent='Use a complete HTTP or HTTPS URL.'; $('form-error').hidden=false;return; }
    const payload={url:$('url').value.trim(),provider:$('provider').value,checks:Number($('checks').value),bill:$('bill').value,uptime:$('uptime').value};
    setRunning(true);currentResult=null;currentRecord='';
    $('results').hidden=true;$('empty-state').hidden=true;$('evidence-drawer').hidden=true;$('announcement').textContent='';
    animate($('progress'));
    if(innerWidth<851)$('run-output').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
    try {
      const response=await fetch('/api/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(40000)});
      const data=await response.json();
      if(!response.ok||!data.ok||!Array.isArray(data.checks)||!data.checks.length)throw new Error(data.error||'The miner did not return a valid measurement.');
      currentResult=data;
      render(data,payload);
    } catch(error) {
      setRunning(false);$('empty-state').hidden=false;
      $('run-state').textContent='Unavailable';
      $('form-error').textContent=error.name==='TimeoutError'?'The miner did not respond in time. No result has been inferred. Please try again.':'Check unavailable. '+error.message+' Please retry.';
      $('form-error').hidden=false;
      $('announcement').textContent='The check could not complete. No result or claim was generated.';
    }
  });
  function render(data,payload) {
    setRunning(false);const breached=data.verdict==='breach';
    $('results').hidden=false;$('empty-state').hidden=true;
    $('run-state').textContent=breached?'Threshold breached':'Checks passed';$('run-state').className='status-chip'+(breached?' breach':'');
    $('verdict-icon').textContent=breached?'!':'✓';$('verdict-icon').style.color=breached?'var(--red)':'var(--green)';
    $('verdict-title').textContent=breached?'A threshold was breached.':'Within the check threshold.';
    const failed=data.checks.filter(item=>item.sla?.breached).length;
    $('verdict-summary').textContent=`${failed} of ${data.checks.length} samples breached the 1,000 ms / availability threshold for ${payload.url}. This is a point-in-time check.`;
    $('sample-count').textContent=String(data.checks.length);
    const times=data.checks.map(item=>item.latency_ms).filter(v=>typeof v==='number'&&Number.isFinite(v));
    $('latency-value').textContent=times.length?Math.round(times.reduce((a,b)=>a+b,0)/times.length)+' ms':'No response';
    $('samples').replaceChildren(...data.checks.map((sample,index)=>{ const row=node('div','sample'); row.append(node('span','',`SAMPLE ${String(index+1).padStart(2,'0')}`),node('span',sample.sla?.breached?'bad':'good',sample.status_code?'HTTP '+sample.status_code:(sample.is_up?'Responded':'No response')),node('span','',typeof sample.latency_ms==='number'?Math.round(sample.latency_ms)+' ms':'—'));if(sample.error)row.append(node('small','sample-error',sample.error));row.title=sample.summary||sample.error||'';return row; }));
    const credit=$('credit-result');credit.hidden=!data.owed;
    if(data.owed){credit.replaceChildren(node('span','','Estimated service credit'),node('strong','',new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(data.owed.amount)),node('p','',`${data.owed.pct}% of the affected monthly bill, using your supplied monthly uptime. Provider terms and exclusions apply; this is not an approved refund.`));}
    $('raw-output').textContent=JSON.stringify(data,null,2);
    lastKind=breached?'claim-draft':'check-record';
    currentRecord=breached?'DRAFT FOR REVIEW — point-in-time observations do not establish monthly SLA eligibility. Confirm the exact service, monitoring period, exclusions, and claim requirements before sending. Any credit figure is an estimate, not an approved payment.\n\n'+data.letter:data.honesty_record;
    $('record-title').textContent=breached?'Claim draft · review before filing':'Check record · no claim prepared';
    $('record-text').value=currentRecord||'';$('copy-status').textContent='';
    $('announcement').textContent='Verification complete. '+(breached?'Review the observations and draft.':'No compensation claim has been prepared.');
    animate($('results'));
  }
  $('view-record').addEventListener('click',()=>{if(!currentResult)return;$('evidence-drawer').hidden=false;animate($('evidence-drawer'));$('evidence-drawer').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});});
  function download(content,type,name){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $('download-json').addEventListener('click',()=>{if(currentResult)download(JSON.stringify(currentResult,null,2),'application/json','downproof-evidence.json');});
  $('download-record').addEventListener('click',()=>{if(currentRecord)download(currentRecord,'text/markdown','downproof-'+lastKind+'.md');});
  $('copy-record').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(currentRecord);$('copy-status').textContent='Record copied.';}catch(_){$('record-text').focus();$('record-text').select();$('copy-status').textContent='Clipboard unavailable. The text is selected for manual copying.';}});
})();
