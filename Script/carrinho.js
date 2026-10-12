(() => {
    const chave = 'ideiaTech.carrinho.v1';
    const catalogo = window.CatalogoProdutos;
    const moeda = valor => (valor / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    function ler() {
        try {
            const dados = JSON.parse(localStorage.getItem(chave) || '[]');
            if (!Array.isArray(dados)) return [];
            const vistos = new Set();
            return dados.filter(item => item && Object.hasOwn(catalogo, item.id) && Number.isInteger(item.quantidade) && item.quantidade > 0 && !vistos.has(item.id) && vistos.add(item.id))
                .map(item => ({ id: item.id, quantidade: Math.min(item.quantidade, Math.max(1, catalogo[item.id].estoque)) }));
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
        document.querySelector('[data-pagar]').disabled = !itens.length || itens.some(item => catalogo[item.id].estoque < item.quantidade);
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
        const itens = ler();
        if (!itens.length || itens.some(item => item.quantidade > catalogo[item.id].estoque)) { atualizar(); return; }
        botao.disabled = true;
        try { await window.FluxoAutenticacao.pagar(itens); }
        catch (erro) { avisar(erro.message || 'Não foi possível continuar. Tente novamente.'); }
        finally { atualizar(); }
    });
    window.addEventListener('storage', event => { if (event.key === chave || event.key === null) atualizar(); });
    atualizar();
})();
