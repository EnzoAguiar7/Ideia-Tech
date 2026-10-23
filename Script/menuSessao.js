(() => {
    const link = document.querySelector('[data-menu-sessao]');
    if (!link) return;

    fetch('/sessao-atual', {
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { Accept: 'application/json' }
    })
        .then(resposta => resposta.ok ? resposta.json() : null)
        .then(sessao => {
            if (!sessao?.autenticado) return;

            link.href = sessao.tipo === 'empresa'
                ? '/Pages/Empresa/painelEmpresa.html'
                : '/Pages/Perfil.html';
            link.replaceChildren();

            const icone = document.createElement('i');
            icone.setAttribute('data-lucide', 'user-round');
            icone.setAttribute('aria-hidden', 'true');
            const texto = document.createElement('span');
            texto.textContent = 'Perfil';
            link.append(icone, texto);
            window.lucide?.createIcons();
        })
        .catch(() => {});
})();
