'use strict';
// Shared client only knows the real same-origin API. Synthetic behavior is server-side.
window.UI = (() => {
  const $ = selector => document.querySelector(selector);
  const el = (tag, text, className) => { const node = document.createElement(tag); if (text != null) node.textContent = text; if (className) node.className = className; return node; };
  const labels = {front_preview:'Front camera',topdown_preview:'Top camera',imu_series:'IMU bundle',not_planned:'Not planned',not_requested:'Not requested',processing:'Processing',queued:'Queued',ready:'Ready',failed:'Failed',unavailable:'Unavailable',readable:'Readable',damaged:'Damaged',succeeded:'Completed',canceled:'Canceled',paused:'Paused'};
  const label = value => labels[value] || value || 'Unavailable';
  const seconds = ns => ns == null ? 0 : Number(BigInt(ns)) / 1e9;
  const duration = ms => ms == null ? 'Unavailable' : `${Math.floor(ms/60000)}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}`;
  const date = value => value ? new Date(value).toLocaleString('en-GB',{dateStyle:'short',timeStyle:'short'}) : 'Not scanned';
  const recorded = ns => ns == null ? 'Unavailable' : date(Number(BigInt(ns)/1000000n));
  const size = bytes => bytes == null ? 'Unavailable' : Number(bytes)<1048576 ? `${(Number(bytes)/1024).toFixed(2)} KiB` : `${(Number(bytes)/1048576).toFixed(2)} MiB`;
  function apiURL(path) {
    if (typeof path !== 'string' || !/^\/api\/(?:v1\/|recordings\/)/.test(path) || /[\\\s]/.test(path)) throw new Error('Invalid API URL.');
    const url = new URL(path,location.origin);
    if (url.origin !== location.origin || url.username || url.password) throw new Error('Invalid API URL.');
    return url.href;
  }
  async function request(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(),10000);
    try {
      const response = await fetch(apiURL(path),{method:body === undefined ? 'GET':'POST',headers:body === undefined ? {}:{'Content-Type':'application/json'},body:body === undefined ? undefined:JSON.stringify(body),signal:controller.signal,cache:'no-store'});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail?.message === 'string' ? data.detail.message : `Request failed (${response.status}).`);
      return data;
    } catch(error) {
      if (error.name === 'AbortError') throw new Error('The request timed out. Refresh to check its result before trying again.');
      if (error instanceof TypeError) throw new Error('Cannot reach the API. Check the local server and retry.');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  const notice = el('div',null,'api-notice'); notice.hidden = true; notice.setAttribute('role','status'); document.body.append(notice);
  function message(text,error=false) { notice.replaceChildren(el('span',text)); notice.classList.toggle('is-error',error); notice.hidden=false; const close=button('Dismiss',()=>notice.hidden=true); notice.append(close); }
  function button(text,fn,className='quiet-button') { const b=el('button',text,className); b.type='button'; if(fn)b.addEventListener('click',fn); return b; }
  async function action(button,fn) { if(button.disabled)return; button.disabled=true; button.setAttribute('aria-busy','true'); try { await fn(); } catch(error) { message(error.message,true); } finally { button.disabled=false; button.removeAttribute('aria-busy'); } }
  function dialog(title) {
    const d=el('dialog',null,'ide-dialog'); const heading=el('h2',title); heading.id='dialog-title'; d.setAttribute('aria-labelledby',heading.id);
    const content=el('div',null,'dialog-content'); const footer=el('div',null,'dialog-actions');
    footer.append(button('Close',()=>d.close())); d.append(heading,content,footer); document.body.append(d);
    d.addEventListener('close',()=>d.remove(),{once:true}); return {node:d,content,footer,show:()=>d.showModal()};
  }
  function openRecording(id) { if(!Number.isSafeInteger(id)||id<=0)return; sessionStorage.setItem('tectrace-recording',String(id)); location.href=`analyzer.html?id=${id}`; }
  const saved=sessionStorage.getItem('tectrace-recording');
  if(saved && /^[1-9]\d*$/.test(saved)) document.querySelectorAll('a[href="analyzer.html"]').forEach(a=>a.href=`analyzer.html?id=${saved}`);
  function poll(load,ms=1500) {
    let running=false;
    async function refresh() { if(running)return; running=true; try { await load(); } catch(error) { message(error.message,true); } finally {running=false;} }
    const timer=setInterval(()=>{if(!document.hidden && localStorage.getItem('tectrace-live')!=='false')refresh();},ms);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
    window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
    document.addEventListener('refresh-view',refresh);
    return refresh;
  }
  $('.app-settings').addEventListener('click',()=>{
    const d=dialog('Settings');
    const live=el('input'); live.type='checkbox'; live.checked=localStorage.getItem('tectrace-live')!=='false';
    live.addEventListener('change',()=>localStorage.setItem('tectrace-live',String(live.checked)));
    const l=el('label',' Live updates'); l.prepend(live); d.content.append(l,el('p','Automatically refresh catalog and processing state while this view is visible.'));
    d.footer.append(button('Refresh view',()=>{d.node.close();document.dispatchEvent(new Event('refresh-view'));}));
    document.dispatchEvent(new CustomEvent('experiment-settings',{detail:d})); d.show();
  });
  function rememberFocus(host) {
    const active=document.activeElement;
    if(!host.contains(active))return ()=>{};
    const key=active.dataset.focusKey||active.getAttribute('aria-label')||active.textContent;
    return ()=>{const next=[...host.querySelectorAll('button,input,[tabindex]')].find(n=>n.tagName===active.tagName&&(n.dataset.focusKey||n.getAttribute('aria-label')||n.textContent)===key);next?.focus({preventScroll:true});};
  }
  return {rememberFocus,$,el,label,seconds,duration,date,recorded,size,request,apiURL,message,button,action,dialog,openRecording,poll};
})();
