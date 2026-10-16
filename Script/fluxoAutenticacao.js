
(() => {
    const chave = 'ideiaTech.retornoLogin';
    let verificarSessao = null;
    let iniciarPagamento = confirmarPedido;
    async function confirmarPedido(itens) {
        const respostaToken = await fetch('/csrf-token', {
            credentials: 'same-origin',
            cache: 'no-store',
            headers: { Accept: 'application/json' }
        });
        if (!respostaToken.ok) {
            throw new Error('Não foi possível obter o token de segurança. Tente novamente.');
        }
        const token = await respostaToken.json();
        if (typeof token.csrf_token !== 'string' || !token.csrf_token) {
            throw new Error('Não foi possível proteger o envio do pedido. Atualize a página.');
        }
        const resposta = await fetch('/pedidos', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { Accept: 'application/json' },
            body: new URLSearchParams({
                csrf_token: token.csrf_token,
                itens: JSON.stringify(itens.map(item => ({ id: item.id, quantidade: item.quantidade })))
            })
        });
        const dados = await resposta.json().catch(() => null);
        if (!resposta.ok) {
            const erro = new Error(dados?.erro || 'Não foi possível confirmar o pedido. Atualize a página e tente novamente.');
            erro.status = resposta.status;
            throw erro;
        }
        if (!dados || !Array.isArray(dados.pedidos) || !dados.pedidos.length) {
            throw new Error('O servidor retornou uma confirmação inválida. Confira seus pedidos antes de tentar novamente.');
        }
        return dados;
    }
    function encaminharLogin() {
        const destino = location.href;
        try { sessionStorage.setItem(chave, destino); } catch {}
        const url = new URL('login.html', location.href);
        url.searchParams.set('next', destino);
        location.assign(url.href);
    }
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
            if (verificarSessao && !await verificarSessao()) {
                encaminharLogin();
                return;
            }
            try {
                return await iniciarPagamento(itens);
            } catch (erro) {
                if (erro.status === 401) {
                    encaminharLogin();
                    return;
                }
                throw erro;
            }
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
