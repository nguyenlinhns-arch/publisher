import fs from 'node:fs';

const reportPath=process.argv[2];
if(!reportPath||!fs.existsSync(reportPath)){
  console.log(JSON.stringify({lighthouse:'unavailable',reason:'report-missing'},null,2));
  process.exit(0);
}
const lhr=JSON.parse(fs.readFileSync(reportPath,'utf8'));
const score=name=>Math.round(((lhr.categories?.[name]?.score??0)*100));
const numeric=id)=>{
  const a=lhr.audits?.[id];
  return a&&typeof a.numericValue==='number'?Math.round(a.numericValue):null;
};
const opportunities=Object.values(lhr.audits||{})
  .filter(a=>a&&a.details?.type==='opportunity'&&typeof a.details.overallSavingsMs==='number'&&a.details.overallSavingsMs>=100)
  .sort((a,b)=>b.details.overallSavingsMs-a.details.overallSavingsMs)
  .slice(0,8)
  .map(a=>({id:a.id,title:a.title,savingsMs:Math.round(a.details.overallSavingsMs)}));
const diagnostics=Object.values(lhr.audits||{})
  .filter(a=>a&&a.scoreDisplayMode==='binary'&&a.score===0)
  .slice(0,12)
  .map(a=>({id:a.id,title:a.title}));
const summary={
  lighthouseVersion:lhr.lighthouseVersion,
  finalUrl:lhr.finalDisplayedUrl||lhr.finalUrl,
  scores:{
    performance:score('performance'),
    accessibility:score('accessibility'),
    bestPractices:score('best-practices'),
    seo:score('seo')
  },
  metrics:{
    fcpMs:numeric('first-contentful-paint'),
    lcpMs:numeric('largest-contentful-paint'),
    speedIndexMs:numeric('speed-index'),
    tbtMs:numeric('total-blocking-time'),
    cls:lhr.audits?.['cumulative-layout-shift']?.numericValue??null
  },
  opportunities,
  failedBinaryAudits:diagnostics
};
console.log(JSON.stringify(summary,null,2));
