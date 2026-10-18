(() => {
    const formulario = document.querySelector('#formularioOrcamento');

    if (!formulario) {
        return;
    }

    const descricaoProblema = formulario.querySelector('#descricaoProblema');
    const contadorCaracteres = formulario.querySelector('#contadorCaracteres');

    function atualizarContadorCaracteres() {
        contadorCaracteres.textContent =
            `${descricaoProblema.value.length} / ${descricaoProblema.maxLength}`;
    }

    descricaoProblema.addEventListener('input', atualizarContadorCaracteres);
    atualizarContadorCaracteres();

    const opcoesEntrada = formulario.querySelectorAll(
        '[name="modalidade_entrada"]'
    );
    const camposColeta = formulario.querySelector(
        '[data-endereco-coleta]'
    );

    const campoCepColeta = camposColeta?.querySelector(
        '[name="cep_coleta"]'
    );
    const statusCepColeta = camposColeta?.querySelector(
        '#status-cep-coleta'
    );

    if (!opcoesEntrada.length || !camposColeta) {
        return;
    }

    async function consultarCepColeta() {
        const cep = campoCepColeta.value.replace(/\D/g, '');

        if (!/^\d{8}$/.test(cep)) {
            campoCepColeta.setAttribute('aria-invalid', 'true');
            statusCepColeta.textContent =
                'Informe um CEP válido com 8 números.';
            return;
        }

        campoCepColeta.removeAttribute('aria-invalid');
        statusCepColeta.textContent = 'Consultando o CEP...';

        try {
            const resposta = await fetch(
                `https://viacep.com.br/ws/${cep}/json/`
            );

            if (!resposta.ok) {
                throw new Error('Não foi possível consultar o CEP agora.');
            }

            const endereco = await resposta.json();

            if (endereco.erro) {
                throw new Error('CEP não encontrado. Confira o número digitado.');
            }

            if (campoCepColeta.value.replace(/\D/g, '') !== cep) {
                statusCepColeta.textContent =
                    'O CEP foi alterado durante a consulta. Consulte novamente.';
                return;
            }

            const camposParaPreencher = {
                logradouro_coleta: endereco.logradouro,
                bairro_coleta: endereco.bairro,
                cidade_coleta: endereco.localidade,
                uf_coleta: endereco.uf
            };

            Object.entries(camposParaPreencher).forEach(([nome, valor]) => {
                const campo = camposColeta.querySelector(`[name="${nome}"]`);

                if (campo && typeof valor === 'string' && valor.trim()) {
                    campo.value = valor;
                }
            });

            statusCepColeta.textContent =
                'Endereço localizado. Confira os dados e informe o número.';
        } catch (erro) {
            statusCepColeta.textContent =
                erro.message || 'Falha ao consultar o CEP. Tente novamente.';
        }
    }

    function atualizarCamposColeta() {
        const opcaoSelecionada = formulario.querySelector(
            '[name="modalidade_entrada"]:checked'
        );

        const precisaDeColeta = opcaoSelecionada?.value === 'coleta';

        camposColeta.hidden = !precisaDeColeta;
        camposColeta.disabled = !precisaDeColeta;

        if (!precisaDeColeta) {
            camposColeta.querySelectorAll('input').forEach(campo => {
                campo.value = '';
                campo.removeAttribute('aria-invalid');
            });

            statusCepColeta.textContent = '';

        }
    }

    campoCepColeta.addEventListener('input', () => {
        const numeros = campoCepColeta.value
            .replace(/\D/g, '')
            .slice(0, 8);

        campoCepColeta.value = numeros.length > 5
            ? `${numeros.slice(0, 5)}-${numeros.slice(5)}`
            : numeros;

        campoCepColeta.removeAttribute('aria-invalid');
        statusCepColeta.textContent = '';

        [
            'logradouro_coleta',
            'bairro_coleta',
            'cidade_coleta',
            'uf_coleta'
        ].forEach(nome => {
            const campo = camposColeta.querySelector(`[name="${nome}"]`);

            if (campo) {
                campo.value = '';
            }
        });

    });

    campoCepColeta.addEventListener('blur', consultarCepColeta);

    opcoesEntrada.forEach(opcao => {
        opcao.addEventListener('change', atualizarCamposColeta);
    });

    atualizarCamposColeta();
})();