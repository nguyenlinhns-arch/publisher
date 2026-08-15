window.HLX_CONFIG={
  FORM_ENDPOINT:'https://script.google.com/macros/s/AKfycbw0QjEWzZf-NXI7ykt2851kePOGJN5w10O7SMt3JMr7dPK5g7Vp2l4ABLnSO1vpFeqS/exec',
  GA4_MEASUREMENT_ID:'',
  GOOGLE_ADS_ID:'AW-16660675113',
  GOOGLE_ADS_CONVERSION_LABEL:'WlccCOvqpeAcEKn0tog-',
  GOOGLE_ADS_CALL_CONVERSION_LABEL:'_bbHCP7SqeAcEKn0tog-',
  GOOGLE_ADS_ZALO_CONVERSION_LABEL:'A5g8CM7OuOAcEKn0tog-'
};
(function(){
  // Các trang chuẩn đã nạp mobile-v2.css tĩnh trong <head>; không tải trùng CSS.
  // Một số trang đặc thù/legacy có stylesheet riêng: chỉ bổ sung design system khi thiếu.
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
  var shell=document.createElement('script');
  shell.src='/assets/official-shell.js?v=20260815e';
  shell.defer=true;
  document.head.appendChild(shell);
})();
