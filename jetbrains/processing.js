'use strict';
const {$,el,label,request,message,button,action}=UI;
let activeTab='queue',overview=null,items=[],selection=new Set(),version=0,loaded=100,more=false,signature='',mutating=false;
const views={queue:'queued',failures:'failed',history:'history',canceled:'canceled'};
const tabs=[...document.querySelectorAll('[data-tab]')];
const canceled=button('Canceled ',null);canceled.id='canceled-tab';canceled.dataset.tab='canceled';canceled.setAttribute('role','tab');canceled.setAttribute('aria-controls','jobs-panel');canceled.setAttribute('aria-selected','false');canceled.tabIndex=-1;const canceledCount=el('span','0');canceledCount.id='canceled-count';canceled.append(canceledCount);$('.processing-tabs').append(canceled);tabs.push(canceled);
const toolbar=el('div',null,'jobs-actions');$('.processing-tabs').after(toolbar);
const earlier=button('Move earlier',()=>bulk('reorder','earlier')),later=button('Move later',()=>bulk('reorder','later')),cancelSelected=button('Cancel selected',()=>bulk('cancel')),retrySelected=button('Retry selected',()=>bulk('retry'));
const refreshButton=button('Refresh',()=>refresh());const summary=el('span','Loading…','jobs-summary');toolbar.append(earlier,later,cancelSelected,retrySelected,refreshButton,summary);
const pause=$('#pause-job'),cancel=$('#cancel-job'),selectAll=$('#select-jobs');
const estimate=$('.job-timing>span:last-child span');
$('.job-timing>span:last-child').firstChild.textContent='Likely duration ≈ ';
const stateText=el('span','','job-state');$('.job-heading').append(stateText);
$('#job-progress').removeAttribute('value');
function controls(){
  const chosen=items.filter(j=>selection.has(j.id));
  const all=control=>chosen.length>0&&chosen.every(j=>j.allowed_controls.includes(control));
  earlier.hidden=later.hidden=cancelSelected.hidden=activeTab!=='queue';retrySelected.hidden=activeTab!=='failures';
  earlier.disabled=mutating||!all('move_earlier');later.disabled=mutating||!all('move_later');cancelSelected.disabled=mutating||!all('cancel');retrySelected.disabled=mutating||!chosen.length;
  selectAll.disabled=items.length===0||!['queue','failures'].includes(activeTab);
  selectAll.checked=chosen.length>0&&chosen.length===items.length;selectAll.indeterminate=chosen.length>0&&chosen.length<items.length;
  if(overview){
    pause.disabled=mutating||!overview.current?.allowed_controls.some(c=>c==='pause'||c==='resume');
    cancel.disabled=mutating||!overview.current?.allowed_controls.includes('cancel');
  }
}
async function bulk(operation,direction){
  if(mutating||!selection.size)return;mutating=true;controls();
  try{
    const ids=[...selection];if(ids.length>100)throw new Error('Select at most 100 jobs per request.');
    const result=await request(`/api/v1/processing/jobs/${operation}`,{job_ids:ids,...(direction?{direction}:{})});
    const outcomes={};for(const item of result.items)outcomes[item.outcome]=(outcomes[item.outcome]||0)+1;
    message(Object.entries(outcomes).map(([s,n])=>`${n} ${s.replaceAll('_',' ')}`).join(' · ')||'No jobs changed.');
    selection.clear();version++;await load();
  }catch(error){message(error.message,true);}finally{mutating=false;controls();}
}
function current(){
  const j=overview.current;
  $('.job-name').textContent=j?`${j.recording_name} · ${label(j.kind)}`:overview.worker_online?'No active job':'Worker offline';
  stateText.textContent=j?(j.control_state==='none'?label(j.state):label(j.control_state))+(overview.worker_online?'':' · Worker offline'):'';
  $('#job-elapsed').textContent=UI.duration(j?.elapsed_ms);
  estimate.textContent=j?.estimate?.status==='available'?UI.duration(j.estimate.estimated_total_ms):j?.estimate?.status==='exceeded'?'Estimate exceeded':'Unavailable';
  $('#job-progress').hidden=!j;$('#job-progress').setAttribute('aria-label',j?`${label(j.kind)}: ${stateText.textContent}; progress unavailable`:'No active job');
  const resume=j?.allowed_controls.includes('resume');pause.title=resume?'Resume processing':'Pause processing';pause.setAttribute('aria-label',pause.title);pause.querySelector('path').setAttribute('d',resume?'M7 4 20 12 7 20Z':'M8 5v14M16 5v14');
  for(const [id,count] of Object.entries({queue:overview.queued_count,failures:overview.failed_count,history:overview.succeeded_count,canceled:overview.canceled_count}))$(`#${id}-count`).textContent=count;
}
function render(){
  const key=JSON.stringify([activeTab,items.map(j=>[j.id,j.state,j.control_state,j.queue_position,j.queue_estimate?.status,j.queue_estimate?.ready_in_ms]),[...selection]]);
  if(key!==signature){
    signature=key;
    const body=$('#jobs-body');const restoreFocus=UI.rememberFocus(body);body.replaceChildren();
    for(const j of items){
      const tr=el('tr');tr.classList.toggle('is-selected',selection.has(j.id));const td=el('td',null,'checkbox-cell'),check=el('input');check.type='checkbox';check.checked=selection.has(j.id);check.disabled=!['queue','failures'].includes(activeTab);check.setAttribute('aria-label',`Select job ${j.id}`);
      check.addEventListener('change',()=>{check.checked?selection.add(j.id):selection.delete(j.id);tr.classList.toggle('is-selected',check.checked);controls();});td.append(check);tr.append(td);
      const name=el('td');name.append(button(`${j.queue_position?j.queue_position+'. ':''}${j.recording_name}`,()=>UI.openRecording(j.recording_id),'recording-link'));tr.append(name);
      const time=activeTab==='queue'?j.queued_at:j.finished_at;
      const state=activeTab==='queue'?(j.queue_estimate?.status==='available'?'≈ '+UI.duration(j.queue_estimate.ready_in_ms):'Estimate unavailable'):activeTab==='failures'?(j.diagnostic?.message||'Failed'):label(j.state);
      const status=el('td',state);status.title=state;
      tr.append(el('td',UI.date(time)),status,el('td',label(j.kind)));body.append(tr);
    }
    restoreFocus();
    if(!items.length){const tr=el('tr'),td=el('td',`No ${activeTab==='failures'?'failed jobs':activeTab==='queue'?'queued jobs':activeTab==='history'?'completed jobs':'canceled jobs'}.`);td.colSpan=5;tr.append(td);body.append(tr);}
  }
  summary.textContent=`${selection.size?selection.size+' selected · ':''}${items.length} jobs${more?' · Scroll for more':''}`;
  controls();
}
async function load(){
  const ticket=version,view=views[activeTab];
  const result=await request('/api/v1/processing/overview');
  let cursor=null,rows=[];
  do{
    const page=await request(`/api/v1/processing/jobs?view=${view}&limit=100${cursor?'&cursor='+encodeURIComponent(cursor):''}`);
    rows.push(...page.items);cursor=page.next_cursor;
  }while(cursor&&rows.length<loaded);
  if(ticket!==version)return;
  overview=result;items=rows;more=Boolean(cursor);
  for(const id of selection)if(!items.some(j=>j.id===id))selection.delete(id);
  current();render();
}
tabs.forEach((tab,index)=>{
  tab.addEventListener('click',()=>{
    activeTab=tab.dataset.tab;version++;loaded=100;selection.clear();
    tabs.forEach(t=>{t.setAttribute('aria-selected',String(t===tab));t.tabIndex=t===tab?0:-1;});
    $('#jobs-panel').setAttribute('aria-labelledby',tab.id);$('#job-date-heading').textContent=activeTab==='queue'?'Queued':'Finished';$('#job-state-heading').textContent=activeTab==='queue'?'Est. ready in':activeTab==='failures'?'Reason':'Status';
    items=[];render();load().catch(e=>message(e.message,true));
  });
  tab.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length;tabs[next].click();tabs[next].focus();});
});
selectAll.addEventListener('change',()=>{selection=new Set(selectAll.checked?items.map(j=>j.id):[]);render();});
async function single(b,operation){
  const id=overview?.current?.id;if(!id||mutating)return;
  mutating=true;controls();try{await request(`/api/v1/processing/jobs/${id}/${operation}`,{});version++;await load();}catch(e){message(e.message,true);}finally{mutating=false;controls();}
}
pause.addEventListener('click',()=>single(pause,overview?.current?.allowed_controls.includes('resume')?'resume':'pause'));
cancel.addEventListener('click',()=>single(cancel,'cancel'));
$('#jobs-panel').addEventListener('scroll',()=>{const host=$('#jobs-panel');if(more&&host.scrollTop+host.clientHeight>=host.scrollHeight-50){loaded+=100;more=false;refresh();}});
const refresh=UI.poll(load,1500);refresh();
