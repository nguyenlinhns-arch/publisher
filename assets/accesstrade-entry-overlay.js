(function(){
  'use strict';

  var VPBANK_URL='https://go.isclix.com/deep_link/v6/6342443575996511342/6822308958202075636?sub4=oneatweb&url_enc=aHR0cHM6Ly92YXlvbmxpbmUudnBiYW5rLmNvbS52bi8%3D';
  var SESSION_KEY='hlxqn_vpbank_offer_closed_v1';

  function isGooglePaidVisit(){
    try{
      var q=new URLSearchParams(location.search);
      if(q.get('gclid')||q.get('gbraid')||q.get('wbraid'))return true;
      var source=(q.get('utm_source')||'').toLowerCase();
      var medium=(q.get('utm_medium')||'').toLowerCase();
      return source==='google'&&/^(cpc|ppc|paid|paidsearch|paid_search)$/.test(medium);
    }catch(e){return false;}
  }

  function shouldSkip(){
    try{if(sessionStorage.getItem(SESSION_KEY)==='1')return true}catch(e){}
    if(isGooglePaidVisit())return true;
    if(/\/(?:dang-ky-hoc-lai-xe-quang-ninh|uu-dai-hoc-vien)\.html$/.test(location.pathname))return true;
    return false;
  }

  function emit(name,params){
    try{
      if(window.LaiXeTracking&&typeof window.LaiXeTracking.event==='function')window.LaiXeTracking.event(name,params||{});
    }catch(e){}
  }

  function init(){
    if(shouldSkip()||document.querySelector('.at-offer-banner'))return;

    var style=document.createElement('style');
    style.textContent=''
      +'.at-offer-banner{position:fixed;right:16px;bottom:16px;z-index:58;width:min(560px,calc(100% - 32px));border:1px solid rgba(255,255,255,.30);border-radius:18px;background:linear-gradient(120deg,#2b0b63 0%,#5a167c 45%,#e76e22 100%);box-shadow:0 18px 48px rgba(28,13,55,.30);overflow:hidden;color:#fff}'
      +'.at-offer-inner{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;padding:15px 16px 13px}'
      +'.at-offer-copy{min-width:0;padding-right:16px}.at-offer-tag{display:inline-flex;margin-bottom:5px;padding:4px 7px;border-radius:999px;background:rgba(255,255,255,.16);color:#ffe6a8;font-size:9px;font-weight:900;letter-spacing:.055em;text-transform:uppercase}'
      +'.at-offer-copy strong{display:block;color:#fff;font-size:19px;line-height:1.2}.at-offer-copy small{display:block;margin-top:4px;color:rgba(255,255,255,.88);font-size:11px;line-height:1.4}'
      +'.at-offer-meta{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}.at-offer-meta span{display:inline-flex;align-items:center;min-height:24px;padding:0 7px;border:1px solid rgba(255,255,255,.20);border-radius:999px;background:rgba(255,255,255,.08);color:#fff;font-size:9px;font-weight:800}'
      +'.at-offer-cta{min-height:44px;min-width:132px;padding:0 15px;border-radius:12px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#ff7a22,#ffb11a);color:#fff!important;text-decoration:none;font-size:12px;font-weight:900;white-space:nowrap}'
      +'.at-offer-close{position:absolute;top:6px;right:6px;width:28px;height:28px;border:1px solid rgba(255,255,255,.25);border-radius:50%;background:rgba(255,255,255,.16);color:#fff;font-size:20px;line-height:1;cursor:pointer}'
      +'.at-offer-note{padding:0 16px 10px;color:rgba(255,255,255,.70);font-size:8.5px;line-height:1.35}'
      +'@media(max-width:600px){.at-offer-banner{left:10px;right:10px;bottom:78px;width:auto;border-radius:16px}.at-offer-inner{padding:13px 38px 11px 14px;grid-template-columns:1fr;gap:10px}.at-offer-copy{padding-right:0}.at-offer-copy strong{font-size:18px}.at-offer-copy small{font-size:10.5px}.at-offer-cta{min-height:42px;width:100%}.at-offer-note{padding:0 14px 9px}}';
    document.head.appendChild(style);

    var banner=document.createElement('aside');
    banner.className='at-offer-banner';
    banner.setAttribute('aria-label','Ưu đãi vay tiền online tài trợ');
    banner.innerHTML=''
      +'<button class="at-offer-close" type="button" aria-label="Đóng quảng cáo">×</button>'
      +'<div class="at-offer-inner">'
      +  '<div class="at-offer-copy"><span class="at-offer-tag">Tài trợ · ACCESSTRADE · VPBank</span><strong>Vay tiền online</strong><small>Xem ưu đãi, điều kiện và đăng ký online theo chính sách của VPBank.</small><div class="at-offer-meta"><span>Đăng ký online</span><span>Xem điều kiện</span><span>VPBank xét duyệt</span></div></div>'
      +  '<a class="at-offer-cta" href="'+VPBANK_URL+'" target="_blank" rel="sponsored nofollow noopener" data-affiliate="accesstrade-vpbank-vay-online">XEM NGAY →</a>'
      +'</div>'
      +'<div class="at-offer-note">Liên kết tài trợ qua ACCESSTRADE. Điều kiện và quyết định thực tế do VPBank áp dụng.</div>';

    function closeBanner(){
      try{sessionStorage.setItem(SESSION_KEY,'1')}catch(e){}
      banner.remove();
      emit('affiliate_banner_close',{affiliate_network:'ACCESSTRADE',affiliate_campaign:'vpbank_vay_online',merchant:'VPBank',page_path:location.pathname});
    }

    banner.querySelector('.at-offer-close').addEventListener('click',closeBanner);
    banner.querySelector('.at-offer-cta').addEventListener('click',function(){
      emit('affiliate_click',{affiliate_network:'ACCESSTRADE',affiliate_campaign:'vpbank_vay_online',merchant:'VPBank',link_url:VPBANK_URL,page_path:location.pathname});
    });
    document.body.appendChild(banner);
    emit('affiliate_banner_view',{affiliate_network:'ACCESSTRADE',affiliate_campaign:'vpbank_vay_online',merchant:'VPBank',page_path:location.pathname});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
