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
  const CLICK_CONVERSION_KEY='hlxqn_click_conversion_v2:';
  const SESSION_ID_KEY='hlxqn_session_id_v1';
  const ATTR_TTL_MS=90*24*60*60*1000;
  const ATTR_KEYS=[
    'utm_source','utm_medium','utm_campaign','utm_term','utm_content',
    'gclid','gbraid','wbraid','campaignid','adgroupid','keyword','matchtype',
    'device','devicemodel','network','creative','targetid','placement','adposition',
    'feeditemid','extensionid','loc_physical_ms','loc_interest_ms'
  ];

  function safeStore(k,v){try{localStorage.setItem(k,v)}catch(e){}}
  function safeRead(k){try{return localStorage.getItem(k)}catch(e){return null}}
  function safeRemove(k){try{localStorage.removeItem(k)}catch(e){}}
  function safeSessionStore(k,v){try{sessionStorage.setItem(k,v)}catch(e){}}
  function safeSessionRead(k){try{return sessionStorage.getItem(k)}catch(e){return null}}
  function uuid(){try{return crypto.randomUUID()}catch(e){return 'lead-'+Date.now()+'-'+Math.random().toString(36).slice(2,10)}}
  function sessionId(){let id=safeSessionRead(SESSION_ID_KEY);if(!id){id=uuid();safeSessionStore(SESSION_ID_KEY,id)}return id}

  function readAttribution(){
    let stored={};
    try{stored=JSON.parse(safeRead(STORAGE_KEY)||'{}')||{}}catch(e){}
    if(stored.saved_at&&Date.now()-Number(stored.saved_at)>ATTR_TTL_MS){stored={};safeRemove(STORAGE_KEY)}
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
    if(document.querySelector('script[src*="googletagmanager.com/gtag/js"]'))return;
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
      campaign_id:a.campaignid||'',ad_group_id:a.adgroupid||'',keyword:a.keyword||'',match_type:a.matchtype||'',device:a.device||'',device_model:a.devicemodel||'',network:a.network||'',creative_id:a.creative||'',target_id:a.targetid||'',placement:a.placement||'',ad_position:a.adposition||'',
      gclid_present:a.gclid?'yes':'no',gbraid_present:a.gbraid?'yes':'no',wbraid_present:a.wbraid?'yes':'no'
    };
  }

  function event(name,params){
    params=Object.assign({},attributionParams(),params||{});
    if(CONFIG.GA4_MEASUREMENT_ID||CONFIG.GOOGLE_ADS_ID){
      try{gtag('event',name,params);return}catch(e){}
    }
    window.dataLayer.push(Object.assign({event:name},params));
  }

  function fireAdsConversion(label,params){
    if(!CONFIG.GOOGLE_ADS_ID||!label)return false;
    try{
      gtag('event','conversion',Object.assign({send_to:CONFIG.GOOGLE_ADS_ID+'/'+label},params||{}));
      return true;
    }catch(e){return false}
  }

  function fireClickConversionOnce(channel,label){
    const key=CLICK_CONVERSION_KEY+channel;
    if(safeSessionRead(key))return false;
    const fired=fireAdsConversion(label,{transaction_id:channel+'-'+sessionId()});
    if(fired)safeSessionStore(key,'1');
    return fired;
  }

  function delay(ms){return new Promise(function(resolve){setTimeout(resolve,ms)})}

  function jsonp(params,timeoutMs){
    return new Promise(function(resolve,reject){
      const callback='__hlxAck'+Date.now().toString(36)+Math.random().toString(36).slice(2,8);
      const script=document.createElement('script');
      const timer=setTimeout(function(){finish(new Error('ACK_TIMEOUT'))},timeoutMs||2500);
      function finish(error,value){
        clearTimeout(timer);
        try{delete window[callback]}catch(_){window[callback]=undefined}
        if(script.parentNode)script.parentNode.removeChild(script);
        if(error)reject(error);else resolve(value);
      }
      window[callback]=function(value){finish(null,value)};
      script.onerror=function(){finish(new Error('ACK_NETWORK_ERROR'))};
      const query=new URLSearchParams(Object.assign({},params,{callback:callback,t:String(Date.now())}));
      script.src=CONFIG.FORM_ENDPOINT+(CONFIG.FORM_ENDPOINT.indexOf('?')===-1?'?':'&')+query.toString();
      document.head.appendChild(script);
    });
  }

  async function confirmLead(leadId,phone){
    for(let attempt=0;attempt<12;attempt++){
      if(attempt)await delay(550);
      try{
        const ack=await jsonp({mode:'status',lead_id:leadId,phone:String(phone||'')},2200);
        if(ack&&ack.ok&&ack.saved)return ack;
      }catch(_){}
    }
    return null;
  }

  function vnPhoneToE164(phone){
    const p=String(phone||'').replace(/\D/g,'');
    if(/^0\d{9,10}$/.test(p))return '+84'+p.slice(1);
    if(/^84\d{9,10}$/.test(p))return '+'+p;
    if(/^\d{11,15}$/.test(p))return '+'+p;
    return '';
  }

  function setEnhancedConversionUserData(payload){
    if(!payload||payload.consent!==true)return false;
    const phone=vnPhoneToE164(payload.phone);
    if(!phone)return false;
    try{
      gtag('set','user_data',{phone_number:phone});
      return true;
    }catch(e){return false}
  }

  function classifySource(a,fallback){
    const src=String(a.utm_source||'').toLowerCase();
    const med=String(a.utm_medium||'').toLowerCase();
    if(src==='google'&&(med==='cpc'||med==='ppc'||med==='paidsearch'))return 'Google Ads';
    if(src)return a.utm_source;
    if(a.gclid||a.gbraid||a.wbraid)return 'Google Ads';
    return fallback||'Website';
  }

  function normalizeLicense(value){
    const raw=String(value||'').trim();
    if(/^B(?:\s|$)/i.test(raw))return 'B';
    if(/^C1(?:\s|$)/i.test(raw))return 'C1';
    if(/^D2(?:\s|$)/i.test(raw))return 'D2';
    if(/^D(?:\s|$)/i.test(raw))return 'D';
    if(/^C(?:\s|$)/i.test(raw))return 'C';
    if(/^A1(?:\s|$)/i.test(raw))return 'A1';
    return 'Cần tư vấn';
  }

  function buildLead(data){
    const a=readAttribution();
    const requestedLicense=String(data.license||'').trim();
    const normalizedLicense=normalizeLicense(requestedLicense);
    const noteParts=[String(data.note||'').trim()];
    if(requestedLicense&&requestedLicense!==normalizedLicense)noteParts.push('Lựa chọn hạng: '+requestedLicense);
    return Object.assign({},data,{
      license:normalizedLicense,
      note:noteParts.filter(Boolean).join(' | '),
      lead_id:data.lead_id||uuid(),
      source:classifySource(a,data.source),
      landing_page:location.href,
      first_landing:a.first_landing||'',
      utm_source:a.utm_source||'',utm_medium:a.utm_medium||'',utm_campaign:a.utm_campaign||'',utm_term:a.utm_term||'',utm_content:a.utm_content||'',
      gclid:a.gclid||'',gbraid:a.gbraid||'',wbraid:a.wbraid||'',campaign_id:a.campaignid||'',ad_group_id:a.adgroupid||'',keyword:a.keyword||'',match_type:a.matchtype||'',device:a.device||'',device_model:a.devicemodel||'',network:a.network||'',creative_id:a.creative||'',target_id:a.targetid||'',placement:a.placement||'',ad_position:a.adposition||'',feed_item_id:a.feeditemid||'',extension_id:a.extensionid||'',
      physical_location_id:a.loc_physical_ms||'',interest_location_id:a.loc_interest_ms||'',referrer:document.referrer||'',user_agent:navigator.userAgent||''
    });
  }

  async function submitLead(data){
    const payload=buildLead(data);
    event('form_submit',{lead_id:payload.lead_id,license:payload.license||'',area:payload.area||'',lead_source:payload.source});
    event('generate_lead_intent',{lead_id:payload.lead_id,license:payload.license||'',area:payload.area||'',lead_source:payload.source});
    if(!CONFIG.FORM_ENDPOINT){
      event('lead_endpoint_unavailable',{lead_id:payload.lead_id});
      return {dispatched:false,payload:payload};
    }
    try{
      await fetch(CONFIG.FORM_ENDPOINT,{method:'POST',mode:'no-cors',keepalive:true,headers:{'Content-Type':'text/plain;charset=UTF-8'},body:JSON.stringify(payload)});
      const ack=await confirmLead(payload.lead_id,payload.phone);
      if(!ack){
        event('lead_submit_unconfirmed',{lead_id:payload.lead_id});
        return {dispatched:false,confirmed:false,pending:true,payload:payload};
      }
      if(!ack.duplicate&&CONFIG.GOOGLE_ADS_ID&&CONFIG.GOOGLE_ADS_CONVERSION_LABEL){
        setEnhancedConversionUserData(payload);
        fireAdsConversion(CONFIG.GOOGLE_ADS_CONVERSION_LABEL,{transaction_id:payload.lead_id});
      }
      event(ack.duplicate?'lead_duplicate':'generate_lead',{lead_id:payload.lead_id,license:payload.license||'',area:payload.area||'',lead_source:payload.source,row:ack.row||'',email_notified:ack.email_notified});
      return {dispatched:true,confirmed:true,duplicate:!!ack.duplicate,ack:ack,payload:payload};
    }catch(err){
      event('lead_submit_error',{lead_id:payload.lead_id});
      return {dispatched:false,payload:payload,error:err};
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

  function currentRegistrationIntent(){
    const path=location.pathname.toLowerCase();
    let license='';
    let area='';
    if(path.endsWith('/hoc-lai-xe-so-tu-dong-quang-ninh.html'))license='B số tự động';
    else if(path.endsWith('/hoc-lai-xe-so-co-khi-quang-ninh.html'))license='B số cơ khí';
    else if(path.endsWith('/hoc-c1-quang-ninh.html'))license='C1';
    else if(path.endsWith('/hoc-a1-quang-ninh.html'))license='A1';

    if(path.endsWith('/hoc-lai-xe-cam-pha.html')||path.endsWith('/trung-tam-quang-hanh.html'))area='Quang Hanh / Cẩm Phả';
    else if(path.endsWith('/hoc-lai-xe-ha-long.html'))area='Hạ Long';
    else if(path.endsWith('/hoc-lai-xe-uong-bi.html'))area='Uông Bí';
    else if(path.endsWith('/hoc-lai-xe-mong-cai.html'))area='Móng Cái';
    return {license:license,area:area};
  }

  function decorateRegistrationLinks(){
    if(location.pathname.endsWith('/dang-ky-hoc-lai-xe-quang-ninh.html'))return;
    const intent=currentRegistrationIntent();
    if(!intent.license&&!intent.area)return;
    document.querySelectorAll('a[href*="dang-ky-hoc-lai-xe-quang-ninh.html"]').forEach(function(a){
      try{
        const url=new URL(a.getAttribute('href'),location.href);
        if(intent.license&&!url.searchParams.has('hang'))url.searchParams.set('hang',intent.license);
        if(intent.area&&!url.searchParams.has('khuvuc'))url.searchParams.set('khuvuc',intent.area);
        if(!url.hash)url.hash='dang-ky';
        a.setAttribute('href',url.pathname+url.search+url.hash);
      }catch(e){}
    });
  }

  function selectOptionByText(select,value){
    if(!select||!value)return;
    const wanted=String(value).trim().toLowerCase();
    const option=Array.from(select.options||[]).find(function(o){
      const text=String(o.textContent||o.value||'').trim().toLowerCase();
      return text===wanted||text.indexOf(wanted)!==-1||wanted.indexOf(text)!==-1;
    });
    if(option)select.value=option.value;
  }

  function prefillRegistrationForm(){
    const q=new URLSearchParams(location.search);
    const license=q.get('hang');
    const area=q.get('khuvuc');
    if(license)selectOptionByText(document.querySelector('#rLicense,#license'),license);
    if(area)selectOptionByText(document.querySelector('#rArea,#area'),area);
  }

  function ensureConversionCtas(){
    if(!document.querySelector('.sticky-mobile')){
      const nav=document.createElement('nav');
      nav.className='sticky-mobile';
      nav.setAttribute('aria-label','Liên hệ nhanh');
      nav.innerHTML='<a href="tel:0398696879">☎ Gọi</a><a class="zalo" href="https://zalo.me/0398696879">Zalo</a><a href="/dang-ky-hoc-lai-xe-quang-ninh.html#dang-ky">Đăng ký</a>';
      document.body.appendChild(nav);
    }
    if(!document.querySelector('main a[href^="tel:"], main a[href*="zalo.me/"]')){
      const main=document.querySelector('main');
      if(!main)return;
      const section=document.createElement('section');
      section.className='site-conversion-cta';
      section.setAttribute('aria-label','Tư vấn học lái xe');
      section.innerHTML='<div><strong>Cần tư vấn hạng học phù hợp?</strong><span>Gọi hoặc nhắn Zalo 0398696879. Không thu phí tư vấn.</span></div><div><a href="tel:0398696879">Gọi ngay</a><a class="zalo" href="https://zalo.me/0398696879">Nhắn Zalo</a><a href="/dang-ky-hoc-lai-xe-quang-ninh.html#dang-ky">Đăng ký</a></div>';
      main.appendChild(section);
    }
  }

  document.addEventListener('click',function(e){
    const a=e.target.closest&&e.target.closest('a');
    if(!a)return;
    const href=a.getAttribute('href')||'';
    if(href.indexOf('tel:')===0){
      event('phone_click',{link_url:href,page_path:location.pathname});
      event('click_call',{link_url:href,page_path:location.pathname});
      fireClickConversionOnce('call',CONFIG.GOOGLE_ADS_CALL_CONVERSION_LABEL);
    }
    if(href.indexOf('zalo.me/')!==-1){
      event('zalo_click',{link_url:href,page_path:location.pathname});
      event('click_zalo',{link_url:href,page_path:location.pathname});
      fireClickConversionOnce('zalo',CONFIG.GOOGLE_ADS_ZALO_CONVERSION_LABEL);
    }
    if(href.indexOf('dang-ky-hoc-lai-xe-quang-ninh.html')!==-1||href==='#dang-ky'){
      event('registration_cta_click',{link_url:href,page_path:location.pathname});
    }
  },true);

  function init(){
    event('view_content',{page_path:location.pathname,page_title:document.title});
    registerFormStart();
    ensureConversionCtas();
    decorateRegistrationLinks();
    prefillRegistrationForm();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();

  window.LaiXeTracking={config:CONFIG,event:event,getAttribution:readAttribution,buildLead:buildLead,submitLead:submitLead,confirmLead:confirmLead,fireAdsConversion:fireAdsConversion,vnPhoneToE164:vnPhoneToE164};
})();
