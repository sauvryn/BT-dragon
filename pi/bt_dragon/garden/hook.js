/* BT Dragon: added inside Bookworm's script (just before its end), so these can reach its data. */
window.__garden = {
  country: COUNTRY,
  unlocks: UNLOCKS,
  habitatNames: function(){ var o = {}; HABITATS.forEach(function(h){ o[h.k] = h.name; }); return o; },
  dump: function(){
    return SPECIES.map(function(s){
      var K = KINDS[s.kind] || {};
      return {id: s.id, name: s.name, sci: s.sci, kind: s.kind, rarity: s.rarity, months: Array.from(s.months),
              pupAt: pupAt(s.id), forms: formsOf(s.id), caste: isCaste(s.id), habitats: habOf(s.id),
              noun: s.noun, young: K.young || "larva", pupa: K.pupa || "pupa"};
    });
  },
  /* the field notes for any species (Bookworm's own notes pop-up, which normally needs a book) */
  notes: function(id){
    var s = SP[id]; if (!s) return false;
    $("mn-h").textContent = s.name; $("mn-sci").textContent = s.sci; $("mn-kind").textContent = cap1(s.noun);
    var lc = function(t){ return t.charAt(0).toLowerCase() + t.slice(1); };
    var extra = DIMORPH[s.id] ? ["Males and females look different. Male: " + lc(DIMORPH[s.id][0]) + ". Female: " + lc(DIMORPH[s.id][1]) + "."]
      : isCaste(s.id) ? [formsOf(s.id).map(function(k){ return SEX_WORD[k] + ": " + lc(formDesc(s.id, k)) + "."; }).join(" "),
                         CASTE.why[casteGroup(s.id)].text] : [];
    $("mn-facts").innerHTML = s.facts.concat(extra).map(function(f){ return "<li>" + esc(f) + "</li>"; }).join("");
    renderLearn(s, "mn");
    $("m-notes").hidden = false;
    return true;
  },
  /* Bookworm's own larva, pupa and adult art: stage 0-8 a larva growing, 9 its pupa, 10 the adult.
     mood: "content", "hungry" or "xhungry" (a thought bubble with a leaf, and "!" when very hungry). */
  art: function(id, stage, mood){ return SP[id] ? artFor(+stage, mood || "content", id) : ""; },
  /* BT Dragon's own title names in place of Bookworm's (same points) */
  setTitles: function(names){
    TITLES.forEach(function(t, i){ if (names[i]) t.name = names[i]; });
    try { renderScore(); } catch (e) {}
  },
  species: function(id){ if (SP[id]) openSpecies(id); },
  showColl: function(){ tab = "coll"; show(); }
};

/* a species card lists each one raised; garden ones have no author or page count to show */
(function(){
  var orig = openSpecies;
  openSpecies = function(id){
    orig(id);
    $("ms-kv").innerHTML = $("ms-kv").innerHTML.replace(/% of the book/g, "% of its food");
    $("ms-list").querySelectorAll(".small.muted").forEach(function(el){
      el.innerHTML = el.innerHTML.replace(/ · Unknown author · <span class="mono">0 pp<\/span>/, "");
    });
  };
})();
