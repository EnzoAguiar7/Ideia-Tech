const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { runInNewContext } = require('node:vm');

const codigo = readFileSync(join(__dirname, '../fluxoAutenticacao.js'), 'utf8');

function preparar(respostas) {
    const chamadas = [];
    const redirecionamentos = [];
    const armazenamento = new Map();
    const window = {};
    runInNewContext(codigo, {
        window, URL, URLSearchParams,
        location: {
            href: 'http://localhost:5000/Pages/Carrinho.html',
            origin: 'http://localhost:5000', search: '',
            assign: url => redirecionamentos.push(url)
        },
        sessionStorage: {
            getItem: chave => armazenamento.get(chave),
            setItem: (chave, valor) => armazenamento.set(chave, valor)
        },
        document: { querySelectorAll: () => [], querySelector: () => null },
        fetch: async (url, opcoes) => {
            chamadas.push({ url, opcoes });
            const resposta = respostas.shift();
            assert.ok(resposta, 'Requisição inesperada');
            return resposta;
        }
    });
    return { fluxo: window.FluxoAutenticacao, chamadas, redirecionamentos, armazenamento };
}

const resposta = (status, dados) => ({
    ok: status >= 200 && status < 300, status,
    json: async () => dados
});
const token = () => resposta(200, { csrf_token: 'token-da-sessao' });
const itens = [{ id: 'produto-1', quantidade: 2, preco: 1 }];

test('obtém CSRF e envia somente IDs e quantidades com a sessão', async () => {
    const confirmado = { mensagem: 'Pedido confirmado com sucesso.', pedidos: [10] };
    const { fluxo, chamadas, redirecionamentos } = preparar([token(), resposta(201, confirmado)]);
    assert.deepEqual(await fluxo.pagar(itens), confirmado);
    assert.deepEqual(chamadas.map(c => c.url), ['/csrf-token', '/pedidos']);
    for (const chamada of chamadas) assert.equal(chamada.opcoes.credentials, 'same-origin');
    const envio = chamadas[1].opcoes;
    assert.equal(envio.method, 'POST');
    assert.equal(envio.body.get('csrf_token'), 'token-da-sessao');
    assert.deepEqual(JSON.parse(envio.body.get('itens')), [{ id: 'produto-1', quantidade: 2 }]);
    assert.equal(redirecionamentos.length, 0);
});

test('sessão expirada leva ao login com retorno para o carrinho', async () => {
    const { fluxo, redirecionamentos, armazenamento } = preparar([
        token(), resposta(401, { erro: 'Entre na sua conta.' })
    ]);
    await fluxo.pagar(itens);
    const destino = new URL(redirecionamentos[0]);
    assert.equal(destino.pathname, '/Pages/login.html');
    assert.equal(destino.searchParams.get('next'), 'http://localhost:5000/Pages/Carrinho.html');
    assert.equal(armazenamento.get('ideiaTech.retornoLogin'), 'http://localhost:5000/Pages/Carrinho.html');
});

for (const status of [400, 403, 500]) {
    test(`propaga erro ${status} sem anunciar confirmação ou redirecionar`, async () => {
        const { fluxo, redirecionamentos } = preparar([token(), resposta(status, { erro: 'Pedido recusado.' })]);
        await assert.rejects(fluxo.pagar(itens), /Pedido recusado/);
        assert.equal(redirecionamentos.length, 0);
    });
}

test('não envia pedido se o token estiver ausente ou indisponível', async () => {
    for (const respostaToken of [resposta(500, {}), resposta(200, {})]) {
        const { fluxo, chamadas } = preparar([respostaToken]);
        await assert.rejects(fluxo.pagar(itens));
        assert.equal(chamadas.length, 1);
    }
});

test('trata resposta HTML de erro sem falhar na leitura do JSON', async () => {
    const { fluxo } = preparar([token(), {
        ok: false, status: 400, json: async () => { throw new SyntaxError('HTML'); }
    }]);
    await assert.rejects(fluxo.pagar(itens), /Não foi possível confirmar/);
});
