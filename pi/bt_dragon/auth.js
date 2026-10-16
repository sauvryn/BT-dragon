// The Den password (denauth.py): if a page's ticket runs out while it's open, the next thing
// it asks for comes back "401: log in", and this takes you to the login page instead of the page
// quietly failing.
(function () {
  const real = window.fetch;
  window.fetch = async function (...args) {
    const r = await real.apply(this, args);
    if (r.status === 401 && location.pathname !== '/login') {
      try { if ((await r.clone().json()).error === 'login') location.href = '/login'; } catch (e) {}
    }
    return r;
  };
})();
