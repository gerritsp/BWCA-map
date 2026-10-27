// Exercise the real popup and request-cache helpers without browser globals.
const assert = require('assert/strict');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('Templates/js_template.js', 'utf8').split('    function init(')[0].replace('__LAKE_BUNDLES_URL__', 'fisheries/');
(async () => {
  let count = 0;
  const context = vm.createContext({fetch: async url => { count++; return {ok:true,json: async () => ({unique_guid:'{A}'})}; }});
  vm.runInContext(source, context);
  await vm.runInContext('Promise.all([fetchLakeBundle("{A}"), fetchLakeBundle("{A}")])', context);
  assert.equal(count, 1);
  let bad = true;
  context.fetch = async () => ({ok:true,json:async()=>({unique_guid:bad?'wrong':'{B}'})});
  await assert.rejects(vm.runInContext('fetchLakeBundle("{B}")',context), /mismatch/);
  bad = false;
  assert.equal((await vm.runInContext('fetchLakeBundle("{B}")',context)).unique_guid,'{B}');
  context.bundle = {unique_guid:'{A}',name:'<img src=x onerror=alert(1)>',dowlknum:'04013500',
    lake_info:{maxDepthFeet:50}, project:{area_acres:10},clarity:[{date:'2020-01-01',clarity_ft:5},{date:'2024-01-01',clarity_ft:8}],
    fish_lengths:[{species:'WAE',length_inches:20}], fish_catches:[{species:'WAE',cpue:0,gear:'<script>',date:'2024-01-01'}],
    surveys:[{}],survey_inventory:[{}],assessments:[{}]};
  const html=vm.runInContext('lakeBundleHTML(bundle)',context);
  assert(!html.includes('<img'));
  assert(!html.includes('<script>'));
  assert(html.includes('&lt;img'));
  assert(html.includes('2024-01-01'));
  assert(html.includes('clarity_ft: 8'));
  assert(html.includes('CPUE 0'));
  assert(html.includes('fisheries/%7BA%7D.json'));
  assert(vm.runInContext('lakeBundleHTML(null)',context).includes('No lake data'));
  console.log('Popup escaping, latest clarity, zero CPUE, cache reuse, mismatch rejection and retry passed');
})().catch(e=>{console.error(e);process.exit(1);});
