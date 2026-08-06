(() => {
  const shell = document.getElementById('appShell');
  const sidebar = document.getElementById('sidebar');
  const scrim = document.querySelector('[data-sidebar-close]');
  const mobile = () => window.matchMedia('(max-width: 900px)').matches;

  if (shell && localStorage.getItem('movixSidebar') === 'collapsed' && !mobile()) shell.classList.add('sidebar-collapsed');
  document.querySelectorAll('[data-sidebar-toggle]').forEach(button => button.addEventListener('click', () => {
    if (mobile()) { sidebar?.classList.toggle('mobile-open'); scrim?.classList.toggle('open'); }
    else { shell?.classList.toggle('sidebar-collapsed'); localStorage.setItem('movixSidebar', shell?.classList.contains('sidebar-collapsed') ? 'collapsed' : 'open'); }
  }));
  scrim?.addEventListener('click', () => { sidebar?.classList.remove('mobile-open'); scrim.classList.remove('open'); });

  document.querySelectorAll('[data-dropdown-toggle]').forEach(button => button.addEventListener('click', event => {
    event.stopPropagation(); document.getElementById(button.dataset.dropdownToggle)?.classList.toggle('open');
  }));
  document.addEventListener('click', event => { if (!event.target.closest('.dropdown') && !event.target.closest('[data-dropdown-toggle]')) document.querySelectorAll('.dropdown.open').forEach(el => el.classList.remove('open')); });
  document.querySelectorAll('[data-dismiss]').forEach(button => button.addEventListener('click', () => button.closest('.alert')?.remove()));

  const dialog = document.getElementById('confirmDialog'); let pendingForm = null;
  document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
    if (form.dataset.confirmed === 'true') return;
    event.preventDefault(); pendingForm = form;
    const [title, text] = (form.dataset.confirm || '').split('|');
    if (!dialog?.showModal) { if (window.confirm(text || title)) { form.dataset.confirmed = 'true'; form.submit(); } return; }
    dialog.querySelector('#confirmTitle').textContent = title || 'Confirmar acción'; dialog.querySelector('#confirmText').textContent = text || 'Esta acción no se puede deshacer.'; dialog.showModal();
  }));
  dialog?.querySelector('[data-dialog-cancel]')?.addEventListener('click', () => { pendingForm = null; dialog.close(); });
  dialog?.querySelector('[data-dialog-confirm]')?.addEventListener('click', () => { if (pendingForm) { pendingForm.dataset.confirmed = 'true'; pendingForm.submit(); } dialog.close(); });

  document.querySelectorAll('input[type="file"]').forEach(input => input.addEventListener('change', () => {
    const label = input.closest('label'); const target = label?.querySelector('[data-file-name]');
    if (target) target.textContent = input.files?.[0]?.name || 'Ningún archivo seleccionado';
  }));

  // Buscadores de tablas: consulta automática desde dos caracteres.
  document.querySelectorAll('form[data-auto-search]').forEach(form => {
    const input = form.querySelector('input[name="q"]');
    const minimum = Number(form.dataset.minLength || 2);
    let timer;
    input?.addEventListener('input', () => {
      clearTimeout(timer);
      const value = input.value.trim();
      if (value.length > 0 && value.length < minimum) return;
      timer = setTimeout(() => form.requestSubmit(), 380);
    });
    input?.addEventListener('keydown', event => {
      if (event.key === 'Enter' && input.value.trim().length > 0 && input.value.trim().length < minimum) event.preventDefault();
    });
    form.querySelectorAll('[data-filter-value]').forEach(button => button.addEventListener('click', () => {
      const target = form.querySelector('[data-filter-input]');
      if (target) target.value = button.dataset.filterValue;
      form.requestSubmit();
    }));
  });

  // La búsqueda superior navega únicamente entre los módulos del menú.
  const moduleForm = document.querySelector('[data-module-search]');
  const moduleInput = moduleForm?.querySelector('input[type="search"]');
  const moduleResults = document.getElementById('moduleSearchResults');
  const modules = [...document.querySelectorAll('.sidebar-nav [data-module-name]')].map(link => ({
    name: link.dataset.moduleName,
    href: link.href,
    icon: link.querySelector('use')?.getAttribute('href') || '#i-search',
  }));
  const escapeHtml = value => String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const renderModules = () => {
    if (!moduleResults || !moduleInput) return;
    const query = moduleInput.value.trim().toLocaleLowerCase('es');
    const matches = modules.filter(item => !query || item.name.toLocaleLowerCase('es').includes(query));
    moduleResults.innerHTML = matches.length
      ? matches.map(item => `<a href="${item.href}" role="option"><svg><use href="${item.icon}"></use></svg><span>${escapeHtml(item.name)}</span></a>`).join('')
      : '<p>No existe un módulo con ese nombre.</p>';
    moduleResults.classList.add('open');
    moduleInput.setAttribute('aria-expanded', 'true');
  };
  moduleForm?.addEventListener('submit', event => {
    event.preventDefault();
    const first = moduleResults?.querySelector('a');
    if (first) window.location.assign(first.href);
  });
  moduleInput?.addEventListener('focus', renderModules);
  moduleInput?.addEventListener('input', renderModules);
  document.addEventListener('click', event => {
    if (!event.target.closest('[data-module-search]')) {
      moduleResults?.classList.remove('open');
      moduleInput?.setAttribute('aria-expanded', 'false');
    }
  });

  // Vista previa de documentos en una sola ventana emergente.
  const previewDialog = document.getElementById('documentPreviewDialog');
  const previewImage = document.getElementById('documentPreviewImage');
  const previewFrame = document.getElementById('documentPreviewFrame');
  const previewStage = document.getElementById('documentPreviewStage');
  const closePreview = () => {
    if (previewImage) previewImage.removeAttribute('src');
    if (previewFrame) previewFrame.removeAttribute('src');
    previewDialog?.close();
  };
  document.querySelectorAll('[data-document-preview]').forEach(button => button.addEventListener('click', () => {
    if (!previewDialog) return;
    const isPdf = button.dataset.previewPdf === 'true';
    previewDialog.querySelector('#documentPreviewTitle').textContent = button.dataset.title || 'Documento';
    previewDialog.querySelector('#documentPreviewName').textContent = button.dataset.fileName || '';
    const download = previewDialog.querySelector('#documentPreviewDownload');
    download.href = button.dataset.downloadUrl;
    previewStage?.classList.add('loading');
    previewStage?.classList.toggle('show-pdf', isPdf);
    if (isPdf && previewFrame) previewFrame.src = button.dataset.previewUrl;
    if (!isPdf && previewImage) previewImage.src = button.dataset.previewUrl;
    previewDialog.showModal();
  }));
  previewImage?.addEventListener('load', () => previewStage?.classList.remove('loading'));
  previewImage?.addEventListener('error', () => previewStage?.classList.remove('loading'));
  previewFrame?.addEventListener('load', () => previewStage?.classList.remove('loading'));
  previewDialog?.querySelector('[data-preview-close]')?.addEventListener('click', closePreview);
  previewDialog?.addEventListener('click', event => {
    const rect = previewDialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closePreview();
  });

  document.querySelectorAll('button[data-loading-text]').forEach(button => button.closest('form')?.addEventListener('submit', () => {
    button.disabled = true;
    button.dataset.originalText = button.innerHTML;
    button.textContent = button.dataset.loadingText;
  }));
  document.querySelectorAll('[data-password-toggle]').forEach(button => button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.passwordToggle); if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password'; button.textContent = input.type === 'password' ? 'Ver' : 'Ocultar';
  }));

  const audience = document.getElementById('id_audience'); const recipientField = document.querySelector('.recipient-field');
  const updateRecipient = () => { if (recipientField) recipientField.style.display = audience?.value === 'specific' ? 'flex' : 'none'; };
  audience?.addEventListener('change', updateRecipient); updateRecipient();
  const message = document.getElementById('id_message'); const count = document.querySelector('[data-char-count]');
  const updateCount = () => { if (count) count.textContent = message?.value.length || 0; };
  message?.addEventListener('input', updateCount); updateCount();

  const rawData = document.getElementById('dashboard-data');
  if (rawData) {
    let data = JSON.parse(rawData.textContent); if (typeof data === 'string') data = JSON.parse(data);
    drawLineChart(document.getElementById('growthChart'), data.labels, [data.clients, data.drivers], ['#27aef3', '#7b55ec']);
    drawBarChart(document.getElementById('ridesChart'), data.labels, data.rides, '#8355ed');
  }

  function setupCanvas(canvas) {
    if (!canvas) return null; const ratio = window.devicePixelRatio || 1; const width = canvas.clientWidth || 600; const height = Number(canvas.getAttribute('height')) || 280;
    canvas.width = width * ratio; canvas.height = height * ratio; canvas.style.height = `${height}px`; const ctx = canvas.getContext('2d'); ctx.scale(ratio, ratio); return {ctx, width, height};
  }
  function drawGrid(ctx, width, height, max, labels) {
    ctx.font = '12px system-ui'; ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--border'); ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--muted'); ctx.lineWidth = 1;
    for (let i=0;i<5;i++){const y=18+(height-55)*i/4;ctx.beginPath();ctx.moveTo(35,y);ctx.lineTo(width-10,y);ctx.stroke();ctx.fillText(String(Math.round(max*(4-i)/4)),2,y+4)}
    labels.forEach((label,i)=>{const x=45+(width-70)*i/Math.max(1,labels.length-1);ctx.fillText(label,x-10,height-10)});
  }
  function drawLineChart(canvas, labels, series, colors) {
    const setup=setupCanvas(canvas); if(!setup)return; const {ctx,width,height}=setup; const max=Math.max(5,...series.flat())*1.15; drawGrid(ctx,width,height,max,labels);
    series.forEach((values,s)=>{ctx.strokeStyle=colors[s];ctx.lineWidth=3;ctx.beginPath();values.forEach((v,i)=>{const x=45+(width-70)*i/Math.max(1,values.length-1);const y=18+(height-55)*(1-v/max);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();values.forEach((v,i)=>{const x=45+(width-70)*i/Math.max(1,values.length-1);const y=18+(height-55)*(1-v/max);ctx.fillStyle=colors[s];ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill()})});
  }
  function drawBarChart(canvas, labels, values, color) {
    const setup=setupCanvas(canvas); if(!setup)return; const {ctx,width,height}=setup; const max=Math.max(5,...values)*1.15; drawGrid(ctx,width,height,max,labels); const step=(width-70)/Math.max(1,values.length); const bar=Math.min(32,step*.55);
    values.forEach((v,i)=>{const x=43+i*step+(step-bar)/2;const h=(height-55)*v/max;const y=height-37-h;ctx.fillStyle=color;ctx.beginPath();ctx.roundRect(x,y,bar,h,6);ctx.fill()});
  }
})();
