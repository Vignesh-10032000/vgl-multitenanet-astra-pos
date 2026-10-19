(function () {
  var fmt = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var inr = function (n) { return '₹' + fmt.format(n); };
  var P = [
    { id: 'rice', n: 'Ponni Rice', u: '5 kg', p: 310, g: 5, c: 'R', bg: '#BFE8D2' },
    { id: 'oil', n: 'Groundnut Oil', u: '1 L', p: 185, g: 5, c: 'O', bg: '#F6DFA8' },
    { id: 'cof', n: 'Filter Coffee', u: '200 g', p: 125, g: 5, c: 'C', bg: '#E6CDB8', low: true },
    { id: 'dal', n: 'Toor Dal', u: '1 kg', p: 165, g: 5, c: 'T', bg: '#F3D1A0', low: true },
    { id: 'det', n: 'Detergent Powder', u: '500 g', p: 98, g: 18, c: 'D', bg: '#BBD3F7', low: true },
    { id: 'wat', n: 'Mineral Water', u: '1 L', p: 20, g: 18, c: 'W', bg: '#BDE6F2' }
  ];
  var byId = {}; P.forEach(function (x) { byId[x.id] = x; });
  var cart = { rice: 1, oil: 1 }, sales = 8420, bills = 24, no = 824, paid = false, timer = null;
  var $ = function (id) { return document.getElementById(id); };

  function calc() {
    var sub = 0, tax = {}, taxTotal = 0;
    Object.keys(cart).forEach(function (id) {
      var q = cart[id]; if (!q) return;
      var it = byId[id], line = it.p * q; sub += line;
      var t = Math.round(line * it.g) / 100; tax[it.g] = (tax[it.g] || 0) + t; taxTotal += t;
    });
    return { sub: sub, tax: tax, total: Math.round((sub + taxTotal) * 100) / 100 };
  }

  function render() {
    $('prods').innerHTML = P.map(function (x) {
      return '<button class="prod" type="button" data-add="' + x.id + '"' + (paid ? ' disabled' : '') + '>' +
        '<span class="glyph glyph-' + x.id + '">' + x.c + '</span>' +
        '<span><b>' + x.n + (x.low ? '<span class="low">LOW</span>' : '') + '</b><small>' + x.u + '</small></span>' +
        '<span class="pr">₹' + x.p + '</span></button>';
    }).join('');

    var ids = Object.keys(cart).filter(function (id) { return cart[id] > 0; });
    $('lines').innerHTML = ids.length ? ids.map(function (id) {
      var it = byId[id], q = cart[id];
      return '<div class="line"><div class="nm">' + it.n + '<small>' + it.u + ' · ₹' + it.p + '</small></div>' +
        '<div class="qty"><button type="button" data-dec="' + id + '" aria-label="Decrease"' + (paid ? ' disabled' : '') + '>−</button><span>' + q + '</span><button type="button" data-inc="' + id + '" aria-label="Increase"' + (paid ? ' disabled' : '') + '>+</button></div>' +
        '<div class="amt num">' + fmt.format(it.p * q) + '</div></div>';
    }).join('') : '<div class="empty">Tap a product on the left to start the bill.</div>';

    var c = calc();
    var rows = '';
    if (ids.length) {
      rows += '<div><span>Subtotal</span><span>' + fmt.format(c.sub) + '</span></div>';
      Object.keys(c.tax).sort(function (a, b) { return a - b; }).forEach(function (r) {
        rows += '<div><span>GST (' + r + '%)</span><span>' + fmt.format(c.tax[r]) + '</span></div>';
      });
    }
    $('sums').innerHTML = rows;
    $('sums').hidden = !ids.length;
    $('total').textContent = inr(c.total);
    $('billno').textContent = '#DEMO-' + no;
    var pay = $('pay');
    pay.disabled = !ids.length || paid;
    pay.classList.toggle('done', paid);
    pay.textContent = paid ? '✓ Payment received · UPI' : (ids.length ? 'Collect ' + inr(c.total) + ' via UPI' : 'Collect via UPI');
    $('note').textContent = paid ? 'Bill saved. Starting the next one…' : 'A clear bill. A confident checkout.';
    $('k-sales').textContent = '₹' + new Intl.NumberFormat('en-IN').format(Math.round(sales));
    $('k-bills').textContent = bills;
  }

  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-add],[data-inc],[data-dec]');
    if (!t || paid) return;
    var id = t.getAttribute('data-add') || t.getAttribute('data-inc') || t.getAttribute('data-dec');
    if (t.hasAttribute('data-dec')) { cart[id] = Math.max(0, (cart[id] || 0) - 1); if (!cart[id]) delete cart[id]; }
    else { cart[id] = Math.min(99, (cart[id] || 0) + 1); }
    render();
  });

  $('pay').addEventListener('click', function () {
    var c = calc(); if (!c.total || paid) return;
    var doneNo = no; paid = true; sales += c.total; bills += 1; render();
    $('f-amt').textContent = inr(c.total); $('f-bill').textContent = 'Bill #DEMO-' + doneNo + ' · just now';
    clearTimeout(timer);
    timer = setTimeout(function () { cart = {}; paid = false; no += 1; render(); }, 2200);
  });

  /* password toggle */
  $('toggle').addEventListener('click', function () {
    var p = $('pass'), show = p.type === 'password';
    p.type = show ? 'text' : 'password';
    this.textContent = show ? 'Hide' : 'Show';
    this.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  });

  /* copy buttons */
  document.querySelectorAll('[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () {
      var el = $(b.getAttribute('data-copy')), txt = el.textContent.trim();
      var done = function () { b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy'; }, 1600); };
      var fallback = function () {
        var r = document.createRange(); r.selectNodeContents(el);
        var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
        b.textContent = 'Selected'; setTimeout(function () { b.textContent = 'Copy'; }, 1600);
      };
      try { navigator.clipboard.writeText(txt).then(done, fallback); } catch (err) { fallback(); }
    });
  });

  /* English / Tamil */
  var T = {
    en: {
      nav_features: 'Features', nav_dash: 'Dashboard', nav_access: 'Team access', nav_contact: 'Contact', nav_signin: 'Sign in',
      pill: 'Built for Indian retail',
      h1: 'Run the whole store from <em>one fast counter.</em>',
      lede: 'VGL POS brings billing, stock, customers and GST reports into a single workspace, built for Indian retail and ready in English and Tamil.',
      cta_demo: 'Try the live demo', cta_signin: 'Sign in to your store',
      feat_h: "Everything the counter needs, nothing it doesn't.",
      signin_h: 'Store team sign in', f_company: 'Company code', f_user: 'Username', f_pass: 'Password',
      f_branch: 'Branch ID', f_term: 'Terminal ID', btn_signin: 'Sign in', lang: 'தமிழ்'
    },
    ta: {
      nav_features: 'அம்சங்கள்', nav_dash: 'டாஷ்போர்டு', nav_access: 'குழு அணுகல்', nav_contact: 'தொடர்புக்கு', nav_signin: 'உள்நுழை',
      pill: 'இந்திய சில்லறை வணிகத்திற்காக',
      h1: 'ஒரே கவுண்டரில் <em>முழு கடையையும் நிர்வகியுங்கள்.</em>',
      lede: 'பில்லிங், ஸ்டாக், வாடிக்கையாளர்கள், GST அறிக்கைகள் அனைத்தும் ஒரே இடத்தில். இந்திய சில்லறை வணிகத்திற்காக தமிழிலும் ஆங்கிலத்திலும்.',
      cta_demo: 'டெமோவை முயற்சிக்கவும்', cta_signin: 'உங்கள் கடைக்கு உள்நுழைக',
      feat_h: 'கவுண்டருக்குத் தேவையான அனைத்தும், தேவையற்றது எதுவுமில்லை.',
      signin_h: 'கடை குழு உள்நுழைவு', f_company: 'நிறுவன குறியீடு', f_user: 'பயனர் பெயர்', f_pass: 'கடவுச்சொல்',
      f_branch: 'கிளை ஐடி', f_term: 'டெர்மினல் ஐடி', btn_signin: 'உள்நுழை', lang: 'English'
    }
  };
  var lang = 'en';
  function apply() {
    var d = T[lang];
    document.documentElement.lang = lang;
    document.querySelectorAll('[data-i18n]').forEach(function (el) { el.textContent = d[el.getAttribute('data-i18n')]; });
    document.querySelectorAll('[data-i18n-html]').forEach(function (el) { el.innerHTML = d[el.getAttribute('data-i18n-html')]; });
    $('lang').textContent = d.lang;
  }
  $('lang').addEventListener('click', function () { lang = lang === 'en' ? 'ta' : 'en'; apply(); });

  render();
})();
