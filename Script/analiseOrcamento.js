(() => {
    const formulario = document.querySelector('#formularioOrcamento');
    if (!formulario) return;

    const painel = document.querySelector('#painelResultado');
    const espera = document.querySelector('#resultadoEspera');
    const carregando = document.querySelector('#resultadoCarregando');
    const resultado = document.querySelector('#resultadoConteudo');
    const erroAnalise = document.querySelector('#erroAnalise');
    const botao = document.querySelector('#botaoAnalisar');
    const status = document.querySelector('#statusIdeiaAI');
    const conversa = document.querySelector('#conversaIdeiaAI');

    function mostrarEstado(estado) {
        espera.style.display = estado === 'espera' ? 'flex' : 'none';
        carregando.style.display = estado === 'carregando' ? 'flex' : 'none';
        resultado.style.display = estado === 'resultado' ? 'block' : 'none';
        erroAnalise.style.display = estado === 'erro' ? 'block' : 'none';
        painel.setAttribute('aria-busy', estado === 'carregando' ? 'true' : 'false');
    }

    function mostrarConversa(relato, resposta) {
        conversa.replaceChildren();

        const mensagemCliente = document.createElement('div');
        mensagemCliente.className = 'mensagem-cliente-ia';
        const textoCliente = document.createElement('p');
        textoCliente.textContent = relato;
        mensagemCliente.append(textoCliente);

        const mensagemAssistente = document.createElement('div');
        mensagemAssistente.className = 'mensagem-ia';
        const icone = document.createElement('i');
        icone.dataset.lucide = 'bot';
        icone.setAttribute('aria-hidden', 'true');
        const textoAssistente = document.createElement('p');
        textoAssistente.textContent = resposta;
        mensagemAssistente.append(icone, textoAssistente);

        conversa.append(mensagemCliente, mensagemAssistente);
        window.lucide?.createIcons();
    }

    async function obterTokenCsrf() {
        const resposta = await fetch('/csrf-token', {
            credentials: 'same-origin',
            headers: { Accept: 'application/json' }
        });
        const dados = await resposta.json();
        if (!resposta.ok || !dados.csrf_token) {
            throw new Error('Não foi possível iniciar a análise segura. Atualize a página e tente novamente.');
        }
        return dados.csrf_token;
    }

    function preencherPerguntas(perguntas) {
        const bloco = document.querySelector('#blocoPerguntas');
        const lista = document.querySelector('#perguntasDiagnostico');
        lista.replaceChildren();

        (Array.isArray(perguntas) ? perguntas : []).slice(0, 3).forEach((pergunta) => {
            const item = document.createElement('li');
            item.textContent = pergunta;
            lista.append(item);
        });

        bloco.hidden = lista.childElementCount === 0;
    }

    formulario.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (botao.disabled) return;

        const camposObrigatoriosDaAnalise = [
            formulario.querySelector('#marca'),
            formulario.querySelector('#modelo'),
            formulario.querySelector('#descricaoProblema')
        ];
        const primeiroCampoInvalido = camposObrigatoriosDaAnalise.find(
            (campo) => !campo.checkValidity()
        );
        if (primeiroCampoInvalido) {
            primeiroCampoInvalido.reportValidity();
            return;
        }

        const dados = {
            marca: formulario.querySelector('#marca').value,
            modelo: formulario.querySelector('#modelo').value.trim(),
            categoria_problema: formulario.querySelector('#categoriaProblema').value,
            descricao_problema: formulario.querySelector('#descricaoProblema').value.trim(),
            modalidade_entrada: formulario.querySelector('[name="modalidade_entrada"]:checked')?.value || 'loja'
        };
        if (dados.modalidade_entrada === 'coleta') {
            ['cep', 'logradouro', 'numero', 'bairro', 'cidade', 'uf'].forEach((campo) => {
                const entrada = formulario.querySelector(`#${campo}-coleta`);
                dados[`${campo}_coleta`] = entrada?.value.trim() || '';
            });
        }

        botao.disabled = true;
        status.textContent = 'Analisando relato...';
        erroAnalise.textContent = '';
        mostrarEstado('carregando');
        mostrarConversa(dados.descricao_problema, 'Estou analisando os sintomas informados.');

        try {
            const csrfToken = await obterTokenCsrf();
            const resposta = await fetch('/api/orcamento/analisar', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrfToken
                },
                body: JSON.stringify(dados)
            });
            const analise = await resposta.json();

            if (!resposta.ok) {
                throw new Error(analise.erro || 'Não foi possível analisar o relato agora.');
            }

            document.querySelector('#servicoIdentificado').textContent = analise.servico;
            document.querySelector('#explicacaoDiagnostico').textContent = analise.explicacao;
            document.querySelector('#orientacaoDiagnostico').textContent = analise.orientacao;
            const faixa = analise.faixa_preco;
            const formatarReais = (centavos) => (centavos / 100).toLocaleString('pt-BR', {
                style: 'currency', currency: 'BRL'
            });
            document.querySelector('#precoEstimado').textContent = faixa
                ? `${formatarReais(faixa.minimo_centavos)} a ${formatarReais(faixa.maximo_centavos)}`
                : 'Sem referência confiável para esta categoria';
            const avisoPreco = document.querySelector('#fontePrecoEstimado');
            avisoPreco.textContent = faixa
                ? `Faixa de referência de mercado (valor médio do intervalo: ${formatarReais(faixa.medio_centavos)}). ${faixa.fonte} O valor final será definido pela assistência após analisar o aparelho.`
                : 'Ainda não há dados de mercado suficientes para estimar esta categoria. O valor final será informado após análise técnica.';
            const prazo = analise.prazo_estimado;
            const formatarDias = (dias) => String(dias).replace('.', ',');
            document.querySelector('#prazoEstimado').textContent = prazo
                ? `${prazo.minimo_dias_uteis} a ${prazo.maximo_dias_uteis} dias úteis · média ${formatarDias(prazo.medio_dias_uteis)} dias úteis`
                : 'A estimativa será informada após a análise';
            document.querySelector('#avisoPrazoEstimado').textContent = prazo?.aviso ||
                'O prazo será confirmado pela assistência após a análise técnica.';
            document.querySelector('#orientacaoDiagnostico').parentElement.hidden = !analise.orientacao;
            preencherPerguntas(analise.perguntas);

            mostrarConversa(
                dados.descricao_problema,
                analise.explicacao
            );
            status.textContent = 'Análise concluída';
            mostrarEstado('resultado');
        } catch (erro) {
            erroAnalise.textContent = erro.message || 'A análise não ficou disponível. Tente novamente.';
            status.textContent = 'Análise indisponível';
            mostrarConversa(dados.descricao_problema, erroAnalise.textContent);
            mostrarEstado('erro');
        } finally {
            botao.disabled = false;
        }
    });
})();
