/* BT Dragon: Bookworm's page as Harald's Garden Collection. Only the Collection and Habitats
   show (no reading, shelf or achievements), with buttons between them. The Habitats view is
   "#habitats" on the address, so the browser's back button works too. */
(function(){
  var G = window.__GARDEN || {}, name = G.name || "Harald";
  var $ = function(id){ return document.getElementById(id); };
  document.documentElement.setAttribute("data-theme", "dark");
  document.title = name + "'s Butterfly Garden";
  var wm = document.querySelector(".wordmark");
  if (wm) { wm.textContent = name + "'s Butterfly Garden"; wm.setAttribute("aria-label", wm.textContent); }
  window.__garden.setTitles(G.titleNames || []);
  window.__garden.showColl();

  /* Bookworm's wording is about books; here everything was raised in the garden */
  var intro = document.querySelector("#species-view > p.muted.small");
  if (intro && intro.firstChild && intro.firstChild.nodeType === 3)
    intro.firstChild.textContent = "Each adult raised in " + name + "'s Butterfly Garden joins the collection. Tap any species to read its summary and to mark if you've seen it in the wild. ";
  var hp = document.querySelector("#hab-view > p.muted.small");
  if (hp) hp.textContent = "Each species raised in the garden unlocks one habitat: the first one on its species card that's still locked. Tap an unlocked habitat to see which insects live there.";

  var nav = document.createElement("div");
  nav.className = "garden-nav";
  nav.innerHTML = '<button type="button" id="gd-to-hab">See Habitats</button>';
  $("species-view").appendChild(nav);
  var back = document.createElement("div");
  back.className = "garden-nav top";
  back.innerHTML = '<button type="button" id="gd-back">Go back to Collection</button>';
  $("hab-view").insertBefore(back, $("hab-view").firstChild);

  function follow(){
    var hab = location.hash === "#habitats";
    $(hab ? "cv-habitats" : "cv-species").click();
    window.scrollTo(0, 0);
  }
  var pushed = false;
  $("gd-to-hab").onclick = function(){ pushed = true; location.hash = "habitats"; };
  $("gd-back").onclick = function(){
    if (pushed) { pushed = false; history.back(); }       /* undo our own step: the back button stays tidy */
    else { history.replaceState(null, "", location.pathname + location.search); follow(); }
  };
  window.addEventListener("hashchange", follow);
  if (location.hash === "#habitats") follow();
  /* the Den's larva cards open "?notes=<species>": that species' field notes */
  /* with "&stage=<0-10>&mood=<content|hungry|xhungry>", the larva's own picture at the top, crawling */
  var Q = new URLSearchParams(location.search), q = Q.get("notes");
  if (q && window.__garden.notes(q)) {
    var old = document.getElementById("gd-notes-art");
    if (old) old.remove();
    if (Q.get("stage") !== null) {
      var st = Math.max(0, Math.min(10, +Q.get("stage") || 0));
      var art = document.createElement("div");
      art.id = "gd-notes-art";
      art.className = "art-wrap" + (st < 9 ? " crawl" : "");
      art.innerHTML = window.__garden.art(q, st, Q.get("mood") || "content");
      var sheet = document.querySelector("#m-notes .sheet");
      sheet.insertBefore(art, sheet.children[1]);
    }
  }
})();
