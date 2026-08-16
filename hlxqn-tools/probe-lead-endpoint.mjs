import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..');
const config=fs.readFileSync(path.join(root,'assets/site-config.js'),'utf8');
const match=config.match(/FORM_ENDPOINT:\s*'([^']+)'/);
if(!match)throw new Error('FORM_ENDPOINT not found in site-config.js');
const endpoint=match[1];
const leadId=`healthcheck-${Date.now()}`;
const callback='__hlxHealthAck';
const url=new URL(endpoint);
url.searchParams.set('mode','status');
url.searchParams.set('lead_id',leadId);
url.searchParams.set('phone','0399999999');
url.searchParams.set('callback',callback);

try{
  const response=await fetch(url,{redirect:'follow',headers:{'user-agent':'hoclaixequangninh-health-probe/1.0'}});
  const text=await response.text();
  const jsonpPrefix=`${callback}(`;
  let mode='unknown';
  let payload=null;
  if(text.trim().startsWith(jsonpPrefix)){
    mode='jsonp-status';
    const body=text.trim().slice(jsonpPrefix.length).replace(/\);?\s*$/,'');
    try{payload=JSON.parse(body)}catch(_){payload={parse_error:true,raw:body.slice(0,300)}}
  }else{
    try{payload=JSON.parse(text);mode='json'}catch(_){payload={raw:text.slice(0,500)}}
  }
  const supportsStatus=mode==='jsonp-status'&&payload&&payload.ok===true&&Object.prototype.hasOwnProperty.call(payload,'saved');
  console.log(JSON.stringify({httpStatus:response.status,mode,supportsStatus,payload},null,2));
  // Diagnostic only. A later gate can be made strict after the live deployment capability is known.
  process.exit(0);
}catch(error){
  console.log(JSON.stringify({httpStatus:null,mode:'network-error',supportsStatus:false,error:String(error)},null,2));
  process.exit(0);
}
