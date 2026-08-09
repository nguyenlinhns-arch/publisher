(function(){
  'use strict';
  const CONFIG=Object.assign({
    FORM_ENDPOINT:'',
    GA4_MEASUREMENT_ID:'',
    GOOGLE_ADS_ID:'',
    GOOGLE_ADS_CONVERSION_LABEL:''
  },window.HLX_CONFIG||{});
  const STORAGE_KEY='hlxqn_attribution_v1';
  const ATTR_KEYS=['utm_source','utm_medium','utm_campaign','utm_term','utm_content','gclid','gbraid','wbraid'];

  function safeStore(k,v){try{localStorage.setItem(k,v)}catch(e){}}
  function safeRead(k){try{return localStorage.getItem(k)}catch(e){return null}}
  function uuid(){try{return crypto.randomUUID()}catch(e){return 'lead-'+Date.now()+'-'+Math.random().toString(36).slice(2,10)}}
  function readAttribution(){
    let stored={};
    try{stored=JSON.parse(safeRead(STORAGE_KEY)||'{}')||{}}catch(e){}
    const params=new URLSearchParams(location.search);
    let changed=false;
    ATTR_KEYS.forEach(function(k){const v=params.get(k);if(v){stored[k]=v;changed=true}});
    if(changed||!stored.first_landing){
      if(!stored.first_landing)stored.first_landing=location.href;
      stored.last_landing=location.href;
      stored.saved_at=Date.now();
      safeStore(STORAGE_KEY,JSON.stringify(stored));
    }
    return stored;
  }
  readAttribution();

  window.dataLayer=window.dataLayer||[];
  function gtag(){window.dataLayer.push(arguments)}
  window.gtag=window.gtag||gtag;

  function loadGoogleTag(){
    const id=CONFIG.GA4_MEASUREMENT_ID||CONFIG.GOOGLE_ADS_ID;
    if(!id)return;
    const s=document.createElement('script');
    s.async=true;
    s.src='https://www.googletagmanager.com/gtag/js?id='+encodeURIComponent(id);
    document.head.appendChild(s);
    gtag('js',new Date());
    if(CONFIG.GA4_MEASUREMENT_ID)gtag('config',CONFIG.GA4_MEASUREMENT_ID,{send_page_view:true});
    if(CONFIG.GOOGLE_ADS_ID)gtag('config',CONFIG.GOOGLE_ADS_ID);
  }
  loadGoogleTag();

  function event(name,params){
    params=params||{};
    window.dataLayer.push(Object.assign({event:name},params));
    if(CONFIG.GA4_MEASUREMENT_ID||CONFIG.GOOGLE_ADS_ID){try{gtag('event',name,params)}catch(e){}}
  }

  function vnPhoneToE164(phone){
    const p=String(phone||'').replace(/\D/g,'');
    if(/^0\d{9,10}$/.test(p))return '+84'+p.slice(1);
    if(/^84\d{9,10}$/.test(p))return '+'+p;
    return p?('+'+p):'';
  }

  function buildLead(data){
    const a=readAttribution();
    return Object.assign({},data,{
      lead_id:data.lead_id||uuid(),
      source:data.source||a.utm_source||'Website',
      landing_page:location.href,
      utm_source:a.utm_source||'',
      utm_medium:a.utm_medium||'',
      utm_campaign:a.utm_campaign||'',
      utm_term:a.utm_term||'',
      utm_content:a.utm_content||'',
      gclid:a.gclid||'',
      gbraid:a.gbraid||'',
      wbraid:a.wbraid||'',
      referrer:document.referrer||'',
      user_agent:navigator.userAgent||''
    });
  }

  async function submitLead(data){
    const payload=buildLead(data);
    event('generate_lead_intent',{
      lead_id:payload.lead_id,
      license:payload.license||'',
      area:payload.area||'',
      utm_campaign:payload.utm_campaign||'',
      gclid_present:payload.gclid?'yes':'no'
    });
    if(!CONFIG.FORM_ENDPOINT){
      safeStore('hlxqn_pending_lead',JSON.stringify(payload));
      return {dispatched:false,payload:payload};
    }
    try{
      await fetch(CONFIG.FORM_ENDPOINT,{
        method:'POST',
        mode:'no-cors',
        keepalive:true,
        headers:{'Content-Type':'text/plain;charset=UTF-8'},
        body:JSON.stringify(payload)
      });
      if(CONFIG.GOOGLE_ADS_ID&&CONFIG.GOOGLE_ADS_CONVERSION_LABEL){
        const phone=vnPhoneToE164(payload.phone);
        if(phone)gtag('set','user_data',{phone_number:phone});
        gtag('event','conversion',{send_to:CONFIG.GOOGLE_ADS_ID+'/'+CONFIG.GOOGLE_ADS_CONVERSION_LABEL});
      }
      event('generate_lead',{
        lead_id:payload.lead_id,
        license:payload.license||'',
        area:payload.area||'',
        utm_campaign:payload.utm_campaign||''
      });
      try{localStorage.removeItem('hlxqn_pending_lead')}catch(e){}
      return {dispatched:true,payload:payload};
    }catch(err){
      safeStore('hlxqn_pending_lead',JSON.stringify(payload));
      event('lead_submit_error',{lead_id:payload.lead_id});
      return {dispatched:false,payload:payload,error:err};
    }
  }

  document.addEventListener('click',function(e){
    const a=e.target.closest&&e.target.closest('a');
    if(!a)return;
    const href=a.getAttribute('href')||'';
    if(href.indexOf('tel:')===0)event('phone_click',{link_url:href});
    if(href.indexOf('zalo.me/')!==-1)event('zalo_click',{link_url:href});
  },true);

  window.LaiXeTracking={config:CONFIG,event:event,getAttribution:readAttribution,buildLead:buildLead,submitLead:submitLead};
})();
