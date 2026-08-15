(function(){
  'use strict';
  function ensureModernRuntime(){
    if(window.LaiXeTracking)return;
    if(document.querySelector('script[src*="/assets/site-runtime.js"],script[src="assets/site-runtime.js"],script[src="../assets/site-runtime.js"]'))return;
    var s=document.createElement('script');
    s.src='/assets/site-runtime.js?v=20260815e';
    s.defer=true;
    document.head.appendChild(s);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ensureModernRuntime);else ensureModernRuntime();
})();
