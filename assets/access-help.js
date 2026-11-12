/* Access support keeps its draft in this document and sends no login secrets. */
(() => {
  'use strict';

  const panel = document.getElementById('access-help-panel');
  const form = document.getElementById('access-help-form');
  if (!panel || !form) return;

  const identifier = document.getElementById('access-help-identifier');
  const email = document.getElementById('access-help-email');
  const category = document.getElementById('access-help-category');
  const details = document.getElementById('access-help-details');
  const submit = document.getElementById('access-help-submit');
  const status = document.getElementById('access-help-status');
  if (![identifier, email, category, details, submit, status].every(Boolean)) return;

  const categories = new Set(['code', 'password', 'two_factor', 'payment', 'other']);
  const touched = new Set();
  const initialSubmitLabel = submit.textContent;
  let busy = false;
  let accountRequest = null;
  let lastSuccessfulDraft = null;

  function feedback(message, error = false) {
    status.textContent = message;
    status.classList.toggle('error', error);
  }

  function fillEmpty(field, value) {
    if (!touched.has(field) && !field.value && typeof value === 'string') {
      field.value = value;
    }
  }

  function fillLoginIdentifier() {
    const login = document.querySelector('#login-form input[name="username"]:not([type="password"])');
    if (login) fillEmpty(identifier, login.value.trim());
  }

  async function readAccount() {
    if (accountRequest) return accountRequest;
    accountRequest = (async () => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 20000);
      try {
        const response = await fetch('/api/account/me', {
          credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        });
        const data = await response.json();
        if (!response.ok || !data || typeof data.csrf !== 'string' || !data.csrf) {
          throw new Error('No se pudo preparar el formulario. Pulsa enviar para volver a intentarlo.');
        }
        if (data.user) {
          fillEmpty(identifier, data.user.username);
          fillEmpty(email, data.profile?.email);
        }
        return data;
      } catch (error) {
        if (error.name === 'AbortError') {
          throw new Error('La conexión tarda demasiado. Pulsa enviar para volver a intentarlo.');
        }
        throw error;
      } finally {
        clearTimeout(timer);
      }
    })();
    try {
      return await accountRequest;
    } finally {
      accountRequest = null;
    }
  }

  function prepare() {
    fillLoginIdentifier();
    // This is called only by an explicit opening gesture or form submission.
    return readAccount();
  }

  function open(options = {}) {
    panel.hidden = false;
    panel.classList.remove('hidden');
    if (panel.tagName === 'DETAILS') panel.open = true;
    if (categories.has(options.category) && !touched.has(category) && !busy) category.value = options.category;
    panel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    if (!busy) identifier.focus({ preventScroll: true });
    prepare().catch(() => {
      if (!busy && !lastSuccessfulDraft) {
        feedback('No se pudo preparar la conexión. Puedes completar el formulario y pulsar enviar para volver a intentarlo.', true);
      }
    });
  }

  document.addEventListener('click', event => {
    const target = event.target?.closest?.('[data-access-help-open], a[href="#access-help-panel"]');
    if (target) {
      event.preventDefault();
      open({ category: target.dataset.accessHelpCategory });
      return;
    }
    const summary = event.target?.closest?.('summary');
    if (panel.tagName === 'DETAILS' && summary?.parentElement === panel && !panel.open) {
      prepare().catch(() => {
        if (!busy && !lastSuccessfulDraft) feedback('Completa el formulario y pulsa enviar para preparar la conexión.', true);
      });
    }
  });

  for (const field of [identifier, email, category, details]) {
    const remember = () => {
      touched.add(field);
      if (!busy) {
        submit.disabled = false;
        submit.textContent = initialSubmitLabel;
      }
    };
    field.addEventListener('input', remember);
    field.addEventListener('change', remember);
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !form.reportValidity()) return;
    const draftSignature = () => JSON.stringify({
      identifier: identifier.value.trim(), contact_email: email.value.trim(),
      category: category.value, details: details.value.trim(),
    });
    if (draftSignature() === lastSuccessfulDraft) return;
    busy = true;
    const disabledFields = [identifier, email, category, details].map(field => [field, field.disabled]);
    for (const [field] of disabledFields) field.disabled = true;
    submit.disabled = true;
    submit.textContent = 'Enviando…';
    form.setAttribute('aria-busy', 'true');
    feedback('Guardando tu solicitud de ayuda…');
    const controller = new AbortController();
    let timer;
    try {
      const account = await prepare();
      const signature = draftSignature();
      timer = setTimeout(() => controller.abort(), 20000);
      // One POST per explicit submission; a failed response is never retried automatically.
      const response = await fetch('/api/account/access-help', {
        method: 'POST', credentials: 'same-origin', signal: controller.signal,
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': account.csrf },
        body: signature,
      });
      let data;
      try { data = await response.json(); }
      catch { throw new Error('No se pudo confirmar la solicitud. Revisa la conexión antes de volver a enviarla.'); }
      if (!response.ok || data?.ok !== true || !['sent', 'queued'].includes(data.delivery)) {
        throw new Error(data?.error || 'No se pudo confirmar la solicitud. Puedes volver a intentarlo.');
      }
      lastSuccessfulDraft = signature;
      const delivery = data.delivery === 'sent' ? 'Aviso enviado a administración.' : 'Aviso guardado; el correo queda pendiente de envío.';
      feedback((typeof data.message === 'string' ? data.message + ' ' : '') + delivery);
      submit.textContent = 'Solicitud guardada';
    } catch (error) {
      feedback(error.name === 'AbortError'
        ? 'No se pudo confirmar la solicitud a tiempo. Revisa la conexión antes de volver a enviarla.'
        : error.message || 'No se pudo confirmar la solicitud. Puedes volver a intentarlo.', true);
      submit.disabled = false;
      submit.textContent = 'Volver a intentar';
    } finally {
      clearTimeout(timer);
      busy = false;
      for (const [field, disabled] of disabledFields) field.disabled = disabled;
      form.removeAttribute('aria-busy');
    }
  });

  window.OLAccessHelp = Object.freeze({ open });
})();
