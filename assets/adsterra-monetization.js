(function(){
  'use strict';

  var NATIVE_KEY='e336b428517bbcb55a3e3da308cc7939';
  var NATIVE_SRC='https://pl30863058.effectivecpmnetwork.com/'+NATIVE_KEY+'/invoke.js';
  var BANNER_KEY='b3caa39744fc30610e7756cf4ccb98cd';
  var BANNER_SRC='https://www.highperformanceformat.com/'+BANNER_KEY+'/invoke.js';

  function init(){
    if(document.querySelector('.adsterra-monetization'))return;
    if(/\/dang-ky-hoc-lai-xe-quang-ninh\.html$/.test(location.pathname))return;

    var style=document.createElement('style');
    style.textContent=''
      +'.adsterra-monetization{padding:28px 0 34px;background:#f7f9fc;border-top:1px solid #e1e8f0}'
      +'.adsterra-monetization .adsterra-wrap{width:min(1120px,calc(100% - 28px));margin:auto;display:grid;gap:24px}'
      +'.adsterra-slot{text-align:center;min-width:0}'
      +'.adsterra-label{margin:0 0 9px;color:#7b8c9c;font-size:10px;font-weight:800;letter-spacing:.07em;text-transform:uppercase}'
      +'.adsterra-frame{min-height:90px;display:flex;align-items:center;justify-content:center;overflow:hidden}'
      +'.adsterra-frame--300{min-height:250px}'
      +'.adsterra-frame iframe{max-width:100%}'
      +'@media(max-width:600px){.adsterra-monetization{padding:22px 0 28px}.adsterra-monetization .adsterra-wrap{width:calc(100% - 20px);gap:18px}}';
    document.head.appendChild(style);

    var section=document.createElement('section');
    section.className='adsterra-monetization';
    section.setAttribute('aria-label','Quảng cáo');
    section.innerHTML=''
      +'<div class="adsterra-wrap">'
      +  '<div class="adsterra-slot"><p class="adsterra-label">Quảng cáo</p><div class="adsterra-frame" id="hlxqn-adsterra-native"></div></div>'
      +  '<div class="adsterra-slot"><p class="adsterra-label">Quảng cáo</p><div class="adsterra-frame adsterra-frame--300" id="hlxqn-adsterra-300"></div></div>'
      +'</div>';

    var footer=document.querySelector('body > footer,.official-footer,.simple-footer,.footer');
    if(footer&&footer.parentNode)footer.parentNode.insertBefore(section,footer);
    else document.body.appendChild(section);

    var nativeFrame=document.getElementById('hlxqn-adsterra-native');
    var nativeScript=document.createElement('script');
    nativeScript.async=true;
    nativeScript.setAttribute('data-cfasync','false');
    nativeScript.src=NATIVE_SRC;
    nativeFrame.appendChild(nativeScript);
    var nativeContainer=document.createElement('div');
    nativeContainer.id='container-'+NATIVE_KEY;
    nativeFrame.appendChild(nativeContainer);

    var bannerFrame=document.getElementById('hlxqn-adsterra-300');
    window.atOptions={
      key:BANNER_KEY,
      format:'iframe',
      height:250,
      width:300,
      params:{}
    };
    var bannerScript=document.createElement('script');
    bannerScript.src=BANNER_SRC;
    bannerScript.async=false;
    bannerFrame.appendChild(bannerScript);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
