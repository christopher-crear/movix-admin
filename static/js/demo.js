(() => {
  const panels = [...document.querySelectorAll('[data-demo-panel]')];
  const progress = [...document.querySelectorAll('[data-progress]')];
  const state = {
    user: 'Lucía Demo',
    provider: 'Invitado',
    vehicle: '',
    capacity: '',
    price: '',
    cargo: {},
    location: {},
    payment: ''
  };
  let toastTimer;

  const firstName = name => (name || 'Lucía Demo').trim().split(/\s+/)[0] || 'Lucía';

  const showToast = message => {
    const toast = document.querySelector('.demo-toast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove('show'), 2200);
  };

  const showPanel = name => {
    let currentStep = 0;
    panels.forEach(panel => {
      const active = panel.dataset.demoPanel === name;
      panel.classList.toggle('is-active', active);
      if (active) {
        currentStep = Number(panel.dataset.step || 0);
        panel.scrollTop = 0;
      }
    });
    progress.forEach((item, index) => {
      item.classList.toggle('active', index === currentStep);
      item.classList.toggle('done', index < currentStep);
    });
  };

  const fillSummary = () => {
    const values = {
      '[data-summary-vehicle]': `${state.vehicle} · ${state.capacity}`,
      '[data-summary-cargo]': `${state.cargo.cargoType || 'Muebles'} · ${state.cargo.weight || '85'} kg`,
      '[data-summary-origin]': state.location.origin || 'Parque Jipiro, Loja',
      '[data-summary-destination]': state.location.destination || 'Sector La Tebaida, Loja',
      '[data-summary-payment]': state.payment || 'Efectivo',
      '[data-offer-origin]': state.location.origin || 'Parque Jipiro, Loja',
      '[data-offer-destination]': state.location.destination || 'Sector La Tebaida, Loja',
      '[data-offer-cargo]': state.cargo.cargoType || 'Muebles'
    };
    Object.entries(values).forEach(([selector, value]) => {
      document.querySelectorAll(selector).forEach(node => { node.textContent = value; });
    });
  };

  const enterDemo = provider => {
    const input = document.getElementById('demoName');
    state.user = input?.value.trim() || 'Lucía Demo';
    state.provider = provider;
    document.querySelectorAll('[data-demo-user]').forEach(node => { node.textContent = firstName(state.user); });
    showPanel('home');
    showToast(`Perfil temporal iniciado como ${firstName(state.user)}`);
  };

  document.querySelectorAll('[data-demo-login]').forEach(button => {
    button.addEventListener('click', () => {
      const label = button.innerHTML;
      button.disabled = true;
      button.textContent = 'Preparando demo...';
      window.setTimeout(() => {
        enterDemo(button.dataset.demoLogin);
        button.disabled = false;
        button.innerHTML = label;
      }, 450);
    });
  });

  document.querySelectorAll('[data-nav]').forEach(button => {
    button.addEventListener('click', () => showPanel(button.dataset.nav));
  });

  document.querySelectorAll('[data-demo-toast]').forEach(button => {
    button.addEventListener('click', () => showToast(button.dataset.demoToast));
  });

  document.querySelectorAll('[data-demo-vehicle]').forEach(button => {
    button.addEventListener('click', () => {
      document.querySelectorAll('[data-demo-vehicle]').forEach(node => node.classList.remove('selected'));
      button.classList.add('selected');
      state.vehicle = button.dataset.demoVehicle;
      state.capacity = button.dataset.capacity;
      state.price = button.dataset.price;
      document.querySelectorAll('[data-selected-vehicle]').forEach(node => { node.textContent = state.vehicle; });
      document.querySelectorAll('[data-route-price]').forEach(node => { node.textContent = state.price; });
      document.querySelector('[data-confirm-vehicle]').disabled = false;
    });
  });

  document.querySelector('[data-confirm-vehicle]')?.addEventListener('click', () => {
    if (state.vehicle) showPanel('cargo');
  });

  document.getElementById('demoCargoForm')?.addEventListener('submit', event => {
    event.preventDefault();
    state.cargo = Object.fromEntries(new FormData(event.currentTarget).entries());
    state.cargo.helpers = event.currentTarget.elements.helpers.checked ? 'Sí' : 'No';
    showPanel('location');
  });

  document.getElementById('demoLocationForm')?.addEventListener('submit', event => {
    event.preventDefault();
    state.location = Object.fromEntries(new FormData(event.currentTarget).entries());
    showPanel('payment');
  });

  document.querySelectorAll('[data-payment]').forEach(button => {
    button.addEventListener('click', () => {
      document.querySelectorAll('[data-payment]').forEach(node => node.classList.remove('selected'));
      button.classList.add('selected');
      state.payment = button.dataset.payment;
      const bank = document.querySelector('[data-bank-demo]');
      bank.hidden = state.payment !== 'Transferencia demo';
      document.querySelector('[data-submit-demo]').disabled = false;
    });
  });

  document.querySelectorAll('[data-bank-demo] button').forEach(button => {
    button.addEventListener('click', () => {
      document.querySelectorAll('[data-bank-demo] button').forEach(node => node.classList.remove('selected'));
      button.classList.add('selected');
    });
  });

  document.querySelector('[data-submit-demo]')?.addEventListener('click', () => {
    fillSummary();
    showPanel('success');
  });

  const reset = () => {
    state.user = 'Lucía Demo';
    state.provider = 'Invitado';
    state.vehicle = '';
    state.capacity = '';
    state.price = '';
    state.cargo = {};
    state.location = {};
    state.payment = '';
    const nameInput = document.getElementById('demoName');
    if (nameInput) nameInput.value = 'Lucía Demo';
    document.querySelectorAll('[data-demo-vehicle],[data-payment]').forEach(node => node.classList.remove('selected'));
    document.querySelector('[data-confirm-vehicle]').disabled = true;
    document.querySelector('[data-submit-demo]').disabled = true;
    document.querySelector('[data-bank-demo]').hidden = true;
    document.getElementById('demoCargoForm')?.reset();
    document.getElementById('demoLocationForm')?.reset();
    showPanel('auth');
    showToast('Demostración reiniciada');
  };

  document.querySelectorAll('[data-demo-reset]').forEach(button => button.addEventListener('click', reset));
})();
