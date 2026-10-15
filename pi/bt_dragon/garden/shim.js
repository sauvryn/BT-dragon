/* BT Dragon: runs before Bookworm's own script. Bookworm keeps its save in this browser's
   storage; here the save comes from Harald's Butterfly Garden on the Pi instead, written in
   just before Bookworm reads it. The only thing sent back is what you tick in "I've Seen It!". */
(function(){
  var D = __GARDEN_DATA__;
  window.__GARDEN = {name: D.name, country: D.country, titleNames: D.titleNames || []};
  try {
    localStorage.setItem("bookworm-country", D.country);
    localStorage.setItem("bookworm-lang", D.lang);
    localStorage.removeItem("bookworm-merged");
    /* every country's save, so Bookworm's score (which counts all countries) is right */
    var saves = D.saves || {}; saves[D.key] = saves[D.key] || D.save;
    for (var k in saves) localStorage.setItem(k, JSON.stringify(saves[k]));
    localStorage.setItem("bookworm-titles", JSON.stringify(D.titles || {}));
    sessionStorage.setItem("bookworm-splashed", "1");
  } catch (e) {}
  var mine = (D.saves && D.saves[D.key]) || D.save || {};
  var last = JSON.stringify([mine.seen || {}, mine.seenDates || {}]);
  var setItem = Storage.prototype.setItem;
  Storage.prototype.setItem = function(k, v) {
    setItem.call(this, k, v);
    if (this !== window.localStorage || k !== D.key) return;
    try {
      var s = JSON.parse(v), now = JSON.stringify([s.seen || {}, s.seenDates || {}]);
      if (now === last) return;
      last = now;
      fetch("/api/garden/seen", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({country: D.country, seen: s.seen || {}, seenDates: s.seenDates || {}})});
    } catch (e) {}
  };
})();
