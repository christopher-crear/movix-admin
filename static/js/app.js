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

  // Tooltip fuera del contenedor desplazable: al estar fijado al documento no
  // se recorta por el borde del menú lateral.
  const menuTooltip = document.createElement('div');
  menuTooltip.className = 'menu-tooltip';
  menuTooltip.setAttribute('role', 'tooltip');
  document.body.appendChild(menuTooltip);
  const showMenuTooltip = link => {
    if (!shell?.classList.contains('sidebar-collapsed') || mobile()) return;
    const label = link.dataset.tooltip || link.querySelector('span')?.textContent?.trim();
    if (!label) return;
    const rect = link.getBoundingClientRect();
    menuTooltip.textContent = label;
    menuTooltip.style.left = `${rect.right + 12}px`;
    menuTooltip.style.top = `${Math.max(8, Math.min(window.innerHeight - 48, rect.top + rect.height / 2 - 18))}px`;
    menuTooltip.classList.add('visible');
  };
  const hideMenuTooltip = () => menuTooltip.classList.remove('visible');
  document.querySelectorAll('.sidebar .nav-link').forEach(link => {
    link.addEventListener('mouseenter', () => showMenuTooltip(link));
    link.addEventListener('mouseleave', hideMenuTooltip);
    link.addEventListener('focus', () => showMenuTooltip(link));
    link.addEventListener('blur', hideMenuTooltip);
  });

  document.querySelectorAll('[data-dropdown-toggle]').forEach(button => button.addEventListener('click', event => {
    event.stopPropagation(); document.getElementById(button.dataset.dropdownToggle)?.classList.toggle('open');
  }));
  document.addEventListener('click', event => { if (!event.target.closest('.dropdown') && !event.target.closest('[data-dropdown-toggle]')) document.querySelectorAll('.dropdown.open').forEach(el => el.classList.remove('open')); });
  document.querySelectorAll('[data-dismiss]').forEach(button => button.addEventListener('click', () => button.closest('.alert')?.remove()));

  // El número se guarda como 09XXXXXXXX, pero la persona solo escribe los
  // nueve dígitos nacionales después del prefijo ecuatoriano fijo.
  document.querySelectorAll('input[data-ecuador-phone]').forEach(input => {
    if (input.parentElement?.classList.contains('phone-country-field')) return;
    const field = document.createElement('span');
    field.className = 'phone-country-field';
    const prefix = document.createElement('span');
    prefix.className = 'phone-country-prefix';
    prefix.textContent = '🇪🇨 +593';
    input.parentNode.insertBefore(field, input);
    field.append(prefix, input);
    input.addEventListener('input', () => { input.value = input.value.replace(/\D/g, '').replace(/^0/, '').slice(0, 9); });
  });

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
    const host = input.closest('[data-local-upload]');
    const label = input.closest('label');
    const target = label?.querySelector('[data-file-name]') || host?.querySelector('[data-file-name]');
    const file = input.files?.[0];
    if (target) target.textContent = file?.name || 'Ningún archivo seleccionado';

    // Previsualización local, pequeña y proporcional antes de guardar.
    const preview = host?.querySelector('.local-file-preview');
    const image = preview?.querySelector('img');
    const pdfFrame = preview?.querySelector('.local-pdf-frame');
    if (!preview || !image) return;
    const previousUrl = preview.dataset.objectUrl;
    if (previousUrl) URL.revokeObjectURL(previousUrl);
    preview.classList.remove('active', 'is-pdf');
    image.removeAttribute('src');
    pdfFrame?.removeAttribute('src');
    if (!file) return;
    preview.classList.add('active');
    if (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) {
      preview.classList.add('is-pdf');
      const objectUrl = URL.createObjectURL(file);
      preview.dataset.objectUrl = objectUrl;
      if (pdfFrame) pdfFrame.src = `${objectUrl}#page=1&zoom=page-fit&toolbar=0&navpanes=0`;
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    preview.dataset.objectUrl = objectUrl;
    image.src = objectUrl;
  }));

  // Nunca se muestra el icono roto del navegador dentro de una tarjeta.
  document.querySelectorAll('[data-media-thumb]').forEach(image => image.addEventListener('error', () => {
    image.closest('.asset-preview-canvas')?.classList.add('is-error');
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
    previewStage?.classList.remove('loading', 'preview-error');
    previewDialog?.close();
  };
  document.querySelectorAll('[data-document-preview]').forEach(button => button.addEventListener('click', () => {
    if (!previewDialog) return;
    const isPdf = button.dataset.previewPdf === 'true';
    previewDialog.querySelector('#documentPreviewTitle').textContent = button.dataset.title || 'Documento';
    previewDialog.querySelector('#documentPreviewName').textContent = button.dataset.fileName || '';
    const download = previewDialog.querySelector('#documentPreviewDownload');
    download.href = button.dataset.downloadUrl;
    previewStage?.classList.remove('preview-error');
    previewStage?.classList.add('loading');
    previewStage?.classList.toggle('show-pdf', isPdf);
    if (isPdf) {
      previewImage?.removeAttribute('src');
      if (previewFrame) previewFrame.src = `${button.dataset.previewUrl}#page=1&zoom=page-width&toolbar=1&navpanes=1`;
    } else {
      previewFrame?.removeAttribute('src');
      if (previewImage) previewImage.src = button.dataset.previewUrl;
    }
    previewDialog.showModal();
  }));
  previewImage?.addEventListener('load', () => previewStage?.classList.remove('loading', 'preview-error'));
  previewImage?.addEventListener('error', () => { previewStage?.classList.remove('loading'); previewStage?.classList.add('preview-error'); });
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

  // Mensualidad del transportista: las tarjetas solo abren información y el
  // formulario conserva opciones válidas según la forma de pago elegida.
  document.querySelectorAll('[data-bank-dialog-open]').forEach(button => button.addEventListener('click', () => {
    const dialog = document.getElementById(button.dataset.bankDialogOpen);
    if (dialog?.showModal) dialog.showModal();
  }));
  document.querySelectorAll('.driver-bank-dialog').forEach(dialog => {
    dialog.querySelectorAll('[data-bank-dialog-close]').forEach(button => button.addEventListener('click', () => dialog.close()));
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    });
  });

  const paymentForm = document.getElementById('driverPaymentForm');
  if (paymentForm) {
    const bankSelect = paymentForm.querySelector('#id_bank');
    const methodSelect = paymentForm.querySelector('#id_payment_method');
    const receiptInput = paymentForm.querySelector('input[type="file"][name="receipt"]');
    const receiptField = paymentForm.querySelector('[data-payment-receipt-field]');
    const methodHelp = paymentForm.querySelector('[data-payment-method-help] span');
    const syncPaymentMethod = () => {
      const physical = methodSelect?.value === 'cash';
      if (physical && bankSelect) bankSelect.value = 'physical';
      if (!physical && bankSelect?.value === 'physical') bankSelect.value = '';
      if (receiptInput) receiptInput.required = !physical;
      receiptField?.classList.toggle('is-optional', physical);
      if (methodHelp) methodHelp.textContent = physical
        ? 'El pago físico no requiere comprobante. El administrador registrará y confirmará la mensualidad.'
        : 'Selecciona una cuenta bancaria y adjunta el comprobante de la transferencia o depósito.';
    };
    methodSelect?.addEventListener('change', syncPaymentMethod);
    syncPaymentMethod();

    document.querySelectorAll('[data-use-payment-bank]').forEach(button => button.addEventListener('click', () => {
      if (bankSelect) bankSelect.value = button.dataset.usePaymentBank;
      if (methodSelect) methodSelect.value = 'transfer';
      syncPaymentMethod();
      button.closest('dialog')?.close();
      paymentForm.scrollIntoView({behavior: 'smooth', block: 'center'});
      window.setTimeout(() => bankSelect?.focus(), 350);
    }));
  }

  document.querySelectorAll('[data-letters-only]').forEach(input => input.addEventListener('input', () => {
    input.value = input.value.replace(/[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ '\-]/g, '');
  }));
  document.querySelectorAll('[data-digits-only]').forEach(input => input.addEventListener('input', () => {
    input.value = input.value.replace(/\D/g, '').slice(0, Number(input.maxLength) || undefined);
  }));
  document.querySelectorAll('[data-ecuador-plate]').forEach(input => input.addEventListener('input', () => {
    const raw = input.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 7);
    input.value = raw.length > 3 ? `${raw.slice(0, 3)}-${raw.slice(3)}` : raw;
  }));
  document.querySelectorAll('[data-code-only]').forEach(input => input.addEventListener('input', () => {
    input.value = input.value.toUpperCase().replace(/[^A-Z0-9/\-]/g, '');
  }));

  const rawData = document.getElementById('dashboard-data');
  if (rawData) {
    let data = JSON.parse(rawData.textContent); if (typeof data === 'string') data = JSON.parse(data);
    const renderDashboardCharts = () => {
      drawLineChart(document.getElementById('growthChart'), data.labels, [data.clients, data.drivers], ['Usuarios', 'Transportistas']);
      drawBarChart(document.getElementById('ridesChart'), data.labels, data.rides, '#2864ef');
    };
    renderDashboardCharts();
    let resizeTimer;
    window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderDashboardCharts, 140); });
  }

  function setupCanvas(canvas) {
    if (!canvas) return null; const ratio = window.devicePixelRatio || 1; const width = canvas.clientWidth || 600; const height = Number(canvas.getAttribute('height')) || 280;
    canvas.width = width * ratio; canvas.height = height * ratio; canvas.style.height = `${height}px`; const ctx = canvas.getContext('2d'); ctx.scale(ratio, ratio); return {ctx, width, height};
  }
  function drawGrid(ctx, width, height, max, labels) {
    ctx.font = '12px system-ui'; ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--border'); ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--muted'); ctx.lineWidth = 1;
    for (let i=0;i<5;i++){const y=18+(height-62)*i/4;ctx.beginPath();ctx.moveTo(40,y);ctx.lineTo(width-10,y);ctx.stroke();ctx.fillText(String(Math.round(max*(4-i)/4)),3,y+4)}
    labels.forEach((label,i)=>{const x=48+(width-78)*i/Math.max(1,labels.length-1);ctx.fillText(label,x-12,height-12)});
  }
  function attachChartTooltip(canvas, regions) {
    if (!canvas) return;
    canvas._movixRegions = regions;
    if (canvas.dataset.tooltipReady) return;
    canvas.dataset.tooltipReady = '1';
    const tooltip = document.createElement('div'); tooltip.className = 'chart-tooltip'; tooltip.hidden = true; document.body.appendChild(tooltip);
    canvas.addEventListener('mousemove', event => {
      const rect = canvas.getBoundingClientRect(); const x = event.clientX - rect.left; const y = event.clientY - rect.top;
      const hit = (canvas._movixRegions || []).find(point => Math.hypot(point.x-x, point.y-y) < (point.radius || 15));
      if (!hit) { tooltip.hidden = true; return; }
      tooltip.innerHTML = `<strong>${escapeHtml(hit.label)}</strong>${escapeHtml(hit.detail)}`;
      tooltip.style.left = `${event.clientX}px`; tooltip.style.top = `${event.clientY}px`; tooltip.hidden = false;
    });
    canvas.addEventListener('mouseleave', () => { tooltip.hidden = true; });
  }
  function drawLineChart(canvas, labels, series, names) {
    const setup=setupCanvas(canvas); if(!setup)return; const {ctx,width,height}=setup; const max=Math.max(5,...series.flat())*1.18; drawGrid(ctx,width,height,max,labels); const regions=[];
    const colors=['#18cdb7','#2356d8'];
    series.forEach((values,s)=>{
      const points=values.map((v,i)=>({x:48+(width-78)*i/Math.max(1,values.length-1),y:18+(height-62)*(1-v/max),v}));
      if(s===0 && points.length){const gradient=ctx.createLinearGradient(0,18,0,height-36);gradient.addColorStop(0,'rgba(35,86,216,.55)');gradient.addColorStop(.48,'rgba(40,158,237,.35)');gradient.addColorStop(1,'rgba(24,205,183,.08)');ctx.beginPath();ctx.moveTo(points[0].x,height-36);points.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.lineTo(p.x,p.y));ctx.lineTo(points.at(-1).x,height-36);ctx.closePath();ctx.fillStyle=gradient;ctx.fill()}
      ctx.strokeStyle=colors[s];ctx.lineWidth=s?3:4;ctx.lineJoin='round';ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));ctx.stroke();
      points.forEach((p,i)=>{ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(p.x,p.y,6,0,Math.PI*2);ctx.fill();ctx.strokeStyle=colors[s];ctx.lineWidth=3;ctx.stroke();regions.push({x:p.x,y:p.y,radius:16,label:labels[i],detail:`${names[s]}: ${p.v}`})});
    });
    attachChartTooltip(canvas,regions);
  }
  function drawBarChart(canvas, labels, values, color) {
    const setup=setupCanvas(canvas); if(!setup)return; const {ctx,width,height}=setup; const max=Math.max(5,...values)*1.15; drawGrid(ctx,width,height,max,labels); const step=(width-78)/Math.max(1,values.length); const bar=Math.min(36,step*.58);const regions=[];
    const gradient=ctx.createLinearGradient(0,18,0,height-36);gradient.addColorStop(0,color);gradient.addColorStop(1,'#2dc9d0');
    values.forEach((v,i)=>{const x=43+i*step+(step-bar)/2;const h=(height-62)*v/max;const y=height-38-h;ctx.fillStyle=gradient;ctx.beginPath();ctx.roundRect(x,y,bar,Math.max(h,2),8);ctx.fill();regions.push({x:x+bar/2,y:y+Math.max(h,2)/2,radius:Math.max(18,h/2),label:labels[i],detail:`Carreras completadas: ${v}`})});
    attachChartTooltip(canvas,regions);
  }
})();
