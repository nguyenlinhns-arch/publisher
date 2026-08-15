(function(){
  'use strict';

  var SMARTLINK='https://nguyenlinhtkv_aul4jx.accesslanding.site';
  var SESSION_KEY='hlxqn_accesstrade_entry_closed_v1';

  function isGooglePaidVisit(){
    try{
      var q=new URLSearchParams(location.search);
      if(q.get('gclid')||q.get('gbraid')||q.get('wbraid'))return true;
      var source=(q.get('utm_source')||'').toLowerCase();
      var medium=(q.get('utm_medium')||'').toLowerCase();
      return source==='google' && /^(cpc|ppc|paid|paidsearch|paid_search)$/.test(medium);
    }catch(e){return false;}
  }

  function shouldSkip(){
    if(sessionStorage.getItem(SESSION_KEY)==='1')return true;
    if(isGooglePaidVisit())return true;
    if(/\/dang-ky-hoc-lai-xe-quang-ninh\.html$/.test(location.pathname))return true;
    return false;
  }

  function emit(name,params){
    try{
      if(window.LaiXeTracking&&typeof window.LaiXeTracking.event==='function'){
        window.LaiXeTracking.event(name,params||{});
      }
    }catch(e){}
  }

  function init(){
    if(shouldSkip()||document.querySelector('.at-entry-overlay'))return;

    var style=document.createElement('style');
    style.textContent=''
      +'.at-entry-lock{overflow:hidden!important}'
      +'.at-entry-overlay{position:fixed;inset:0;z-index:2147483000;display:grid;place-items:center;padding:18px;background:rgba(3,20,36,.78);backdrop-filter:blur(5px);-webkit-backdrop-filter:blur(5px)}'
      +'.at-entry-card{position:relative;width:min(520px,100%);border-radius:24px;background:#fff;box-shadow:0 28px 80px rgba(0,0,0,.34);overflow:hidden;border:1px solid rgba(255,255,255,.45)}'
      +'.at-entry-top{padding:26px 26px 22px;background:linear-gradient(135deg,#fff3ec,#fff);text-align:left}'
      +'.at-entry-tag{display:inline-flex;padding:6px 9px;border-radius:999px;background:#fff0e8;color:#b74022;font-size:10px;font-weight:900;letter-spacing:.06em;text-transform:uppercase}'
      +'.at-entry-card h2{margin:11px 0 8px;color:#082f55;font-size:27px;line-height:1.16;letter-spacing:-.03em}'
      +'.at-entry-card p{margin:0;color:#536777;font-size:14px;line-height:1.55}'
      +'.at-entry-actions{padding:0 26px 24px;display:grid;gap:10px}'
      +'.at-entry-primary{min-height:54px;border-radius:14px;display:flex;align-items:center;justify-content:center;background:#ee4d2d;color:#fff!important;text-decoration:none;font-size:15px;font-weight:900}'
      +'.at-entry-secondary{min-height:46px;border:0;background:transparent;color:#5b6d79;font-size:13px;font-weight:800;cursor:pointer}'
      +'.at-entry-close{position:absolute;top:12px;right:12px;width:40px;height:40px;border:0;border-radius:50%;display:grid;place-items:center;background:#fff;color:#17384f;font-size:25px;line-height:1;box-shadow:0 4px 16px rgba(8,34,57,.14);cursor:pointer}'
      +'.at-entry-note{padding:11px 26px 15px;background:#f7f9fb;color:#84919a;font-size:10px;line-height:1.4;text-align:center}'
      +'@media(max-width:520px){.at-entry-overlay{padding:12px}.at-entry-card{border-radius:20px}.at-entry-top{padding:24px 20px 18px}.at-entry-card h2{font-size:24px}.at-entry-actions{padding:0 20px 20px}.at-entry-note{padding:10px 18px 13px}}';
    document.head.appendChild(style);

    var overlay=document.createElement('div');
    overlay.className='at-entry-overlay';
    overlay.setAttribute('role','dialog');
    overlay.setAttribute('aria-modal','true');
    overlay.setAttribute('aria-labelledby','at-entry-title');
    overlay.innerHTML=''
      +'<div class="at-entry-card">'
      +  '<button class="at-entry-close" type="button" aria-label="Đóng">×</button>'
      +  '<div class="at-entry-top">'
      +    '<span class="at-entry-tag">ƯU ĐÃI MUA SẮM</span>'
      +    '<h2 id="at-entry-title">Xem ưu đãi đang có</h2>'
      +    '<p>Phụ kiện ô tô, đồ chăm sóc xe và nhiều sản phẩm đang có ưu đãi.</p>'
      +  '</div>'
      +  '<div class="at-entry-actions">'
      +    '<a class="at-entry-primary" href="'+SMARTLINK+'" target="_blank" rel="sponsored nofollow noopener" data-affiliate="accesstrade-entry-overlay">Xem ưu đãi</a>'
      +    '<button class="at-entry-secondary" type="button">Tiếp tục xem website</button>'
      +  '</div>'
      +  '<div class="at-entry-note">Liên kết tiếp thị ACCESSTRADE có thể mang lại hoa hồng cho hoclaixequangninh.vn.</div>'
      +'</div>';

    function closeOverlay(){
      try{sessionStorage.setItem(SESSION_KEY,'1')}catch(e){}
      document.documentElement.classList.remove('at-entry-lock');
      overlay.remove();
      emit('affiliate_overlay_close',{page_path:location.pathname});
    }

    overlay.querySelector('.at-entry-close').addEventListener('click',closeOverlay);
    overlay.querySelector('.at-entry-secondary').addEventListener('click',closeOverlay);
    overlay.querySelector('.at-entry-primary').addEventListener('click',function(){
      emit('affiliate_click',{affiliate_network:'ACCESSTRADE',affiliate_campaign:'entry_overlay',link_url:SMARTLINK,page_path:location.pathname});
    });
    overlay.addEventListener('click',function(e){if(e.target===overlay)closeOverlay()});
    document.addEventListener('keydown',function esc(e){
      if(e.key==='Escape'){
        document.removeEventListener('keydown',esc);
        closeOverlay();
      }
    });

    document.documentElement.classList.add('at-entry-lock');
    document.body.appendChild(overlay);
    emit('affiliate_overlay_view',{page_path:location.pathname});
    setTimeout(function(){var btn=overlay.querySelector('.at-entry-close');if(btn)btn.focus()},0);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
