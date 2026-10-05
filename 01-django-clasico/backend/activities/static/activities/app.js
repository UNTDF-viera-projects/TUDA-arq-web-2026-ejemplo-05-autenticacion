/** Evita enviar dos veces un formulario mientras el servidor prepara la siguiente página. */
function preventRepeatedSubmit(event) {
  const form = event.target
  if (!(form instanceof HTMLFormElement)) return
  if (form.dataset.submitting === 'true') {
    event.preventDefault()
    return
  }
  form.dataset.submitting = 'true'
  form.setAttribute('aria-busy', 'true')
  if (event.submitter instanceof HTMLButtonElement) {
    event.submitter.disabled = true
    event.submitter.dataset.submitLock = 'true'
  }
}

/** Restablece botones si el navegador recupera una página anterior desde su caché de historial. */
function restoreFormButtons() {
  for (const form of document.forms) {
    delete form.dataset.submitting
    form.removeAttribute('aria-busy')
  }
  for (const button of document.querySelectorAll('button[data-submit-lock]')) {
    button.disabled = false
    delete button.dataset.submitLock
  }
}

// Esta mejora visual no autentica: el servidor verifica sesión, CSRF y propiedad.
document.addEventListener('submit', preventRepeatedSubmit)
window.addEventListener('pageshow', restoreFormButtons)
