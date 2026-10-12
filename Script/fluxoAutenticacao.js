
(() => {
    const chave = 'ideiaTech.retornoLogin';
    let verificarSessao = async () => false;
    let iniciarPagamento = null;
    function destinoSeguro(valor) {
        if (!valor) return null;
        try {
            const url = new URL(valor, location.href);
            const base = new URL('../', location.href);
            if (url.origin !== location.origin || !url.pathname.startsWith(base.pathname + 'Pages/') || url.username || url.password) return null;
            return url.href;
        } catch { return null; }
    }
    function retorno() {
        const parametro = destinoSeguro(new URLSearchParams(location.search).get('next'));
        if (parametro) return parametro;
        try { return destinoSeguro(sessionStorage.getItem(chave)); } catch { return null; }
    }
    window.FluxoAutenticacao = {
        configurar(opcoes) {
            if (typeof opcoes.verificarSessao === 'function') verificarSessao = opcoes.verificarSessao;
            if (typeof opcoes.iniciarPagamento === 'function') iniciarPagamento = opcoes.iniciarPagamento;
        },
        async pagar(itens) {
            if (!await verificarSessao()) {
                const destino = location.href;
                try { sessionStorage.setItem(chave, destino); } catch {}
                const url = new URL('login.html', location.href);
                url.searchParams.set('next', destino);
                location.assign(url.href);
                return;
            }
            if (!iniciarPagamento) throw new Error('O pagamento ainda não está disponível. Seu carrinho continua salvo.');
            await iniciarPagamento(itens);
        },
        concluirLogin() {
            const destino = retorno() || new URL('Carrinho.html', location.href).href;
            try { sessionStorage.removeItem(chave); } catch {  }
            location.assign(destino);
        }
    };
    const destino = retorno();
    if (destino) {
        document.querySelectorAll('[data-link-autenticacao]').forEach(link => {
            const url = new URL(link.getAttribute('href'), location.href);
            url.searchParams.set('next', destino);
            link.href = url.href;
        });
        const form = document.querySelector('.login-form form');
        if (form) {
            const campo = document.createElement('input');
            campo.type = 'hidden'; campo.name = 'next'; campo.value = destino;
            form.append(campo);
            const aviso = document.createElement('p');
            aviso.className = 'aviso-retorno';
            aviso.textContent = 'Entre na sua conta para continuar a compra. Seus produtos estão salvos no carrinho.';
            form.before(aviso);
        }
    }
})();
