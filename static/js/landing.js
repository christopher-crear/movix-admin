(() => {
  const header = document.querySelector('[data-header]');
  const nav = document.querySelector('[data-nav]');
  const navToggle = document.querySelector('[data-nav-toggle]');

  const updateHeader = () => header?.classList.toggle('scrolled', window.scrollY > 18);
  updateHeader();
  window.addEventListener('scroll', updateHeader, {passive: true});

  const closeNav = () => {
    nav?.classList.remove('open');
    document.body.classList.remove('menu-open');
    navToggle?.setAttribute('aria-expanded', 'false');
  };
  navToggle?.addEventListener('click', () => {
    const open = nav?.classList.toggle('open');
    document.body.classList.toggle('menu-open', Boolean(open));
    navToggle.setAttribute('aria-expanded', String(Boolean(open)));
  });
  nav?.querySelectorAll('a').forEach(link => link.addEventListener('click', closeNav));

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const revealItems = document.querySelectorAll('.reveal');
  if (reduceMotion || !('IntersectionObserver' in window)) {
    revealItems.forEach(item => item.classList.add('visible'));
  } else {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, {threshold: .12, rootMargin: '0px 0px -45px'});
    revealItems.forEach((item, index) => {
      item.style.transitionDelay = `${Math.min(index % 4, 3) * 70}ms`;
      observer.observe(item);
    });
  }

  if (!reduceMotion && window.matchMedia('(pointer:fine)').matches) {
    document.querySelectorAll('[data-tilt]').forEach(card => {
      card.addEventListener('pointermove', event => {
        const rect = card.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - .5;
        const y = (event.clientY - rect.top) / rect.height - .5;
        card.style.transform = `perspective(850px) rotateX(${-y * 5}deg) rotateY(${x * 6}deg) translateY(-5px)`;
      });
      card.addEventListener('pointerleave', () => {
        card.style.transform = '';
      });
    });
  }

  document.querySelectorAll('[data-contact-type]').forEach(link => link.addEventListener('click', () => {
    const select = document.getElementById('id_request_type');
    if (select) select.value = link.dataset.contactType;
  }));

  const message = document.getElementById('id_message');
  const messageCount = document.querySelector('[data-message-count]');
  const updateCount = () => { if (messageCount) messageCount.textContent = String(message?.value.length || 0); };
  message?.addEventListener('input', updateCount);
  updateCount();

  document.querySelectorAll('.faq-list details').forEach(item => item.addEventListener('toggle', () => {
    if (!item.open) return;
    document.querySelectorAll('.faq-list details[open]').forEach(other => {
      if (other !== item) other.removeAttribute('open');
    });
  }));

  document.querySelector('[data-contact-form]')?.addEventListener('submit', event => {
    const form = event.currentTarget;
    if (!form.checkValidity()) return;
    const button = form.querySelector('button[type="submit"]');
    if (button) {
      button.disabled = true;
      button.textContent = button.dataset.submitText || 'Enviando...';
    }
  });
})();
