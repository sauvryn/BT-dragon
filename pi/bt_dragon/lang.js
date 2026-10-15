/* BT Dragon: the Den's pages in British, American or Canadian English (see lang.py). The rules are
   Bookworm's; Harald fills in which English and the rules when he serves this file.
   Every piece of text on the page is converted as it appears, except inside anything marked
   data-nolang: names of networks, gadgets, places and your own list items stay as they are. */
(function(){
  var LANG = "__LANG__", R = __RULES__;
  if (!R || !R.us) return;
  var mk = function(L){ return L.map(function(x){ return [new RegExp(x[0], x[1])].concat(x.slice(2)); }); };
  var S = {us: mk(R.us), gb: mk(R.gb), ca_gb: mk(R.ca_gb), ca_ize: mk(R.ca_ize),
           us_words: mk(R.us_words), gb_words: mk(R.gb_words), ca_words: mk(R.ca_words)};
  function fix(m, from, to){
    var r = to + m.slice(from.length);
    return m.length > 1 && m === m.toUpperCase() ? r.toUpperCase() : m[0] !== m[0].toLowerCase() ? r[0].toUpperCase() + r.slice(1) : r;
  }
  /* names never converted, as in Bookworm: every insect species' name (placeholders, then put back) */
  var esc = function(n){ return n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); };
  var KEEP = R.keep && R.keep.length ? new RegExp("(?<![A-Za-z])(?:" + R.keep.map(esc).join("|") + ")(?![A-Za-z])", "gi") : null;
  function convert(t){
    if (typeof t !== "string" || !/[a-z]/i.test(t)) return t;
    if (!KEEP) return conv(t);
    var kept = [];
    var m = t.replace(KEEP, function(x){ return "\u0001" + (kept.push(x) - 1) + "\u0002"; });
    return kept.length ? conv(m).replace(/\u0001(\d+)\u0002/g, function(x, i){ return kept[+i]; }) : conv(t);
  }
  function conv(t){
    if (t === t.toUpperCase() && t !== t.toLowerCase()) return conv(t.toLowerCase()).toUpperCase();
    var words;
    if (LANG === "us") { S.us.forEach(function(x){ t = t.replace(x[0], function(m){ return fix(m, x[1], x[2]); }); }); words = S.us_words; }
    else if (LANG === "ca") {
      S.ca_gb.forEach(function(x){ t = t.replace(x[0], function(m){ return fix(m, x[1], x[2]); }); });
      S.ca_ize.forEach(function(x){ t = t.replace(x[0], function(m){ return fix(m, x[1], x[2]); }); });
      words = S.ca_words;
    } else { S.gb.forEach(function(x){ t = t.replace(x[0], function(m){ return fix(m, x[1], x[2]); }); }); words = S.gb_words; }
    words.forEach(function(x){ t = t.replace(x[0], x[1]); });
    return t;
  }
  window.btLang = {lang: LANG, convert: convert};
  var SKIP = {SCRIPT: 1, STYLE: 1, TEXTAREA: 1, INPUT: 1, CODE: 1, svg: 1, SVG: 1};
  function skipped(el){
    for (; el && el.nodeType === 1; el = el.parentNode) {
      if (SKIP[el.tagName] || el.hasAttribute("data-nolang")) return true;
    }
    return false;
  }
  function doText(n){
    if (skipped(n.parentNode)) return;
    var v = convert(n.nodeValue);
    if (v !== n.nodeValue) n.nodeValue = v;
  }
  function doEl(el){
    if (skipped(el)) return;
    ["placeholder", "title", "aria-label"].forEach(function(a){
      if (el.hasAttribute(a)) { var v = convert(el.getAttribute(a)); if (v !== el.getAttribute(a)) el.setAttribute(a, v); }
    });
  }
  function walk(root){
    if (root.nodeType === 3) return doText(root);
    if (root.nodeType !== 1 || skipped(root)) return;
    doEl(root);
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (var n = w.nextNode(); n; n = w.nextNode()) { if (n.nodeType === 3) doText(n); else doEl(n); }
  }
  /* pop-up questions too */
  var C = window.confirm, A = window.alert, P = window.prompt;
  window.confirm = function(m){ return C.call(window, convert(m)); };
  window.alert = function(m){ return A.call(window, convert(m)); };
  window.prompt = function(m, d){ return P.call(window, convert(m), d); };
  function start(){
    document.title = convert(document.title);
    walk(document.body);
    new MutationObserver(function(list){
      list.forEach(function(m){
        if (m.type === "characterData") doText(m.target);
        else if (m.type === "attributes") doEl(m.target);
        else m.addedNodes.forEach(walk);
      });
    }).observe(document.body, {childList: true, subtree: true, characterData: true,
                               attributes: true, attributeFilter: ["placeholder", "title", "aria-label"]});
  }
  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);
})();
