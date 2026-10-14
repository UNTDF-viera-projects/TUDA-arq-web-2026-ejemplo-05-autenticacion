(async () => {
  const api = 'http://localhost:8005/api/v1';

  async function ingresar(email) {
    const csrf = await fetch(`${api}/auth/csrf`, {
      credentials: 'include',
    }).then(r => r.json());

    const respuesta = await fetch(`${api}/auth/login`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf.csrfToken,
      },
      body: JSON.stringify({ email, password: 'Demo12345!' }),
    });

    if (!respuesta.ok) throw new Error(`Login: ${respuesta.status}`);
    return (await respuesta.json()).access;
  }

  // Leer el payload no verifica su firma.
  function leerPayload(token) {
    const parte = token.split('.')[1]
      .replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(parte));
  }

  const tokenDemo = await ingresar('demo@example.com');
  const tokenOther = await ingresar('other@example.com');

  const [header, , firma] = tokenDemo.split('.');
  const payloadAlterado = {
    ...leerPayload(tokenDemo),
    sub: leerPayload(tokenOther).sub,
  };

  const payloadCodificado = btoa(JSON.stringify(payloadAlterado))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  // Cambiamos el contenido y conservamos la firma de demo.
  const tokenAlterado = `${header}.${payloadCodificado}.${firma}`;

  console.log('Payload original:', leerPayload(tokenDemo));
  console.log('Payload alterado:', payloadAlterado);

  const resultados = await Promise.all(
    [
      ['Demo original', tokenDemo],
      ['Other original', tokenOther],
      ['Demo con sub de other', tokenAlterado],
    ].map(async ([caso, token]) => {
      const respuesta = await fetch(`${api}/me`, {
        credentials: 'omit',
        headers: { Authorization: `Bearer ${token}` },
      });
      const datos = await respuesta.json();
      return {
        caso,
        estado: respuesta.status,
        resultado: datos.email ?? datos.code,
      };
    }),
  );

  console.table(resultados);
})();
