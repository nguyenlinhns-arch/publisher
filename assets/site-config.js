window.HLX_CONFIG={
  FORM_ENDPOINT:'https://script.google.com/macros/s/AKfycbw0QjEWzZf-NXI7ykt2851kePOGJN5w10O7SMt3JMr7dPK5g7Vp2l4ABLnSO1vpFeqS/exec',
  GA4_MEASUREMENT_ID:'',
  GOOGLE_ADS_ID:'AW-16660675113',
  GOOGLE_ADS_CONVERSION_LABEL:'WlccCOvqpeAcEKn0tog-',
  GOOGLE_ADS_CALL_CONVERSION_LABEL:'_bbHCP7SqeAcEKn0tog-',
  GOOGLE_ADS_ZALO_CONVERSION_LABEL:'A5g8CM7OuOAcEKn0tog-'
};
(function(){
  if(!document.querySelector('link[rel~="icon"]')){
    var icon=document.createElement('link');
    icon.rel='icon';
    icon.type='image/svg+xml';
    icon.href='/favicon.svg';
    document.head.appendChild(icon);
  }

  var links=Array.prototype.slice.call(document.querySelectorAll('link[rel="stylesheet"]'));
  var hasInstitutionalCss=links.some(function(link){
    var href=String(link.getAttribute('href')||'');
    return /(?:^|\/)mobile-v2\.css(?:\?|$)/.test(href)||/(?:^|\/)official-site\.css(?:\?|$)/.test(href);
  });
  if(!hasInstitutionalCss){
    ['official-site.css?v=20260815d','official-pages.css?v=20260815d'].forEach(function(file){
      var css=document.createElement('link');
      css.rel='stylesheet';
      css.href='/assets/'+file;
      document.head.appendChild(css);
    });
  }

  var staticHome=!!document.querySelector('.institutional-home')&&!!document.querySelector('.official-header')&&!!document.querySelector('.official-footer');
  if(!staticHome){
    var shell=document.createElement('script');
    shell.src='/assets/official-shell.js?v=20260815h';
    shell.async=true;
    document.head.appendChild(shell);
  }

  function isGooglePaidVisit(){
    try{
      var q=new URLSearchParams(location.search);
      if(q.get('gclid')||q.get('gbraid')||q.get('wbraid'))return true;
      var source=(q.get('utm_source')||'').toLowerCase();
      var medium=(q.get('utm_medium')||'').toLowerCase();
      return source==='google'&&/^(cpc|ppc|paid|paidsearch|paid_search)$/.test(medium);
    }catch(e){return false;}
  }

  function loadAffiliate(){
    if(isGooglePaidVisit())return;
    if(/\/(?:dang-ky-hoc-lai-xe-quang-ninh|uu-dai-hoc-vien)\.html$/.test(location.pathname))return;
    var offer=document.createElement('script');
    offer.src='/assets/accesstrade-entry-overlay.js?v=20260816b';
    offer.async=true;
    document.head.appendChild(offer);
  }

  function scheduleAffiliate(){
    if('requestIdleCallback' in window)requestIdleCallback(loadAffiliate,{timeout:1800});
    else setTimeout(loadAffiliate,900);
  }
  if(document.readyState==='complete')scheduleAffiliate();
  else window.addEventListener('load',scheduleAffiliate,{once:true});
})();
