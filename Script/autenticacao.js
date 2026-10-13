(() => {
    async function obterTokenCsrf() {
        const resposta = await fetch("/csrf-token", {
            credentials: "same-origin",
            headers: { Accept: "application/json" }
        });

        if (!resposta.ok) {
            throw new Error("Não foi possível obter o token de segurança.");
        }

        const dados = await resposta.json();
        if (!dados.csrf_token) {
            throw new Error("O servidor não retornou o token de segurança.");
        }

        return dados.csrf_token;
    }

    function prepararConfirmacaoSenha(formulario) {
        const senha = formulario.querySelector('[name="senha"]');
        const confirmacao = formulario.querySelector('[name="confirmarSenha"]');

        if (!senha || !confirmacao) return;

        const validar = () => {
            confirmacao.setCustomValidity(
                confirmacao.value && confirmacao.value !== senha.value
                    ? "As senhas não coincidem."
                    : ""
            );
        };

        senha.addEventListener("input", validar);
        confirmacao.addEventListener("input", validar);
    }

    document.querySelectorAll('form[data-auth-ajax="true"]').forEach((formulario) => {
        prepararConfirmacaoSenha(formulario);

        formulario.addEventListener("submit", async (evento) => {
            evento.preventDefault();

            const botao = evento.submitter || formulario.querySelector('[type="submit"]');
            let mensagem = formulario.querySelector("[data-form-message]");

            if (!mensagem) {
                mensagem = document.createElement("p");
                mensagem.dataset.formMessage = "true";
                mensagem.className = "auth-form-feedback";
                mensagem.setAttribute("aria-live", "polite");
                formulario.append(mensagem);
            }

            botao.disabled = true;
            mensagem.hidden = false;
            mensagem.setAttribute("role", "status");
            mensagem.textContent = "Enviando...";

            try {
                const dadosFormulario = new FormData(formulario);
                dadosFormulario.set("csrf_token", await obterTokenCsrf());

                const resposta = await fetch(formulario.action, {
                    method: "POST",
                    body: dadosFormulario,
                    credentials: "same-origin",
                    headers: { Accept: "text/plain" }
                });

                if (resposta.redirected) {
                    window.location.assign(resposta.url);
                    return;
                }

                const tipoResposta = resposta.headers.get("content-type") || "";
                const texto = (await resposta.text()).trim();
                const paginaHtmlDeErro = !resposta.ok
                    && tipoResposta.includes("text/html")
                    && texto.startsWith("<");

                mensagem.textContent = resposta.status === 429
                    ? "Muitas tentativas. Aguarde um pouco e tente novamente."
                    : paginaHtmlDeErro
                        ? "Não foi possível concluir a solicitação. Atualize a página e tente novamente."
                        : texto || (
                            resposta.ok
                                ? "Solicitação concluída."
                                : "Não foi possível concluir. Confira os dados e tente novamente."
                        );
                mensagem.setAttribute("role", resposta.ok ? "status" : "alert");
            } catch (erro) {
                mensagem.textContent = erro instanceof TypeError
                    ? "Falha de conexão. Verifique se o servidor está ativo e tente novamente."
                    : "Não foi possível proteger o envio. Atualize a página e tente novamente.";
                mensagem.setAttribute("role", "alert");
            } finally {
                botao.disabled = false;
            }
        });
    });
})();
