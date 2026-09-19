'use strict';
// Only serve.py injects this module. Omit it when porting the frontend.
(async () => {
  try {
    const result=await fetch('/__experiment'); if(!result.ok)return;
    const info=await result.json(); if(!info.synthetic)return;document.documentElement.classList.add('synthetic-experiment');
    const badge=document.createElement('span'); badge.className='experiment-badge'; badge.textContent='Synthetic experiment'; document.querySelector('.techtrace-brand').after(badge);
    document.addEventListener('experiment-settings',({detail:d})=>{
      d.content.append(UI.el('hr'),UI.el('h3','Synthetic scenarios'),UI.el('p','Changes reset this experiment’s invented catalog and jobs for all local tabs.'));
      const choices=UI.el('div',null,'scenario-choices');
      for(const name of info.scenarios){
        const b=UI.button(name,()=>UI.action(b,async()=>{
          const response=await fetch('/__experiment/scenario',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario:name})});
          if(!response.ok)throw new Error('Could not change scenario.');
          location.reload();
        }));
        b.setAttribute('aria-pressed',String(name===info.scenario)); choices.append(b);
      }
      d.content.append(choices);
    });
  } catch { /* Experiment controls are absent on the real backend. */ }
})();
