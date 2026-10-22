/* The Tadpole Pond's placeholder art, for the Den and the Pond Collection page (/pond-art.js).
   Grey, with TEMP across it, in the same style as the Butterfly Garden's placeholder art
   (Bookworm's): the same greys, the same 320 x 210 picture and the same tilted TEMP, until
   there's real artwork. stage: 0 spawn, 1 tadpole or larva, 2 back legs (frogs and toads) or
   front legs (newts and salamanders), 3 four legs, 4 froglet, toadlet, eft or juvenile, 5 grown up. */
(function () {
  var SHADE = {frog: ['#a9a9a9', '#4a4a4a'], toad: ['#8f8f8f', '#3f3f3f'], newt: ['#b9b9b9', '#555555'],
               salamander: ['#9a9a9a', '#3a3a3a']};
  var INK = '#2b2b2b', LINE = '#7a7a7a';
  var TEMP = '<g pointer-events="none" aria-hidden="true"><text x="160" y="116" text-anchor="middle" dominant-baseline="middle" ' +
    'font-family="Arial, Helvetica, sans-serif" font-size="60" font-weight="900" letter-spacing="8" fill="#7a7a7a" ' +
    'fill-opacity=".42" stroke="#fff" stroke-opacity=".55" stroke-width="1.5" transform="rotate(-14 160 116)">TEMP</text></g>';
  var NAMES = {0: 'spawn', 1: 'young', 2: 'growing legs', 3: 'four legs', 4: 'leaving the water', 5: 'grown up'};

  function pondArt(kind, stage) {
    var sh = SHADE[kind] || SHADE.frog, c = sh[0], d = sh[1];
    var newtish = kind === 'newt' || kind === 'salamander';
    var g = '';
    var leg = function (x, y, dx, dy) {
      return '<path d="M' + x + ' ' + y + ' l' + dx + ' ' + dy + ' l' + (dx > 0 ? 3 : -3) + ' 1" stroke="' + INK +
        '" stroke-width="2.6" fill="none" stroke-linecap="round"/>';
    };
    var water = '<path d="M6 20 Q34 14 60 20 T114 20" stroke="' + LINE + '" stroke-width="1" fill="none"/>';
    if (stage === 0) {
      [[40, 44], [52, 40], [64, 46], [48, 54], [60, 56], [72, 52], [56, 34], [70, 38], [44, 32], [80, 44]].forEach(function (p) {
        g += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="7" fill="#d4d4d4" fill-opacity=".7" stroke="' + LINE + '" stroke-width=".8"/>' +
             '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="2.4" fill="' + INK + '"/>';
      });
    } else if (!newtish && stage <= 4) {                 // a tadpole: back legs, then front, then a froglet or toadlet
      var tail = stage === 4 ? 10 : 34;
      g += '<path d="M' + (46 - tail) + ' 42 Q' + (54 - tail / 2) + ' ' + (stage === 4 ? 40 : 34) + ' 52 40" stroke="' + INK +
           '" stroke-width="1" fill="' + d + '" fill-opacity=".6"/>';
      if (stage >= 2) g += leg(54, 46, -6, 8) + leg(58, 46, 4, 9);
      if (stage >= 3) g += leg(70, 46, 4, 7) + leg(66, 46, -2, 8);
      g += '<ellipse cx="' + (stage === 4 ? 64 : 62) + '" cy="40" rx="' + (stage === 4 ? 13 : 12) + '" ry="9" fill="' + c +
           '" stroke="' + INK + '" stroke-width="1.6"/>';
      g += '<circle cx="70" cy="36" r="2" fill="' + INK + '"/>' + (stage === 4 ? '<circle cx="66" cy="34" r="2" fill="' + INK + '"/>' : '');
    } else if (newtish && stage <= 4) {                  // a larva: feathery gills, front legs, back legs, then an eft or juvenile
      if (stage < 4) g += '<path d="M24 44 Q36 34 52 39" stroke="' + d + '" stroke-opacity=".5" stroke-width="10" fill="none"/>';
      g += '<path d="M24 44 Q40 ' + (stage === 4 ? 42 : 38) + ' 56 42 Q72 46 84 42" stroke="' + INK + '" stroke-width="' +
           (stage === 4 ? 9 : 8) + '" fill="none" stroke-linecap="round"/>';
      g += '<path d="M24 44 Q40 ' + (stage === 4 ? 42 : 38) + ' 56 42 Q72 46 84 42" stroke="' + c + '" stroke-width="' +
           (stage === 4 ? 6 : 5) + '" fill="none" stroke-linecap="round"/>';
      if (stage < 4) g += '<path d="M89 38 l6 -6 M89 42 l8 -1 M89 46 l6 6" stroke="' + d + '" stroke-width="2" stroke-linecap="round"/>';
      if (stage >= 2) g += leg(76, 45, 3, 8) + leg(72, 45, -3, 8);
      if (stage >= 3) g += leg(50, 44, 3, 8) + leg(46, 44, -3, 8);
      g += '<ellipse cx="86" cy="42" rx="6" ry="5" fill="' + c + '" stroke="' + INK + '" stroke-width="1.4"/><circle cx="88" cy="40" r="1.6" fill="' + INK + '"/>';
    } else if (!newtish) {                               // grown up: a frog or a toad, on a lily pad
      var bumps = '';
      if (kind === 'toad') [[52, 34], [60, 30], [68, 33], [57, 40], [66, 40]].forEach(function (p) {
        bumps += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="2" fill="' + d + '"/>';
      });
      g += '<ellipse cx="60" cy="56" rx="34" ry="9" fill="#bdbdbd" stroke="' + LINE + '" stroke-width="1"/>' +
        '<path d="M44 52 q-10 -2 -12 4 M76 52 q10 -2 12 4" stroke="' + INK + '" stroke-width="5" fill="none" stroke-linecap="round"/>' +
        '<ellipse cx="60" cy="40" rx="18" ry="13" fill="' + c + '" stroke="' + INK + '" stroke-width="1.6"/>' + bumps +
        '<circle cx="51" cy="28" r="5" fill="' + c + '" stroke="' + INK + '" stroke-width="1.4"/><circle cx="69" cy="28" r="5" fill="' + c +
        '" stroke="' + INK + '" stroke-width="1.4"/><circle cx="51" cy="27" r="2.2" fill="' + INK + '"/><circle cx="69" cy="27" r="2.2" fill="' + INK + '"/>' +
        '<path d="M54 44 q6 4 12 0" stroke="' + INK + '" stroke-width="1.5" fill="none"/>';
    } else {                                             // grown up: a newt or a salamander, on a bank
      var spots = '';
      if (kind === 'salamander') [[40, 47], [54, 45], [68, 47], [80, 45]].forEach(function (p) {
        spots += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="2.2" fill="#e6e6e6"/>';
      });
      g += '<ellipse cx="60" cy="58" rx="40" ry="7" fill="#bdbdbd" stroke="' + LINE + '" stroke-width="1"/>' +
        '<path d="M18 50 Q34 40 52 46 Q70 50 86 46" stroke="' + INK + '" stroke-width="12" fill="none" stroke-linecap="round"/>' +
        '<path d="M18 50 Q34 40 52 46 Q70 50 86 46" stroke="' + c + '" stroke-width="9" fill="none" stroke-linecap="round"/>' + spots +
        leg(74, 49, 4, 7) + leg(70, 49, -4, 7) + leg(46, 47, 4, 7) + leg(42, 47, -4, 7) +
        '<ellipse cx="90" cy="45" rx="7" ry="5.5" fill="' + c + '" stroke="' + INK + '" stroke-width="1.4"/><circle cx="92" cy="43" r="1.6" fill="' + INK + '"/>';
    }
    return '<svg class="art" viewBox="0 0 320 210" role="img" aria-label="' + (kind || 'amphibian') + ', ' + NAMES[stage] +
      ' (placeholder art)"><g transform="translate(16 9) scale(2.4)">' + water + g + '</g>' + TEMP + '</svg>';
  }
  window.pondArt = pondArt;
})();
