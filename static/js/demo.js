(() => {
  const panels = [...document.querySelectorAll('[data-demo-panel]')];
  const progress = [...document.querySelectorAll('[data-progress]')];
  const storageKey = 'movix_demo_profile';
  const state = { user: null, provider: null, form: {}, vehicle: '', capacity: '' };
  let searchTimer;

  const initials = name => name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0].toUpperCase()).join('') || 'MV';
  const firstName = name => name.trim().split(/\s+/)[0] || 'Invitado';

  const showPanel = name => {
    panels.forEach(panel => panel.classList.toggle('is-active', panel.dataset.demoPanel === name));
    const sequence = ['auth', 'request', 'vehicle', 'tracking'];
    const currentIndex = sequence.indexOf(name);
    progress.forEach((item, index) => {
      item.classList.toggle('active', index === currentIndex);
      item.classList.toggle('done', index < currentIndex);
    });
  };

  const enterDemo = provider => {
    const input = document.getElementById('demoName');
    const name = input?.value.trim() || 'Invitado MOVIX';
    state.user = name;
    state.provider = provider;
    localStorage.setItem(storageKey, JSON.stringify({name, provider}));
    document.querySelectorAll('[data-demo-user]').forEach(item => { item.textContent = firstName(name); });
    document.querySelectorAll('[data-demo-initials]').forEach(item => { item.textContent = initials(name); });
    showPanel('request');
  };

  document.querySelectorAll('[data-demo-login]').forEach(button => button.addEventListener('click', () => {
    button.disabled = true;
    const original = button.innerHTML;
    button.textContent = 'Preparando la demostración...';
    window.setTimeout(() => {
      enterDemo(button.dataset.demoLogin);
      button.disabled = false;
      button.innerHTML = original;
    }, 650);
  }));

  document.getElementById('demoRequestForm')?.addEventListener('submit', event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    state.form = Object.fromEntries(data.entries());
    showPanel('vehicle');
  });

  document.querySelectorAll('[data-demo-vehicle]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-demo-vehicle]').forEach(item => item.classList.remove('selected'));
    button.classList.add('selected');
    state.vehicle = button.dataset.demoVehicle;
    state.capacity = button.dataset.demoCapacity;
    document.querySelector('[data-confirm-vehicle]').disabled = false;
  }));

  document.querySelector('[data-confirm-vehicle]')?.addEventListener('click', () => {
    if (!state.vehicle) return;
    const searching = document.querySelector('[data-searching]');
    const accepted = document.querySelector('[data-accepted]');
    searching.hidden = false;
    accepted.hidden = true;
    showPanel('tracking');
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      searching.hidden = true;
      accepted.hidden = false;
      document.querySelector('[data-summary-service]').textContent = state.form.service || 'Transporte';
      document.querySelector('[data-summary-vehicle]').textContent = `${state.vehicle} · ${state.capacity}`;
      document.querySelector('[data-summary-route]').textContent = `${state.form.origin} → ${state.form.destination}`;
      document.querySelector('[data-summary-payment]').textContent = state.form.payment || 'Efectivo';
    }, 2500);
  });

  document.querySelectorAll('[data-demo-back]').forEach(button => button.addEventListener('click', () => showPanel(button.dataset.demoBack)));
  document.querySelector('[data-new-request]')?.addEventListener('click', () => {
    state.vehicle = '';
    document.querySelectorAll('[data-demo-vehicle]').forEach(item => item.classList.remove('selected'));
    document.querySelector('[data-confirm-vehicle]').disabled = true;
    showPanel('request');
  });

  const reset = () => {
    window.clearTimeout(searchTimer);
    localStorage.removeItem(storageKey);
    state.user = null; state.provider = null; state.form = {}; state.vehicle = '';
    document.querySelectorAll('[data-demo-vehicle]').forEach(item => item.classList.remove('selected'));
    document.querySelector('[data-confirm-vehicle]').disabled = true;
    showPanel('auth');
  };
  document.querySelector('[data-demo-reset]')?.addEventListener('click', reset);

  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (saved?.name) {
      document.getElementById('demoName').value = saved.name;
      enterDemo(saved.provider || 'Invitado');
    }
  } catch (_) { localStorage.removeItem(storageKey); }
})();
