(() => {
    const chave = 'ideiaTech.carrinho.v1';
    const chaveEnderecoEntrega = 'ideiaTech.enderecoEntrega.v1';
    const catalogo = window.CatalogoProdutos;
    let fretePorEmpresa = null;
    let enderecoNaConta = false;
    let enderecoDaConta = false;
    let enviandoPedido = false;
    const moeda = valor => (valor / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    function ler() {
        try {
            const dados = JSON.parse(localStorage.getItem(chave) || '[]');
            if (!Array.isArray(dados)) return [];
            const vistos = new Set();
            return dados
                .filter(item => {
                    if (
                        !item
                        || !Object.hasOwn(catalogo, item.id)
                        || !Number.isInteger(item.quantidade)
                        || item.quantidade <= 0
                        || vistos.has(item.id)
                    ) {
                        return false;
                    }

                    const produto = catalogo[item.id];

                    if (produto.estoque <= 0) {
                        return false;
                    }

                    vistos.add(item.id);
                    return true;
                })
                .map(item => ({
                    id: item.id,
                    quantidade: Math.min(
                        item.quantidade,
                        catalogo[item.id].estoque
                    )
                }));

        } catch { return []; }
    }
    function avisar(texto) {
        let aviso = document.querySelector('[data-aviso-carrinho]');
        if (!aviso) {
            aviso = document.createElement('p'); aviso.dataset.avisoCarrinho = '';
            aviso.className = 'aviso-carrinho'; aviso.setAttribute('role', 'status');
            document.body.append(aviso);
        }
        aviso.textContent = texto;
    }
    function salvar(itens) {
        try { localStorage.setItem(chave, JSON.stringify(itens)); }
        catch { avisar('Não foi possível salvar o carrinho. Libere o armazenamento do navegador e tente novamente.'); return false; }
        atualizar(); return true;
    }
    function elemento(tag, texto, classe) {
        const el = document.createElement(tag);
        if (texto !== undefined) el.textContent = texto;
        if (classe) el.className = classe;
        return el;
    }
    function atualizar() {
        const itens = ler();
        const quantidade = itens.reduce((soma, item) => soma + item.quantidade, 0);
        document.querySelectorAll('[data-contador-carrinho]').forEach(el => el.textContent = quantidade);
        const limpar = document.querySelector('[data-limpar-carrinho]');
        if (limpar) limpar.disabled = itens.length === 0;
        const lista = document.querySelector('[data-itens-carrinho]');
        if (!lista) return;
        lista.replaceChildren();
        document.querySelector('[data-carrinho-vazio]').hidden = itens.length > 0;
        let total = 0;
        itens.forEach(item => {
            const produto = catalogo[item.id];
            total += produto.preco * item.quantidade;
            const card = elemento('article', undefined, 'item-carrinho');
            const foto = elemento('div', undefined, 'foto-carrinho');
            if (produto.imagem) {
                const img = elemento('img'); img.src = produto.imagem; img.alt = produto.nome;
                foto.append(img);
            } else foto.textContent = 'Foto em breve';
            const detalhes = elemento('div', undefined, 'detalhes-carrinho');
            detalhes.append(elemento('h2', produto.nome), elemento('p', 'Cor: ' + produto.cor), elemento('p', produto.estoque > 0 ? 'Disponível · ' + produto.estoque + ' em estoque' : 'Indisponível', 'disponibilidade'), elemento('p', 'Preço unitário: ' + moeda(produto.preco)));
            const label = elemento('label', 'Quantidade');
            const input = elemento('input'); input.type = 'number'; input.min = '1'; input.max = produto.estoque; input.step = '1'; input.value = item.quantidade;
            input.disabled = produto.estoque === 0;
            input.addEventListener('change', () => {
                const valor = Number(input.value);
                if (!Number.isInteger(valor) || valor < 1 || valor > produto.estoque) {
                    input.value = item.quantidade; avisar('Escolha uma quantidade entre 1 e ' + produto.estoque + '.'); return;
                }
                const novos = ler(); const atual = novos.find(i => i.id === item.id);
                if (atual) atual.quantidade = valor;
                if (!salvar(novos)) input.value = item.quantidade;
            });
            label.append(input); detalhes.append(label);
            const acoes = elemento('div', undefined, 'acoes-carrinho');
            const remover = elemento('button', 'Remover'); remover.type = 'button'; remover.setAttribute('aria-label', 'Remover ' + produto.nome);
            remover.addEventListener('click', () => { if (salvar(ler().filter(i => i.id !== item.id))) avisar(produto.nome + ' removido.'); });
            acoes.append(elemento('strong', moeda(produto.preco * item.quantidade)), remover);
            card.append(foto, detalhes, acoes); lista.append(card);
        });
        document.querySelector('[data-total-carrinho]').textContent = moeda(total);
        document.querySelector('[data-quantidade-resumo]').textContent = quantidade + (quantidade === 1 ? ' produto' : ' produtos');
        document.querySelector('[data-pagar]').disabled = enviandoPedido || !itens.length || itens.some(item => catalogo[item.id].estoque < item.quantidade);
        atualizarResumoFrete();
    }

    function atualizarResumoFrete() {
        const campoFrete = document.querySelector('[data-valor-frete]');
        const campoTotal = document.querySelector('[data-total-pedido]');
        if (fretePorEmpresa === null || !campoFrete || !campoTotal) return;
        const itens = ler();
        if (!itens.length) return;
        const empresas = new Set(itens.map(item => catalogo[item.id].empresa_id));
        const frete = fretePorEmpresa * Math.max(empresas.size, 1);
        const produtos = itens.reduce(
            (soma, item) => soma + catalogo[item.id].preco * item.quantidade, 0
        );
        campoFrete.textContent = moeda(frete);
        campoTotal.textContent = moeda(produtos + frete);
    }

    const formularioFrete = document.querySelector('[data-forma-frete]');
    const campoCep = formularioFrete?.querySelector('[name="cep"]');
    const resultadoFrete = document.querySelector('[data-resultado-frete]');
    const botaoConsultarCep = formularioFrete?.querySelector('[data-consultar-cep]');
    if (formularioFrete && campoCep && resultadoFrete && botaoConsultarCep) {
        function formatarCep() {
            const numeros = campoCep.value.replace(/\D/g, '').slice(0, 8);

            campoCep.value = numeros.length > 5
                ? numeros.slice(0, 5) + '-' + numeros.slice(5)
                : numeros;
        }

        fetch('/api/endereco', { credentials: 'same-origin' })
            .then(resposta => {
                if (!resposta.ok) return null;
                enderecoDaConta = true;
                return resposta.json();
            })
            .then(endereco => {
                if (!endereco) return;
                formularioFrete.querySelectorAll('[name]').forEach(campo => {
                    if (typeof endereco[campo.name] === 'string' && endereco[campo.name]) {
                        campo.value = endereco[campo.name];
                    }
                });
                enderecoNaConta = ['cep', 'logradouro', 'numero', 'bairro', 'cidade', 'uf']
                    .every(campo => endereco[campo]);
                formatarCep();
                const cepConta = campoCep.value.replace(/\D/g, '');
                if (/^\d{8}$/.test(cepConta)) consultarFrete(cepConta);
            })
            .catch(() => {});

        try {
            const enderecoSalvo = JSON.parse(
                sessionStorage.getItem(chaveEnderecoEntrega) || 'null'
            );

            if (
                enderecoSalvo
                && typeof enderecoSalvo === 'object'
                && !Array.isArray(enderecoSalvo)
            ) {
                formularioFrete.querySelectorAll('[name]').forEach(campo => {
                    if (typeof enderecoSalvo[campo.name] === 'string') {
                        campo.value = enderecoSalvo[campo.name];
                    }
                });
            }
        } catch { }

        formatarCep();
        campoCep.addEventListener('input', formatarCep);
        formularioFrete.addEventListener('input', () => { enderecoNaConta = false; });

        async function consultarFrete(cep) {
            try {
                const resposta = await fetch(`/api/frete?cep=${cep}`, {
                    credentials: 'same-origin'
                });
                const dados = await resposta.json();
                if (!resposta.ok) throw new Error(dados.erro || 'Não foi possível calcular o frete.');
                fretePorEmpresa = dados.frete_centavos;
            } catch (erro) {
                fretePorEmpresa = null;
                resultadoFrete.textContent = erro.message || 'Falha ao calcular o frete.';
            }
            atualizarResumoFrete();
        }

        async function consultarCep() {
            const cep = campoCep.value.replace(/\D/g, '');

            if (!/^\d{8}$/.test(cep)) {
                resultadoFrete.textContent = 'Informe um CEP válido com 8 números.';
                campoCep.setAttribute('aria-invalid', 'true');
                campoCep.focus();
                return;
            }

            campoCep.removeAttribute('aria-invalid');
            botaoConsultarCep.disabled = true;
            resultadoFrete.textContent = 'Consultando o CEP...';

            try {
                const resposta = await fetch(
                    `https://viacep.com.br/ws/${cep}/json/`
                );

                if (!resposta.ok) {
                    throw new Error('Não foi possível consultar o CEP agora.');
                }

                const enderecoApi = await resposta.json();

                if (enderecoApi.erro) {
                    throw new Error('CEP não encontrado. Confira o número digitado.');
                }

                if (campoCep.value.replace(/\D/g, '') !== cep) {
                    resultadoFrete.textContent =
                        'O CEP foi alterado durante a consulta. Consulte novamente.';
                    return;
                }

                const camposParaPreencher = {
                    logradouro: enderecoApi.logradouro,
                    bairro: enderecoApi.bairro,
                    cidade: enderecoApi.localidade,
                    uf: enderecoApi.uf
                };

                Object.entries(camposParaPreencher).forEach(([nome, valor]) => {
                    const campo = formularioFrete.elements.namedItem(nome);

                    if (
                        campo
                        && typeof valor === 'string'
                        && valor.trim()
                    ) {
                        campo.value = valor;
                    }
                });

                await consultarFrete(cep);

                resultadoFrete.textContent =
                    'Endereço localizado. Confira os dados e preencha o número.';
            } catch (erro) {
                resultadoFrete.textContent =
                    erro.message || 'Falha ao consultar o CEP. Tente novamente.';
            } finally {
                botaoConsultarCep.disabled = false;
            }
        }

        botaoConsultarCep.addEventListener('click', consultarCep);

        formularioFrete.addEventListener('submit', async event => {
            event.preventDefault();

            const cep = campoCep.value.replace(/\D/g, '');

            if (!/^\d{8}$/.test(cep)) {
                resultadoFrete.textContent = 'Informe um CEP válido com 8 números.';
                campoCep.setAttribute('aria-invalid', 'true');
                campoCep.focus();
                return;
            }

            campoCep.removeAttribute('aria-invalid');

            await consultarFrete(cep);

            const endereco = Object.fromEntries(
                new FormData(formularioFrete).entries()
            );

            endereco.cep = cep;
            endereco.uf = (endereco.uf || '').trim().toUpperCase();

            let enderecoGuardado = false;

            try {
                sessionStorage.setItem(
                    chaveEnderecoEntrega,
                    JSON.stringify(endereco)
                );
                enderecoGuardado = true;
            } catch { }

            if (enderecoDaConta) {
                try {
                    const csrfResposta = await fetch('/csrf-token', { credentials: 'same-origin' });
                    const csrf = await csrfResposta.json();
                    const dados = new URLSearchParams({ ...endereco, csrf_token: csrf.csrf_token });
                    const resposta = await fetch('/api/endereco', {
                        method: 'POST', credentials: 'same-origin',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: dados
                    });
                    const resultado = await resposta.json();
                    if (!resposta.ok) throw new Error(resultado.erro || 'Não foi possível salvar na conta.');
                    enderecoNaConta = true;
                    resultadoFrete.textContent = 'Endereço salvo na sua conta e frete calculado.';
                    return;
                } catch (erro) {
                    resultadoFrete.textContent = erro.message || 'Endereço guardado apenas nesta sessão.';
                    return;
                }
            }

            resultadoFrete.textContent = enderecoGuardado
                ? 'Endereço guardado nesta sessão. Entre na conta para salvar e calcular o frete.'
                : 'Endereço preenchido. Entre na conta para salvar e calcular o frete.';
        });
    }
    document.querySelectorAll('.botao-carrinho[data-produto-id]').forEach(botao => {
        const produto = catalogo[botao.dataset.produtoId];
        if (!produto) return;
        botao.disabled = produto.estoque === 0;
        botao.addEventListener('click', () => {
            const itens = ler(); const existente = itens.find(item => item.id === botao.dataset.produtoId);
            if ((existente?.quantidade || 0) >= produto.estoque) { avisar('Você já adicionou todo o estoque disponível de ' + produto.nome + '.'); return; }
            if (existente) existente.quantidade++;
            else itens.push({ id: botao.dataset.produtoId, quantidade: 1 });
            if (salvar(itens)) avisar(produto.nome + ' adicionado ao carrinho.');
        });
    });
    document.querySelector('[data-limpar-carrinho]')?.addEventListener('click', () => {
        if (!ler().length) return;
        if (salvar([])) avisar('Todos os produtos foram removidos do carrinho.');
    });
    document.querySelector('[data-pagar]')?.addEventListener('click', async event => {
        const botao = event.currentTarget;
        if (enviandoPedido) return;
        const itens = ler();
        if (!itens.length || itens.some(item => item.quantidade > catalogo[item.id].estoque)) { atualizar(); return; }
        if (enderecoDaConta && (!enderecoNaConta || fretePorEmpresa === null)) {
            avisar('Salve o endereço de entrega na sua conta antes de confirmar o pedido.');
            document.querySelector('[data-forma-frete]')
                ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }
        enviandoPedido = true;
        botao.disabled = true;
        try {
            const resposta = await window.FluxoAutenticacao.pagar(itens);

            if (resposta) {
                const carrinhoLimpo = salvar([]);

                if (carrinhoLimpo) {
                    avisar(resposta.mensagem || 'Pedido confirmado com sucesso.')
                } else {
                    avisar(
                        'Pedido confirmado, mas não foi possível limpar o carrinho. ' +
                        'Não confirme o mesmo pedido novamente.'
                    );
                }
            }

        }
        catch (erro) { avisar(erro.message || 'Não foi possível continuar. Tente novamente.'); }
        finally { enviandoPedido = false; atualizar(); }
    });
    window.addEventListener('storage', event => { if (event.key === chave || event.key === null) atualizar(); });
    atualizar();
})();
