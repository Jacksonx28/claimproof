(() => {
  const root = document.documentElement;
  let theme = 'dark';
  try { const saved = localStorage.getItem('downproof-theme'); if (['dark','light'].includes(saved)) theme = saved; } catch (_) {}
  root.dataset.theme = theme;
  document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('theme-toggle');
    function syncTheme() {
      if (!toggle) return;
      const dark = root.dataset.theme === 'dark';
      toggle.textContent = dark ? '☼' : '◐';
      toggle.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
      toggle.title = toggle.getAttribute('aria-label');
      document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#080e13' : '#f2f7f7');
    }
    syncTheme();
    toggle?.addEventListener('click', () => {
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('downproof-theme', root.dataset.theme); } catch (_) {}
      syncTheme();
    });
    const menu = document.getElementById('menu-toggle'), nav = document.getElementById('primary-nav');
    function closeMenu() { nav?.classList.remove('open'); menu?.setAttribute('aria-expanded','false'); menu?.setAttribute('aria-label','Open menu'); }
    menu?.addEventListener('click', () => { const open = nav.classList.toggle('open'); menu.setAttribute('aria-expanded',String(open)); menu.setAttribute('aria-label',open?'Close menu':'Open menu'); });
    nav?.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
    document.addEventListener('keydown', e => { if(e.key==='Escape'&&nav?.classList.contains('open')){closeMenu();menu.focus();} });
    document.addEventListener('click', e => { if(!e.target.closest('.site-header'))closeMenu(); const button=e.target.closest('button,.button'); if(button&&!button.disabled&&!matchMedia('(prefers-reduced-motion: reduce)').matches)button.animate([{scale:1},{scale:.96},{scale:1}],{duration:220,easing:'ease-out'}); });
    matchMedia('(min-width:851px)').addEventListener('change', e => {if(e.matches)closeMenu();});
    addEventListener('storage', e => {if(e.key==='downproof-theme'&&['dark','light'].includes(e.newValue)){root.dataset.theme=e.newValue;syncTheme();}});
  });
})();
