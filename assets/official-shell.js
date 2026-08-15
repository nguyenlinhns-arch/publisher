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
      '<details class="official-mobile-menu"><summary>☰ Menu</summary><div class="official-mobile-panel"><a href="/">Trang chủ</a><a href="/gioi-thieu.html">Giới thiệu</a><a href="/hoc-lai-xe-so-tu-dong-quang-ninh.html">B số tự động</a><a href="/hoc-lai-xe-so-co-khi-quang-ninh.html">B số cơ khí</a><a href="/hoc-c1-quang-ninh.html">Hạng C1</a><a href="/hoc-phi-hoc-lai-xe-quang-ninh.html">Học phí</a><a href="/ho-so-hoc-lai-xe-quang-ninh.html">Hồ sơ</a><a href="/lich-sat-hach/">Lịch sát hạch</a><a href="/hoc-ly-thuyet.html">Cẩm nang</a><a href="/tin-tuc.html">Tin tức</a><a href="/lien-he.html">Liên hệ</a><a href="/dang-ky-hoc-lai-xe-quang-ninh.html#dang-ky">Đăng ký học</a></div></details>'+
    '</div>';
  }
  function footerHtml(){
    return '<footer class="official-footer">'+
      '<div class="official-wrap official-footer-main">'+
        '<div class="official-footer-brand"><strong>Học Lái Xe Quảng Ninh</strong><p>Thông tin tuyển sinh, học phí, hồ sơ, chương trình học, khu vực đào tạo và hướng dẫn dành cho người học lái xe tại Quảng Ninh.</p><p><b style="color:#fff">Tư vấn: '+PHONE+'</b></p></div>'+
        '<div><h4>Tuyển sinh</h4><div class="official-footer-links"><a href="/hoc-phi-hoc-lai-xe-quang-ninh.html">Học phí</a><a href="/ho-so-hoc-lai-xe-quang-ninh.html">Hồ sơ đăng ký</a><a href="/dang-ky-hoc-lai-xe-quang-ninh.html">Đăng ký học</a><a href="/lich-sat-hach/">Lịch sát hạch</a></div></div>'+
        '<div><h4>Khóa học</h4><div class="official-footer-links"><a href="/hoc-lai-xe-so-tu-dong-quang-ninh.html">B số tự động</a><a href="/hoc-lai-xe-so-co-khi-quang-ninh.html">B số cơ khí</a><a href="/hoc-c1-quang-ninh.html">Hạng C1</a><a href="/hoc-a1-quang-ninh.html">Hạng A1</a></div></div>'+
        '<div><h4>Thông tin</h4><div class="official-footer-links"><a href="/gioi-thieu.html">Giới thiệu</a><a href="/tin-tuc.html">Tin tức</a><a href="/hoc-ly-thuyet.html">Cẩm nang</a><a href="/chinh-sach-bao-mat.html">Chính sách bảo mật</a><a href="/dieu-khoan-su-dung.html">Điều khoản sử dụng</a><a href="/lien-he.html">Liên hệ</a></div></div>'+
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
      ['Website có thể lưu UTM/GCLID khi truy cập từ quảng cáo để đo hiệu quả.','Hệ thống có thể lưu UTM/GCLID khi truy cập từ quảng cáo để đo hiệu quả.']
    ];
    const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
    const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
    nodes.forEach(function(node){
      let text=node.nodeValue;
      replacements.forEach(function(pair){if(text.indexOf(pair[0])!==-1)text=text.split(pair[0]).join(pair[1])});
      node.nodeValue=text;
    });
  }
  function init(){
    const old=document.querySelector('.simple-header,.header,.official-header');
    if(old && !old.classList.contains('official-header')){
      const h=document.createElement('header');h.className='official-header';h.innerHTML=headerHtml();old.replaceWith(h);
    }else if(!old){const h=document.createElement('header');h.className='official-header';h.innerHTML=headerHtml();document.body.insertBefore(h,document.body.firstChild)}
    if(!document.querySelector('.official-footer'))document.body.insertAdjacentHTML('beforeend',footerHtml());
    polishNarrative();
    document.addEventListener('click',function(e){
      const open=document.querySelectorAll('.official-nav details[open],.official-mobile-menu[open]');
      open.forEach(function(d){if(!d.contains(e.target))d.removeAttribute('open')});
    });
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
