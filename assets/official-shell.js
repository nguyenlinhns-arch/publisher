(function(){
  'use strict';
  const PHONE='0398696879';
  const ZALO='https://zalo.me/'+PHONE;

  function headerHtml(){
    return '<div class="official-topbar"><div class="official-wrap"><div class="topbar-left">Tuyển sinh & hỗ trợ học viên học lái xe tại Quảng Ninh</div><div class="topbar-right">Tư vấn: <a href="tel:'+PHONE+'">'+PHONE+'</a> · <a href="'+ZALO+'">Zalo</a></div></div></div>'+
    '<div class="official-wrap official-head-main">'+
      '<a class="official-brand" href="/" aria-label="Học Lái Xe Quảng Ninh - Trang chủ"><span class="official-mark">QN</span><span class="official-brand-copy"><strong>Học Lái Xe Quảng Ninh</strong><small>Tuyển sinh & hỗ trợ học viên</small></span></a>'+
      '<nav class="official-nav" aria-label="Điều hướng chính">'+
        '<a href="/">Trang chủ</a><a href="/gioi-thieu.html">Giới thiệu</a>'+
        '<details><summary>Khóa học</summary><div class="official-dropdown"><a href="/hoc-lai-xe-so-tu-dong-quang-ninh.html">B số tự động</a><a href="/hoc-lai-xe-so-co-khi-quang-ninh.html">B số cơ khí</a><a href="/hoc-c1-quang-ninh.html">Hạng C1</a><a href="/hoc-a1-quang-ninh.html">Hạng A1</a></div></details>'+
        '<details><summary>Tuyển sinh</summary><div class="official-dropdown"><a href="/hoc-phi-hoc-lai-xe-quang-ninh.html">Học phí</a><a href="/ho-so-hoc-lai-xe-quang-ninh.html">Hồ sơ đăng ký</a><a href="/lich-sat-hach/">Lịch sát hạch</a><a href="/dang-ky-hoc-lai-xe-quang-ninh.html">Đăng ký học</a></div></details>'+
        '<details><summary>Khu vực học</summary><div class="official-dropdown"><a href="/trung-tam-quang-hanh.html">Quang Hanh</a><a href="/hoc-lai-xe-cam-pha.html">Cẩm Phả</a><a href="/hoc-lai-xe-ha-long.html">Hạ Long</a><a href="/hoc-lai-xe-uong-bi.html">Uông Bí</a><a href="/hoc-lai-xe-mong-cai.html">Móng Cái</a></div></details>'+
        '<a href="/hoc-ly-thuyet.html">Cẩm nang</a><a href="/tin-tuc.html">Tin tức</a><a href="/lien-he.html">Liên hệ</a>'+
      '</nav>'+
      '<a class="official-head-cta" href="/dang-ky-hoc-lai-xe-quang-ninh.html#dang-ky">Đăng ký học</a>'+
      '<details class="official-mobile-menu"><summary>☰ Menu</summary><div class="official-mobile-panel"><a href="/">Trang chủ</a><a href="/gioi-thieu.html">Giới thiệu</a><a href="/hoc-lai-xe-so-tu-dong-quang-ninh.html">B số tự động</a><a href="/hoc-lai-xe-so-co-khi-quang-ninh.html">B số cơ khí</a><a href="/hoc-c1-quang-ninh.html">Hạng C1</a><a href="/hoc-a1-quang-ninh.html">Hạng A1</a><a href="/hoc-phi-hoc-lai-xe-quang-ninh.html">Học phí</a><a href="/ho-so-hoc-lai-xe-quang-ninh.html">Hồ sơ</a><a href="/lich-sat-hach/">Lịch sát hạch</a><a href="/hoc-ly-thuyet.html">Cẩm nang</a><a href="/tin-tuc.html">Tin tức</a><a href="/lien-he.html">Liên hệ</a><a href="/dang-ky-hoc-lai-xe-quang-ninh.html#dang-ky">Đăng ký học</a></div></details>'+
    '</div>';
  }

  function footerHtml(){
    return '<footer class="official-footer">'+
      '<div class="official-wrap official-footer-main">'+
        '<div class="official-footer-brand"><strong>Học Lái Xe Quảng Ninh</strong><p>Thông tin tuyển sinh, học phí, hồ sơ, chương trình học, khu vực đào tạo và hướng dẫn dành cho người học lái xe tại Quảng Ninh.</p><p><b style="color:#fff">Tư vấn: '+PHONE+'</b></p></div>'+
        '<div><h4>Tuyển sinh</h4><div class="official-footer-links"><a href="/hoc-phi-hoc-lai-xe-quang-ninh.html">Học phí</a><a href="/ho-so-hoc-lai-xe-quang-ninh.html">Hồ sơ đăng ký</a><a href="/dang-ky-hoc-lai-xe-quang-ninh.html">Đăng ký học</a><a href="/lich-sat-hach/">Lịch sát hạch</a></div></div>'+
        '<div><h4>Khóa học</h4><div class="official-footer-links"><a href="/hoc-lai-xe-so-tu-dong-quang-ninh.html">B số tự động</a><a href="/hoc-lai-xe-so-co-khi-quang-ninh.html">B số cơ khí</a><a href="/hoc-c1-quang-ninh.html">Hạng C1</a><a href="/hoc-a1-quang-ninh.html">Hạng A1</a></div></div>'+
        '<div><h4>Thông tin</h4><div class="official-footer-links"><a href="/gioi-thieu.html">Giới thiệu</a><a href="/tin-tuc.html">Tin tức</a><a href="/hoc-ly-thuyet.html">Cẩm nang</a><a href="/uu-dai-hoc-vien.html">Ưu đãi học viên</a><a href="/chinh-sach-bao-mat.html">Chính sách bảo mật</a><a href="/dieu-khoan-su-dung.html">Điều khoản sử dụng</a><a href="/lien-he.html">Liên hệ</a></div></div>'+
      '</div>'+
      '<div class="official-footer-bottom"><div class="official-wrap"><div class="official-disclaimer">hoclaixequangninh.vn là kênh thông tin và tư vấn tuyển sinh, không phải cổng thông tin của cơ quan quản lý nhà nước. Thông tin học phí, lịch học và sát hạch được cập nhật theo thông báo áp dụng của đơn vị đào tạo/cơ quan có thẩm quyền.</div><div>© hoclaixequangninh.vn</div></div></div>'+
    '</footer>';
  }

  function polishNarrative(){
    const replacements=[
      ['Website tổ chức nội dung theo từng khu vực để người học dễ tìm địa điểm, chương trình và thông tin liên quan.','Chọn khu vực thuận tiện để xem địa điểm học, chương trình và thông tin phù hợp.'],
      ['Website đang cung cấp thông tin theo các khu vực Quang Hanh/Cẩm Phả, Uông Bí, Móng Cái, Hạ Long và khu vực khác.','Có thể lựa chọn Quang Hanh/Cẩm Phả, Hạ Long, Uông Bí, Móng Cái hoặc khu vực khác khi đăng ký.'],
      ['Website đang có thông tin theo Quang Hanh/Cẩm Phả, Uông Bí, Hạ Long và Móng Cái.','Có thể lựa chọn Quang Hanh/Cẩm Phả, Hạ Long, Uông Bí hoặc Móng Cái tùy nơi ở và lịch học.'],
      ['Website được tổ chức theo đúng các câu hỏi mà một người mới thường gặp trong suốt quá trình học.','Các bước được sắp xếp theo hành trình thực tế từ chọn hạng, chuẩn bị hồ sơ đến học và sát hạch.'],
      ['Website có trang Hồ sơ đăng ký riêng. Nên kiểm tra danh mục giấy tờ đang áp dụng trước khi đến nộp để tránh phải bổ sung nhiều lần.','Nên kiểm tra danh mục hồ sơ đang áp dụng trước khi đến nộp để tránh phải bổ sung nhiều lần.'],
      ['Website đã tách nội dung theo Cẩm Phả, Hạ Long, Uông Bí và Móng Cái.','Chọn Cẩm Phả, Hạ Long, Uông Bí hoặc Móng Cái trong mục Khu vực học để xem thông tin phù hợp.'],
      ['Website có trang so sánh riêng để người học xem phạm vi sử dụng, học phí và thời gian trước khi đăng ký.','Hãy so sánh phạm vi sử dụng, học phí và thời gian học trước khi đăng ký.'],
      ['Website có trang giải thích riêng về DAT và tiến độ học.','Xem phần DAT để hiểu cách theo dõi tiến độ thực hành trước khi bắt đầu khóa học.'],
      ['Website không thu phí tư vấn hoặc phí môi giới.','Tư vấn không thu phí hoặc phí môi giới.'],
      ['Xem thêm thông tin các khu vực Hạ Long, Uông Bí và Móng Cái trên website.','Thông tin Hạ Long, Uông Bí và Móng Cái được cập nhật theo từng khu vực.'],
      ['Website tổng hợp và trình bày theo từng nhu cầu:','Thông tin được trình bày theo từng nhu cầu:'],
      ['Website có thể lưu UTM/GCLID khi truy cập từ quảng cáo để đo hiệu quả.','Hệ thống có thể lưu UTM/GCLID khi truy cập từ quảng cáo để đo hiệu quả.'],
      ['Thông tin có thể xem ngay trên website','Thông tin nên xem trước khi quyết định'],
      ['Website tuyển sinh','Tuyển sinh học lái xe']
    ];
    const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
    const nodes=[];
    while(walker.nextNode())nodes.push(walker.currentNode);
    nodes.forEach(function(node){
      let text=node.nodeValue;
      replacements.forEach(function(pair){if(text.indexOf(pair[0])!==-1)text=text.split(pair[0]).join(pair[1])});
      node.nodeValue=text;
    });
  }

  function upgradeHomepageForm(){
    if(!document.querySelector('.institutional-home'))return;
    const old=document.getElementById('quickForm');
    if(!old||old.dataset.officialCapture==='1')return;
    const form=old.cloneNode(true);
    form.dataset.officialCapture='1';
    old.replaceWith(form);
    const name=form.querySelector('#name'),phone=form.querySelector('#phone'),license=form.querySelector('#license'),area=form.querySelector('#area'),status=form.querySelector('#formStatus'),btn=form.querySelector('button[type="submit"]');
    if(!name||!phone||!license||!area||!status||!btn)return;

    document.querySelectorAll('[data-license]').forEach(function(link){
      link.addEventListener('click',function(){
        const selected=link.getAttribute('data-license');
        if(selected)license.value=selected;
      });
    });

    const success=document.createElement('div');
    success.className='success-box';
    success.innerHTML='<strong>Đăng ký đã được ghi nhận.</strong><p>Bạn không cần gửi lại thông tin. Nếu muốn trao đổi ngay, có thể nhắn Zalo.</p><a href="'+ZALO+'">Nhắn Zalo ngay</a>';
    form.appendChild(success);
    form.addEventListener('submit',async function(e){
      e.preventDefault();
      const ph=phone.value.replace(/\D/g,'');
      if(name.value.trim().length<2){name.focus();return}
      if(!/^[0-9]{9,11}$/.test(ph)){phone.setCustomValidity('Nhập số điện thoại 9–11 chữ số');phone.reportValidity();return}
      phone.setCustomValidity('');
      btn.disabled=true;
      status.textContent='Đang ghi nhận đăng ký...';
      success.classList.remove('show');
      let result={dispatched:false};
      if(window.LaiXeTracking&&typeof window.LaiXeTracking.submitLead==='function'){
        result=await window.LaiXeTracking.submitLead({name:name.value.trim(),phone:ph,license:license.value,area:area.value,consent:true,source:'Website',note:'Form trang chủ'});
      }
      btn.disabled=false;
      if(result.confirmed){
        status.textContent=result.duplicate?'Thông tin này đã được ghi nhận trước đó.':'Đã ghi nhận đăng ký thành công.';
        success.classList.add('show');
        form.querySelectorAll('input,select').forEach(function(el){if(el.id!=='consent')el.disabled=true});
        btn.style.display='none';
      }else if(result.pending){
        status.textContent='Yêu cầu đã được gửi và đang chờ xác nhận. Nếu cần trao đổi ngay, vui lòng gọi hoặc nhắn Zalo.';
      }else{
        status.textContent='Chưa ghi nhận được tự động. Vui lòng gọi 0398696879 hoặc nhắn Zalo để được hỗ trợ.';
      }
    });
  }

  function installHeader(){
    const current=document.querySelector('.official-header');
    if(current)return;
    const legacy=document.querySelector('.simple-header,.header,body > header');
    const h=document.createElement('header');
    h.className='official-header';
    h.innerHTML=headerHtml();
    if(legacy)legacy.replaceWith(h);
    else document.body.insertBefore(h,document.body.firstChild);
  }

  function installFooter(){
    const current=document.querySelector('.official-footer');
    if(current)return;
    const holder=document.createElement('div');
    holder.innerHTML=footerHtml();
    const footer=holder.firstElementChild;
    const legacy=document.querySelector('body > footer,.simple-footer,.footer');
    if(legacy)legacy.replaceWith(footer);
    else document.body.appendChild(footer);
  }

  function ensureAffiliateNavigation(){
    const footer=document.querySelector('.official-footer');
    if(footer&&!footer.querySelector('a[href="/uu-dai-hoc-vien.html"],a[href="uu-dai-hoc-vien.html"]')){
      const groups=footer.querySelectorAll('.official-footer-links');
      const target=groups.length?groups[groups.length-1]:null;
      if(target){
        const a=document.createElement('a');
        a.href='/uu-dai-hoc-vien.html';
        a.textContent='Ưu đãi học viên';
        target.appendChild(a);
      }
    }

    if(location.pathname.endsWith('/hoc-ly-thuyet.html')&&!document.querySelector('.affiliate-learning-cta')){
      const main=document.querySelector('main');
      if(main){
        const section=document.createElement('section');
        section.className='simple-section affiliate-learning-cta';
        section.innerHTML='<div class="wrap"><div class="section-title"><span>TIỆN ÍCH</span><h2>Đồ dùng hữu ích cho người đang học và mới lái xe</h2><p class="lead">Một số gợi ý bổ trợ cho việc học và sử dụng xe. Mua sắm hoàn toàn tự chọn, không liên quan điều kiện đăng ký khóa học.</p></div><div class="actions"><a class="cta secondary" href="/uu-dai-hoc-vien.html">Xem gợi ý & ưu đãi →</a></div></div>';
        main.appendChild(section);
      }
    }
  }

  function removeLegacyMobileBars(){
    document.querySelectorAll('nav.mobile').forEach(function(nav){
      if(nav.classList.contains('sticky-mobile'))return;
      nav.remove();
    });
  }

  function trackAffiliateClicks(){
    document.addEventListener('click',function(e){
      const a=e.target.closest&&e.target.closest('a[data-affiliate]');
      if(!a)return;
      if(window.LaiXeTracking&&typeof window.LaiXeTracking.event==='function'){
        window.LaiXeTracking.event('affiliate_click',{
          affiliate_network:'ACCESSTRADE',
          affiliate_campaign:a.getAttribute('data-affiliate')||'accesstrade',
          link_url:a.href,
          page_path:location.pathname
        });
      }
    },true);
  }

  function init(){
    installHeader();
    installFooter();
    removeLegacyMobileBars();
    polishNarrative();
    ensureAffiliateNavigation();
    setTimeout(upgradeHomepageForm,0);
    trackAffiliateClicks();
    document.addEventListener('click',function(e){
      const open=document.querySelectorAll('.official-nav details[open],.official-mobile-menu[open]');
      open.forEach(function(d){if(!d.contains(e.target))d.removeAttribute('open')});
    });
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
