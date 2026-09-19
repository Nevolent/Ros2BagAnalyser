'use strict';
const Timeline = (() => {
  function validate(payload){
    if(payload?.schema_version!==2||!Array.isArray(payload.samples)||payload.samples.length>200000)throw new Error('Unsupported IMU payload.');
    let previous=null;
    for(const row of payload.samples){
      if(!Array.isArray(row)||row.length!==7||typeof row[0]!=='string'||! /^-?\d+$/.test(row[0]))throw new Error('Invalid IMU sample.');
      const time=BigInt(row[0]);if(previous!==null&&time<previous)throw new Error('IMU timestamps are not ordered.');previous=time;
      if(row.slice(1).some(v=>v!==null&&(typeof v!=='number'||!Number.isFinite(v))))throw new Error('Invalid IMU value.');
    }
    return payload.samples;
  }
  function lookup(samples,ns,column){
    let lo=0,hi=samples.length;
    while(lo<hi){const mid=(lo+hi)>>1;if(BigInt(samples[mid][0])<=ns)lo=mid+1;else hi=mid;}
    return lo===0?null:samples[lo-1][column];
  }
  function inside(time,start,end){return time>=start&&time<=end;}
  function unixLabel(epoch,seconds){const ns=BigInt(epoch)+BigInt(Math.round(seconds*1e9));return `${ns/1000000000n}.${String((ns%1000000000n)/1000000n).padStart(3,'0')} s`;}
  return {validate,lookup,inside,unixLabel};
})();
if(typeof module!=='undefined')module.exports=Timeline;
