(function(){
  'use strict';

  const CONFIG=Object.assign({
    FORM_ENDPOINT:'',
    GA4_MEASUREMENT_ID:'',
    GOOGLE_ADS_ID:'',
    GOOGLE_ADS_CONVERSION_LABEL:'',
    GOOGLE_ADS_CALL_CONVERSION_LABEL:'',
    GOOGLE_ADS_ZALO_CONVERSION_LABEL:''
  },window.HLX_CONFIG||{});

  const STORAGE_KEY='hlxqn_attribution_v1';
  const FORM_STARTED_KEY='hlxqn_form_started_v1';
  const ATTR_KEYS=['utm_source','utm_medium','utm_campaign','utm_term','utm_content','gclid','gbraid','wbraid','campaignid','adgroupid','matchtype','device','network','creative','loc_physical_ms','loc_interest_ms'];

  function safeStore(k,v){try{localStorage.setItem(k,v)}catch(e){}}
  function safeRead(k){try{return localStorage.getItem(k)}catch(e){return null}}
  function uuid(){try{return crypto.randomUUID()}catch(e){return 'lead-'+Date.now()+'-'+Math.random().toString(36).slice(2,10)}}

  function readAttribution(){
    let stored={};
    try{stored=JSON.parse(safeRead(STORAGE_KEY)||'{}')||{}}catch(e){}
    const params=new URLSearchParams(location.search);
    let changed=false;
    ATTR_KEYS.forEach(k=>{const v=params.get(k);if(v){stored[k]=v;changed=true}});
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

  function attributionParams(){
    const a=readAttribution();
    return {
      utm_source:a.utm_source||'',utm_medium:a.utm_medium||'',utm_campaign:a.utm_campaign||'',utm_term:a.utm_term||'',utm_content:a.utm_content||'',
      campaign_id:a.campaignid||'',ad_group_id:a.adgroupid||'',match_type:a.matchtype||'',device:a.device||'',network:a.network||'',creative_id:a.creative||'',
      gclid_present:a.gclid?'yes':'no',gbraid_present:a.gbraid?'yes':'no',wbraid_present:a.wbraid?'yes':'no'
    };
  }

  function event(name,params){
    params=Object.assign({},attributionParams(),params||{});
    window.dataLayer.push(Object.assign({event:name},params));
    if(CONFIG.GA4_MEASUREMENT_ID||CONFIG.GOOGLE_ADS_ID){
      try{gtag('event',name,params)}catch(e){}
    }
  }

  function fireAdsConversion(label,params){
    if(!CONFIG.GOOGLE_ADS_ID||!label)return false;
    try{
      gtag('event','conversion',Object.assign({send_to:CONFIG.GOOGLE_ADS_ID+'/'+label},params||{}));
      return true;
    }catch(e){return false}
  }

  function vnPhoneToE164(phone){
    const p=String(phone||'').replace(/\D/g,'');
    if(/^0\d{9,10}$/.test(p))return '+84'+p.slice(1);
    if(/^84\d{9,10}$/.test(p))return '+'+p;
    return p?('+'+p):'';
  }

  function classifySource(a,fallback){
    const src=String(a.utm_source||'').toLowerCase();
    const med=String(a.utm_medium||'').toLowerCase();
    if(src==='google'&&(med==='cpc'||med==='ppc'||med==='paidsearch'))return 'Google Ads';
    if(src)return a.utm_source;
    if(a.gclid||a.gbraid||a.wbraid)return 'Google Ads';
    return fallback||'Website';
  }

  function buildLead(data){
    const a=readAttribution();
    return Object.assign({},data,{
      lead_id:data.lead_id||uuid(),
      source:classifySource(a,data.source),
      landing_page:location.href,
      utm_source:a.utm_source||'',utm_medium:a.utm_medium||'',utm_campaign:a.utm_campaign||'',utm_term:a.utm_term||'',utm_content:a.utm_content||'',
      gclid:a.gclid||'',gbraid:a.gbraid||'',wbraid:a.wbraid||'',campaign_id:a.campaignid||'',ad_group_id:a.adgroupid||'',match_type:a.matchtype||'',device:a.device||'',network:a.network||'',creative_id:a.creative||'',
      physical_location_id:a.loc_physical_ms||'',interest_location_id:a.loc_interest_ms||'',referrer:document.referrer||'',user_agent:navigator.userAgent||''
    });
  }

  async function submitLead(data){
    const payload=buildLead(data);
    event('form_submit',{lead_id:payload.lead_id,license:payload.license||'',area:payload.area||'',lead_source:payload.source});
    event('generate_lead_intent',{lead_id:payload.lead_id,license:payload.license||'',area:payload.area||'',lead_source:payload.source});
    if(!CONFIG.FORM_ENDPOINT){
      event('lead_endpoint_unavailable',{lead_id:payload.lead_id});
      return {dispatched:false,payload};
    }
    try{
      await fetch(CONFIG.FORM_ENDPOINT,{method:'POST',mode:'no-cors',keepalive:true,headers:{'Content-Type':'text/plain;charset=UTF-8'},body:JSON.stringify(payload)});
      if(CONFIG.GOOGLE_ADS_ID&&CONFIG.GOOGLE_ADS_CONVERSION_LABEL){
        const phone=vnPhoneToE164(payload.phone);
        if(phone)gtag('set','user_data',{phone_number:phone});
        fireAdsConversion(CONFIG.GOOGLE_ADS_CONVERSION_LABEL,{value:1.0,currency:'VND'});
      }
      event('generate_lead',{lead_id:payload.lead_id,license:payload.license||'',area:payload.area||'',lead_source:payload.source});
      return {dispatched:true,payload};
    }catch(err){
      event('lead_submit_error',{lead_id:payload.lead_id});
      return {dispatched:false,payload,error:err};
    }
  }

  function registerFormStart(){
    document.addEventListener('focusin',function(e){
      const form=e.target&&e.target.closest&&e.target.closest('form');
      if(!form)return;
      const key=FORM_STARTED_KEY+':'+(form.id||location.pathname);
      if(safeRead(key))return;
      safeStore(key,'1');
      event('form_start',{form_id:form.id||'',page_path:location.pathname});
    },true);
  }

  document.addEventListener('click',function(e){
    const a=e.target.closest&&e.target.closest('a');
    if(!a)return;
    const href=a.getAttribute('href')||'';
    if(href.indexOf('tel:')===0){
      event('phone_click',{link_url:href});
      event('click_call',{link_url:href});
      fireAdsConversion(CONFIG.GOOGLE_ADS_CALL_CONVERSION_LABEL,{value:1.0,currency:'VND'});
    }
    if(href.indexOf('zalo.me/')!==-1){
      event('zalo_click',{link_url:href});
      event('click_zalo',{link_url:href});
      fireAdsConversion(CONFIG.GOOGLE_ADS_ZALO_CONVERSION_LABEL,{value:1.0,currency:'VND'});
    }
  },true);

  function init(){
    event('view_content',{page_path:location.pathname,page_title:document.title});
    registerFormStart();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();

  window.LaiXeTracking={config:CONFIG,event,getAttribution:readAttribution,buildLead,submitLead,fireAdsConversion};
})();
