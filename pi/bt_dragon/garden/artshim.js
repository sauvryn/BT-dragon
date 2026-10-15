/* BT Dragon: the art-only copy of Bookworm's page, loaded unseen by the Den to draw the larvae.
   It must never touch the Garden Collection's save, so Bookworm's own saving does nothing here. */
(function(){
  try { sessionStorage.setItem("bookworm-splashed", "1"); } catch (e) {}
  var setItem = Storage.prototype.setItem, removeItem = Storage.prototype.removeItem;
  Storage.prototype.setItem = function(k, v){ if (String(k).indexOf("bookworm") !== 0) setItem.call(this, k, v); };
  Storage.prototype.removeItem = function(k){ if (String(k).indexOf("bookworm") !== 0) removeItem.call(this, k); };
})();
