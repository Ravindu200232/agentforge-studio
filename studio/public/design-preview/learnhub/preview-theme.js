(() => {
  const hex = value => /^#[0-9a-f]{6}$/i.test(value || '');
  const rgb = value => [1, 3, 5].map(index => parseInt(value.slice(index, index + 2), 16));
  const font = value => /^[a-z0-9 -]{1,60}$/i.test(value || '') ? value : 'sans-serif';
  const root = document.documentElement;

  function loadFont(name) {
    const safe = font(name);
    if (safe === 'sans-serif') return;
    const id = `af-font-${safe.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
    if (document.getElementById(id)) return;
    const link = document.createElement('link');
    link.id = id;
    link.rel = 'stylesheet';
    link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(safe).replace(/%20/g, '+')}&display=swap`;
    document.head.appendChild(link);
  }

  window.addEventListener('message', event => {
    if (event.source !== window.parent || event.data?.type !== 'agentforge-design-preview') return;
    const { colors, headingFont, bodyFont } = event.data;
    if (!Array.isArray(colors) || colors.length !== 4 || !colors.every(hex)) return;
    const [primary, secondary, accent, surface] = colors;
    const channels = rgb(primary);
    const brightness = (channels[0] * 299 + channels[1] * 587 + channels[2] * 114) / 1000;
    root.style.setProperty('--af-primary', primary);
    root.style.setProperty('--af-primary-rgb', channels.join(', '));
    root.style.setProperty('--af-secondary', secondary);
    root.style.setProperty('--af-secondary-rgb', rgb(secondary).join(', '));
    root.style.setProperty('--af-accent', accent);
    root.style.setProperty('--af-surface', surface);
    root.style.setProperty('--af-on-primary', brightness > 150 ? '#171717' : '#ffffff');
    root.style.setProperty('--af-heading-font', `"${font(headingFont)}", sans-serif`);
    root.style.setProperty('--af-body-font', `"${font(bodyFont)}", sans-serif`);
    loadFont(headingFont);
    loadFont(bodyFont);
  });

  document.addEventListener('click', event => {
    if (event.target.closest('a')) event.preventDefault();
  }, true);
  document.addEventListener('submit', event => event.preventDefault(), true);
  window.parent.postMessage({ type: 'agentforge-design-preview-ready' }, '*');
})();
