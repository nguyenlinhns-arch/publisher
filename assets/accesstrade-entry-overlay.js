(function(){
  'use strict';

  var SMARTLINK='https://nguyenlinhtkv_aul4jx.accesslanding.site';
  var SESSION_KEY='hlxqn_accesstrade_offer_closed_v2';

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
      +'.at-offer-banner{position:fixed;right:16px;bottom:16px;z-index:58;width:min(410px,calc(100% - 32px));border:1px solid #e7e1dc;border-radius:18px;background:#fff;box-shadow:0 18px 48px rgba(4,35,58,.18);overflow:hidden}'
      +'.at-offer-inner{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding:15px 16px}'
      +'.at-offer-copy{min-width:0}.at-offer-tag{display:block;margin-bottom:4px;color:#b74022;font-size:10px;font-weight:900;letter-spacing:.055em;text-transform:uppercase}'
      +'.at-offer-copy strong{display:block;color:#082f55;font-size:15px;line-height:1.25}.at-offer-copy small{display:block;margin-top:3px;color:#657785;font-size:11px;line-height:1.35}'
      +'.at-offer-cta{min-height:42px;padding:0 13px;border-radius:11px;display:flex;align-items:center;justify-content:center;background:#b33a20;color:#fff!important;text-decoration:none;font-size:12.5px;font-weight:900;white-space:nowrap}'
      +'.at-offer-close{position:absolute;top:4px;right:4px;width:28px;height:28px;border:0;border-radius:50%;background:transparent;color:#81909a;font-size:20px;line-height:1;cursor:pointer}'
      +'.at-offer-note{padding:6px 14px 8px;border-top:1px solid #f0ece9;background:#fbfaf9;color:#8a969d;font-size:9px;line-height:1.3}'
      +'@media(max-width:600px){.at-offer-banner{left:10px;right:10px;bottom:78px;width:auto;border-radius:15px}.at-offer-inner{padding:13px 38px 13px 14px;grid-template-columns:1fr}.at-offer-cta{min-height:40px;width:100%}.at-offer-note{padding:5px 14px 7px}}';
    document.head.appendChild(style);

    var banner=document.createElement('aside');
    banner.className='at-offer-banner';
    banner.setAttribute('aria-label','Ưu đãi mua sắm');
    banner.innerHTML=''
      +'<button class="at-offer-close" type="button" aria-label="Đóng ưu đãi">×</button>'
      +'<div class="at-offer-inner">'
      +  '<div class="at-offer-copy"><span class="at-offer-tag">Ưu đãi học viên</span><strong>Phụ kiện & đồ dùng cho người học lái xe</strong><small>Xem sản phẩm và ưu đãi từ đối tác.</small></div>'
      +  '<a class="at-offer-cta" href="'+SMARTLINK+'" target="_blank" rel="sponsored nofollow noopener" data-affiliate="accesstrade-entry-banner">Xem ưu đãi</a>'
      +'</div>'
      +'<div class="at-offer-note">Liên kết tiếp thị ACCESSTRADE có thể mang lại hoa hồng cho hoclaixequangninh.vn.</div>';

    function closeBanner(){
      try{sessionStorage.setItem(SESSION_KEY,'1')}catch(e){}
      banner.remove();
      emit('affiliate_banner_close',{page_path:location.pathname});
    }

    banner.querySelector('.at-offer-close').addEventListener('click',closeBanner);
    banner.querySelector('.at-offer-cta').addEventListener('click',function(){
      emit('affiliate_click',{affiliate_network:'ACCESSTRADE',affiliate_campaign:'entry_banner',link_url:SMARTLINK,page_path:location.pathname});
    });
    document.body.appendChild(banner);
    emit('affiliate_banner_view',{page_path:location.pathname});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
