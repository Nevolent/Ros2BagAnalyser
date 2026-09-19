const {test}=require('node:test');
const assert=require('node:assert/strict');
const T=require('./timeline.js');
test('lookup uses decimal ns, duplicate-last and per-series nulls',()=>{
  const samples=T.validate({schema_version:2,samples:[['1000000001',1,2,3,4,5,6],['1000000001',null,9,8,7,6,5],['1000000002',2,3,4,5,6,7]]});
  assert.equal(T.lookup(samples,1000000000n,1),null);
  assert.equal(T.lookup(samples,1000000001n,1),null);
  assert.equal(T.lookup(samples,1000000001n,2),9);
  assert.equal(T.lookup(samples,1000000002n,1),2);
});
test('reject malformed and unordered samples',()=>{
  assert.throws(()=>T.validate({schema_version:1,samples:[]}));
  assert.throws(()=>T.validate({schema_version:2,samples:[['2',1,2,3,4,5,6],['1',1,2,3,4,5,6]]}));
  assert.throws(()=>T.validate({schema_version:2,samples:[['0',NaN,2,3,4,5,6]]}));
});
test('measured coverage and epoch labels',()=>{
  assert.equal(T.inside(1,2,14),false);assert.equal(T.inside(14,2,14),true);assert.equal(T.inside(15,2,14),false);
  assert.equal(T.unixLabel('1772312400000000001',.001),'1772312400.001 s');
});
