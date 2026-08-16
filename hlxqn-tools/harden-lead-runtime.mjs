import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..','_site');
const p=path.join(root,'assets/site-runtime.js');
let js=fs.readFileSync(p,'utf8');

function replaceOnceOrKeep(oldText,newText,label){
  if(js.includes(newText))return;
  if(!js.includes(oldText))throw new Error(`Lead runtime hardening anchor missing: ${label}`);
  js=js.replace(oldText,newText);
}
replaceOnceOrKeep(
  'async function confirmLead(leadId){',
  'async function confirmLead(leadId,phone){',
  'confirmLead signature'
);
replaceOnceOrKeep(
  "const ack=await jsonp({mode:'status',lead_id:leadId},2200);",
  "const ack=await jsonp({mode:'status',lead_id:leadId,phone:String(phone||'')},2200);",
  'status ACK phone context'
);
replaceOnceOrKeep(
  'const ack=await confirmLead(payload.lead_id);',
  'const ack=await confirmLead(payload.lead_id,payload.phone);',
  'submitLead ACK call'
);
fs.writeFileSync(p,js);
if(!js.includes("mode:'status',lead_id:leadId,phone:"))throw new Error('Phone context missing from lead ACK');
if(!js.includes('confirmLead(payload.lead_id,payload.phone)'))throw new Error('Phone context not passed from payload');
console.log(JSON.stringify({leadAckPhoneContext:true,conversionStillAfterConfirmedAck:true,idempotent:true},null,2));
