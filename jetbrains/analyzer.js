'use strict';
const {$,el,label,request,message,button}=UI;
const detailsToggle=$('.details-toggle'),detailsPanel=$('#recording-details'),workspace=$('.analyzer-workspace');
detailsToggle.addEventListener('click',()=>{const visible=detailsPanel.hidden;detailsPanel.hidden=!visible;workspace.classList.toggle('details-hidden',!visible);detailsToggle.classList.toggle('selected',visible);detailsToggle.setAttribute('aria-expanded',String(visible));detailsToggle.setAttribute('aria-label',`${visible?'Hide':'Show'} recording details`);detailsToggle.title=detailsToggle.getAttribute('aria-label');});
const canvas=$('#imu-graph'),context=canvas.getContext('2d'),play=$('#graph-play'),metric=$('#graph-metric'),zoomIn=$('#graph-zoom-in'),zoomOut=$('#graph-zoom-out');
let recording=null,manifest=null,samples=[],duration=0,playhead=0,windowSeconds=12,playing=false,previous=0,frame=0,plot=null,loadedIdentity=null,metadataSignature='',loading=false;
const videos=[];
const graphEmpty=el('div','Select a recording from Recordings.','graph-empty');$('.graph-content').append(graphEmpty);
const timeline=el('div',null,'timeline'),position=el('span','0:00'),endLabel=el('span','0:00'),seek=el('input');seek.type='range';seek.min='0';seek.max='0';seek.step='.001';seek.value='0';seek.setAttribute('aria-label','Recording time');timeline.append(position,seek,endLabel);$('.velocity-panel').append(timeline);
canvas.tabIndex=0;canvas.setAttribute('aria-label','IMU graph. Left and right arrows seek; Home and End go to recording boundaries; Space toggles playback.');
function setPlaying(value){
  playing=value&&duration>0;play.setAttribute('aria-label',playing?'Pause':'Play');play.title=playing?'Pause':'Play';play.setAttribute('aria-pressed',String(playing));$('#play-shape').setAttribute('d',playing?'M7 4V20M17 4V20':'M7 4 20 12 7 20Z');
  cancelAnimationFrame(frame);previous=0;sync();if(playing)frame=requestAnimationFrame(tick);
}
function tick(now){if(!playing)return;if(previous)playhead=Math.min(duration,playhead+(now-previous)/1000);previous=now;draw();sync();if(playhead>=duration)setPlaying(false);else frame=requestAnimationFrame(tick);}
function go(time){playhead=Math.max(0,Math.min(duration,time));previous=0;draw();sync(true);}
function sync(explicit=false){
  position.textContent=UI.duration(playhead*1000);seek.value=String(playhead);
  for(const consumer of videos){
    const {video,empty,start,end}=consumer;
    const covered=Timeline.inside(playhead,start,end)&&!consumer.failed;
    video.hidden=!covered;empty.hidden=covered;
    if(!covered){video.pause();empty.textContent=consumer.failed?'Camera could not be loaded. Refresh to retry.':'Outside camera coverage';continue;}
    if(video.readyState<1)continue;
    const target=Math.max(0,Math.min(video.duration,playhead-start));
    const drift=Math.abs(video.currentTime-target);
    if(explicit||(!video.seeking&&video.readyState>=2&&drift>.1)){
      if(!video.seeking || explicit)video.currentTime=target;
    }
    if(playing&&video.paused&&!consumer.playPending){consumer.playPending=true;video.play().catch(()=>{consumer.failed=true;}).finally(()=>consumer.playPending=false);}
    if(!playing&&!video.paused)video.pause();
  }
}
function selectedSeries(){return manifest?.series.find(s=>s.id===metric.value);}
function draw(){
  const series=selectedSeries();canvas.hidden=!series||!samples.length;graphEmpty.hidden=!canvas.hidden;if(canvas.hidden)return;
  const {width,height}=canvas.getBoundingClientRect();if(!width||!height)return;
  const ratio=window.devicePixelRatio||1;canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);context.setTransform(ratio,0,0,ratio,0,0);context.clearRect(0,0,width,height);
  zoomIn.disabled=!samples.length||windowSeconds<=Math.min(1.5,duration);zoomOut.disabled=!samples.length||windowSeconds>=duration;
  const rem=parseFloat(getComputedStyle(document.documentElement).fontSize),pad=2*rem,top=2.1*rem,bottom=height-2*rem,right=width-pad;if(bottom<=top||right<=pad)return;
  const span=Math.max(.001,windowSeconds),start=Math.max(0,Math.min(Math.max(0,duration-span),playhead-span/2));
  let low=series.minimum_value??-1,high=series.maximum_value??1;if(high===low){high+=1;low-=1;}
  const x=t=>pad+(t-start)/span*(right-pad),y=v=>top+(high-v)/(high-low)*(bottom-top);
  plot={pad,right,start,span};context.font=`${Math.max(10,.72*rem)}px Menlo,Consolas,monospace`;context.lineWidth=1;context.strokeStyle='#2c3035';
  for(const line of [top,(top+bottom)/2,bottom]){context.beginPath();context.moveTo(pad,line);context.lineTo(right,line);context.stroke();}
  context.save();context.beginPath();context.rect(pad,top,right-pad,bottom-top);context.clip();context.beginPath();
  let connected=false;
  for(const row of samples){const t=UI.seconds(row[0]),v=row[series.column_index];if(v===null){connected=false;continue;}if(t<start||t>start+span){connected=false;continue;}if(connected)context.lineTo(x(t),y(v));else context.moveTo(x(t),y(v));connected=true;}
  context.strokeStyle='#c0c4ca';context.lineWidth=1.3;context.stroke();
  const covered=Timeline.inside(playhead,UI.seconds(manifest.coverage_start_ns),UI.seconds(manifest.coverage_end_ns));
  const value=covered?Timeline.lookup(samples,BigInt(Math.round(playhead*1e9)),series.column_index):null;
  context.strokeStyle='#c9cdd3';context.beginPath();context.moveTo(x(playhead),top);context.lineTo(x(playhead),bottom);context.stroke();
  if(value!==null){context.beginPath();context.arc(x(playhead),y(value),3,0,Math.PI*2);context.fillStyle='#111214';context.fill();context.stroke();}context.restore();
  context.fillStyle='#858c96';context.textAlign='left';context.fillText(high.toFixed(2),pad,top-.45*rem);context.fillText(low.toFixed(2),pad,bottom-.4*rem);
  context.fillStyle='#a8aeb8';context.fillText(Timeline.unixLabel(recording.start_time_ns||'0',playhead),pad,height-.65*rem);context.textAlign='right';
  context.fillText(value===null?'No sample':`${value.toFixed(4)} ${series.units}`,right,top-.45*rem);context.fillStyle='#858c96';context.fillText(Timeline.unixLabel(recording.start_time_ns||'0',start+span),right,height-.65*rem);
}
function details(){
  const host=$('.details-content');host.replaceChildren();
  const section=title=>{const s=el('section',null,'details-section');s.append(el('h2',title));host.append(s);return s;};
  const info=section('Recording info'),dl=el('dl');info.append(dl);
  for(const [name,value] of [['Name',recording.name],['Recorded',UI.recorded(recording.start_time_ns)],['Duration',UI.duration(duration*1000)],['Source size',UI.size(recording.total_source_size_bytes)],['Storage',recording.storage_format],['Messages',recording.message_count],['Topics',recording.topic_count],['Source health',label(recording.presentation_health)]]){const row=el('div');row.append(el('dt',name),el('dd',value??'Unavailable'));dl.append(row);}
  const outputs=section('Analysis outputs');for(const o of recording.outputs){const item=el('div',null,'detail-item'),row=el('div');row.append(el('span',label(o.kind)),el('span',label(o.state)));item.append(row);if(o.artifact)item.append(el('div',UI.size(o.artifact.size_bytes)));if(o.diagnostic)item.append(el('div',o.diagnostic.message));outputs.append(item);}
  const components=section('Source components');for(const c of recording.components){const item=el('div',null,'detail-item'),row=el('div');row.append(el('span',c.file_name||c.role),el('span',UI.size(c.size_bytes)));item.append(row,el('div',label(c.condition)));components.append(item);}
  if(recording.diagnostic)host.append(el('p',recording.diagnostic.message,'details-note'));
  const refresh=button('Refresh recording',()=>load(true));host.append(refresh);
}
function camera(kind,selector){
  const host=$(selector);host.replaceChildren();const output=recording.outputs.find(o=>o.kind===kind);
  const empty=el('div',null,'preview-empty');host.append(empty);
  if(output?.state!=='ready'||!output.artifact){empty.append(el('strong',label(output?.state)),el('p',output?.diagnostic?.message||'Prepare this recording on Recordings, then follow its jobs in Processing.'));return;}
  const artifact=output.artifact;
  const expected=`/api/recordings/${recording.id}/${kind.replaceAll('_','-')}/media/${artifact.id}`;
  if(artifact.url!==expected){empty.textContent='Invalid camera artifact URL.';return;}
  const video=el('video');video.muted=true;video.playsInline=true;video.preload='auto';video.src=UI.apiURL(artifact.url);video.setAttribute('aria-label',label(kind));host.append(video);
  if(document.querySelector('.experiment-badge'))host.append(el('span','Synthetic camera test pattern','media-caption'));
  const consumer={video,empty,start:UI.seconds(artifact.coverage_start_ns),end:UI.seconds(artifact.coverage_end_ns),failed:false};videos.push(consumer);
  video.addEventListener('loadedmetadata',()=>sync(true));video.addEventListener('canplay',()=>sync());video.addEventListener('error',()=>{consumer.failed=true;sync();});
}
async function load(force=false){
  if(loading)return;loading=true;
  try{
    const raw=new URLSearchParams(location.search).get('id');
    if(!raw||! /^[1-9]\d*$/.test(raw)||!Number.isSafeInteger(Number(raw)))throw new Error('Choose a recording on the Recordings screen to open Analyzer.');
    const next=await request(`/api/v1/recordings/${raw}`);recording=next;sessionStorage.setItem('tectrace-recording',String(next.id));
    duration=UI.seconds(next.duration_ns);seek.max=String(duration);seek.disabled=duration<=0;endLabel.textContent=UI.duration(duration*1000);play.disabled=duration<=0;
    const meta=JSON.stringify(next);if(meta!==metadataSignature){metadataSignature=meta;details();}
    const identity=JSON.stringify(next.outputs.map(o=>[o.kind,o.state,o.artifact?.id]));
    if(force||identity!==loadedIdentity){
      loadedIdentity=identity;setPlaying(false);playhead=Math.min(playhead,duration);windowSeconds=duration;
      for(const c of videos){c.video.pause();c.video.removeAttribute('src');c.video.load();}videos.length=0;
      camera('front_preview','.front-preview');camera('topdown_preview','.top-preview');samples=[];manifest=null;metric.replaceChildren();
      const imu=await request(`/api/recordings/${next.id}/imu-series`);
      if(imu.state==='ready'&&imu.artifact){
        const expected=`/api/recordings/${next.id}/imu-series/data/${next.outputs.find(o=>o.kind==='imu_series').artifact?.id}`;
        if(imu.artifact.data_url!==expected)throw new Error('Invalid IMU artifact URL.');
        const payload=await request(imu.artifact.data_url);samples=Timeline.validate(payload);manifest=imu.artifact;
        for(const s of manifest.series){if(!s.available||!Number.isInteger(s.column_index)||s.column_index<1||s.column_index>6)continue;const option=el('option',s.component);option.value=s.id;metric.append(option);}
        metric.value=manifest.default_series_id;if(!metric.value&&metric.options.length)metric.selectedIndex=0;
        graphEmpty.textContent=samples.length?'No available IMU series.':'No IMU samples.';
      }else graphEmpty.textContent=`IMU: ${label(imu.state)}. ${imu.diagnostic?.message||'Prepare this recording from Recordings.'}`;
      metric.disabled=!samples.length;draw();sync(true);
    }
  }catch(error){loadedIdentity=null;setPlaying(false);message(error.message,true);if(!recording){$('.details-content').replaceChildren(el('p',error.message,'details-note'));play.disabled=seek.disabled=metric.disabled=true;}else{graphEmpty.textContent=error.message;draw();}}
  finally{loading=false;}
}
play.addEventListener('click',()=>{if(playhead>=duration)playhead=0;setPlaying(!playing);});
metric.addEventListener('change',draw);zoomIn.addEventListener('click',()=>{windowSeconds=Math.max(Math.min(1.5,duration),windowSeconds/2);draw();});zoomOut.addEventListener('click',()=>{windowSeconds=Math.min(duration,windowSeconds*2);draw();});
$('#graph-reset').addEventListener('click',()=>{setPlaying(false);windowSeconds=duration;go(0);});
seek.addEventListener('input',()=>go(Number(seek.value)));
canvas.addEventListener('click',event=>{if(plot)go(plot.start+Math.max(0,Math.min(1,(event.clientX-canvas.getBoundingClientRect().left-plot.pad)/(plot.right-plot.pad)))*plot.span);});
canvas.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End',' '].includes(event.key))return;event.preventDefault();if(event.key===' ')setPlaying(!playing);else go(event.key==='Home'?0:event.key==='End'?duration:playhead+(event.key==='ArrowRight'?1:-1)*(event.shiftKey?1:.1));});
const help=$('[aria-label="Graph help"]');help.title='Graph help';help.addEventListener('click',()=>{const d=UI.dialog('Graph controls');d.content.append(el('p','Play and seek use one recording clock for both cameras and the graph. Click the graph or drag the timeline to seek. Use + and − to change the graph window; Reset returns to the full recording.'),el('p','On the focused graph: Left/Right seek 100 ms; Shift seeks 1 s; Home/End go to the boundaries; Space plays or pauses. Null IMU values are gaps. Cameras disappear outside their measured coverage.'));d.show();});
new ResizeObserver(draw).observe(canvas);document.addEventListener('visibilitychange',()=>{if(document.hidden)setPlaying(false);});window.addEventListener('pagehide',()=>setPlaying(false));
const refresh=UI.poll(()=>load(),2000);draw();refresh();
