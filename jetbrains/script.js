const workspace = document.querySelector('.workspace');
const foldersToggle = document.querySelector('.folders-toggle');
const foldersRailToggle = document.querySelector('.folders-rail-toggle');
const divider = document.querySelector('.panel-divider');
let foldersVisible = true;

function setFoldersVisible(visible) {
  foldersVisible = visible;
  workspace.classList.toggle('folders-hidden', !visible);
  foldersRailToggle.classList.toggle('active', visible);
  foldersRailToggle.setAttribute('aria-expanded', String(visible));
  if (!visible) foldersRailToggle.focus();
}
foldersToggle.addEventListener('click', () => setFoldersVisible(false));
foldersRailToggle.addEventListener('click', () => setFoldersVisible(!foldersVisible));

function setFoldersWidth(percent) {
  const width = Math.max(15, Math.min(55, percent));
  workspace.style.setProperty('--folders-width', `${width}%`);
  divider.setAttribute('aria-valuenow', String(Math.round(width)));
}
let dragPointer = null;
divider.addEventListener('pointerdown', event => {
  if (event.button !== 0) return;
  event.preventDefault();
  dragPointer = event.pointerId;
  divider.setPointerCapture(dragPointer);
  workspace.classList.add('is-resizing');
});
divider.addEventListener('pointermove', event => {
  if (dragPointer !== event.pointerId) return;
  const bounds = workspace.getBoundingClientRect();
  setFoldersWidth((event.clientX - bounds.left) / bounds.width * 100);
});
function finishResize() {
  dragPointer = null;
  workspace.classList.remove('is-resizing');
}
divider.addEventListener('pointerup', finishResize);
divider.addEventListener('pointercancel', finishResize);
divider.addEventListener('lostpointercapture', finishResize);
divider.addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const current = document.querySelector('.project-panel').getBoundingClientRect().width / workspace.getBoundingClientRect().width * 100;
  setFoldersWidth(event.key === 'Home' ? 15 : event.key === 'End' ? 55 : current + (event.key === 'ArrowRight' ? 1 : -1));
});


const {$,el,label,request,message,button,action,dialog} = UI;
let catalogVersion=0;
let catalog = null, selectedFolder = '', folderSignature = '', rowSignature = '';
const selected = new Set(), collapsed = new Set();
const search=$('#recording-search'),status=$('#status-filter'),health=$('#health-filter'),body=$('#recordings-body'),selectAll=$('#select-all-recordings'),prepare=$('#prepare-selected');
function options(select,items){ select.replaceChildren(...items.map(([value,text])=>{const o=el('option',text);o.value=value;return o;})); }
options(status,[['','All statuses'],...['ready','processing','queued','failed','not_planned'].map(s=>[s,label(s)])]);
options(health,[['','All health'],['readable','Readable'],['damaged','Damaged']]);
let visible=[];
function selection(){
  const eligible=visible.filter(r=>r.presentation_health==='readable');
  const count=eligible.filter(r=>selected.has(r.id)).length;
  selectAll.checked=count>0&&count===eligible.length;
  selectAll.indeterminate=count>0&&count<eligible.length;
  selectAll.disabled=!eligible.length;
  prepare.hidden=!selected.size;
  prepare.title=`Prepare ${selected.size} selected recording(s)`;
}
function renderRows(force=false){
  if(!catalog)return;
  const query=search.value.trim().toLowerCase();
  visible=catalog.recordings.filter(r=>(!selectedFolder||r.folder_path===selectedFolder||r.folder_path.startsWith(selectedFolder+'/'))&&(!query||(r.name+' '+r.folder_path).toLowerCase().includes(query))&&(!status.value||status.value===r.analysis_state)&&(!health.value||health.value===r.presentation_health));
  const signature=JSON.stringify([visible,[...selected]]);
  if(!force&&signature===rowSignature)return;
  rowSignature=signature;
  const restoreFocus=UI.rememberFocus(body);body.replaceChildren();
  for(const r of visible){
    const tr=el('tr');tr.classList.toggle('is-selected',selected.has(r.id));
    const cell=el('td',null,'checkbox-cell'),check=el('input');check.type='checkbox';check.checked=selected.has(r.id);check.disabled=r.presentation_health!=='readable';check.setAttribute('aria-label',`Select ${r.name}`);
    check.addEventListener('change',()=>{check.checked?selected.add(r.id):selected.delete(r.id);tr.classList.toggle('is-selected',check.checked);selection();});cell.append(check);tr.append(cell);
    const nameCell=el('td');const link=button(r.name,()=>UI.openRecording(r.id),'recording-link');link.title=r.folder_path+'/'+r.name;nameCell.append(link);tr.append(nameCell);
    tr.append(el('td',UI.recorded(r.start_time_ns),'recorded-date'),el('td',r.duration_ns==null?'Unavailable':UI.duration(UI.seconds(r.duration_ns)*1000),'numeric'),el('td',UI.size(r.total_source_size_bytes),'numeric'));
    const stateCell=el('td',label(r.analysis_state),'recording-status');stateCell.tabIndex=0;stateCell.dataset.focusKey='status-'+r.id;stateCell.title=r.outputs.map(o=>`${label(o.kind)}: ${label(o.state)}${o.diagnostic?' — '+o.diagnostic.message:''}`).join('\n');
    const healthCell=el('td',label(r.presentation_health),'recording-health');healthCell.title=r.diagnostic?.message||label(r.ros_health);
    tr.append(stateCell,healthCell);body.append(tr);
  }
  restoreFocus();
  $('#recordings-empty').hidden=visible.length!==0;
  $('#recordings-empty strong').textContent=catalog.recordings.length?'No matching recordings':'No recordings';
  $('#recordings-empty span').textContent='Try another search or clear the filters.';
  selection();
}
function renderFolders(force=false){
  const signature=JSON.stringify([catalog.folders,[...collapsed],selectedFolder]);
  if(!force&&signature===folderSignature)return; folderSignature=signature;
  const host=$('#folder-list');const restoreFocus=UI.rememberFocus(host);host.replaceChildren();
  function row(path,name,depth,count,children){
    const line=el('div',null,'tree-row folder-row');line.style.setProperty('--folder-depth',depth);line.classList.toggle('highlighted',path===selectedFolder);
    const disclosure=button(children.length?(collapsed.has(path)?'›':'⌄'):'',()=>{collapsed.has(path)?collapsed.delete(path):collapsed.add(path);renderFolders();},'folder-disclosure');
    disclosure.disabled=!children.length;disclosure.setAttribute('aria-label',`${collapsed.has(path)?'Expand':'Collapse'} ${name}`);if(children.length)disclosure.setAttribute('aria-expanded',String(!collapsed.has(path)));
    const select=button('',()=>{selectedFolder=path;renderFolders();renderRows();},'folder-select');select.setAttribute('aria-pressed',String(path===selectedFolder));
    const icon=document.createElementNS('http://www.w3.org/2000/svg','svg'),use=document.createElementNS(icon.namespaceURI,'use');use.setAttribute('href','#folder');icon.setAttribute('aria-hidden','true');icon.append(use);
    select.append(icon,el('span',name),el('small',String(count),'folder-count'));line.append(disclosure,select);host.append(line);
    if(!collapsed.has(path))for(const f of children)row(f.path,f.name,depth+1,f.descendant_recording_count,catalog.folders.filter(c=>c.parent_path===f.path));
  }
  row('','All recordings',0,catalog.recordings.length,catalog.folders.filter(f=>f.parent_path===''));
  restoreFocus();
}
async function load(){
  const ticket=++catalogVersion;
  let next;
  try { next=await request('/api/v1/catalog'); } catch(error) {
    if(!catalog){
      $('#folder-list').textContent='Catalog unavailable';
      $('#last-scan-time').textContent='Unavailable';
      $('#recordings-empty').hidden=false;
      $('#recordings-empty strong').textContent='Catalog unavailable';
      $('#recordings-empty span').textContent='Use Settings → Refresh view to retry.';
    }
    throw error;
  }
  if(ticket!==catalogVersion)return;
  catalog=next;
  for(const id of selected)if(!catalog.recordings.some(r=>r.id===id&&r.presentation_health==='readable'))selected.delete(id);
  if(selectedFolder&&!catalog.folders.some(f=>f.path===selectedFolder))selectedFolder='';
  const time=$('#last-scan-time');time.dateTime=catalog.scan.completed_at||'';time.textContent=UI.date(catalog.scan.completed_at);
  renderFolders();renderRows();
}
search.addEventListener('input',()=>renderRows());status.addEventListener('change',()=>renderRows());health.addEventListener('change',()=>renderRows());
selectAll.addEventListener('change',()=>{for(const r of visible)if(r.presentation_health==='readable')selectAll.checked?selected.add(r.id):selected.delete(r.id);renderRows(true);});
$('#reset-filters').addEventListener('click',()=>{search.value=status.value=health.value='';renderRows();});
const scan=$('#scan-retry');scan.title='Rescan';scan.setAttribute('aria-label','Rescan');
scan.addEventListener('click',()=>action(scan,async()=>{await request('/api/v1/catalog/rescan',{});await load();message('Scan complete.');}));
prepare.addEventListener('click',()=>{
  const ids=[...selected];if(!ids.length)return;
  if(ids.length>100){message('Select at most 100 recordings per preparation request.',true);return;}
  const d=dialog(`Prepare ${ids.length} recording${ids.length===1?'':'s'}`);
  d.content.append(el('p','Choose the outputs to prepare. Compatible ready files and active jobs will be reused.'));
  const checks=['front_preview','topdown_preview','imu_series'].map(kind=>{const l=el('label',' '+label(kind)),c=el('input');c.type='checkbox';c.checked=true;c.value=kind;l.prepend(c);d.content.append(l);return c;});
  const submit=button('Prepare',()=>action(submit,async()=>{
    const kinds=checks.filter(c=>c.checked).map(c=>c.value);if(!kinds.length)throw new Error('Choose at least one output.');
    const result=await request('/api/v1/recordings/prepare',{recording_ids:ids,output_kinds:kinds});
    const counts={};
    for(const r of result.recordings){
      const success=r.outputs.length&&r.outputs.every(o=>['queued','retry_queued','active_reused','ready_reused'].includes(o.outcome));
      if(success)selected.delete(r.recording_id);
      for(const o of r.outputs)counts[o.outcome]=(counts[o.outcome]||0)+1;
      if(!r.outputs.length)counts[r.outcome]=(counts[r.outcome]||0)+1;
    }
    await load();d.node.close();message(Object.entries(counts).map(([outcome,count])=>`${count} ${outcome.replaceAll('_',' ')}`).join(' · '));
  }));
  checks.forEach(c=>c.addEventListener('change',()=>submit.disabled=!checks.some(c=>c.checked)));
  d.footer.append(submit);d.show();
});
const refresh=UI.poll(load,2000);refresh();
