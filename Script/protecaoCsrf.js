(() => {
    document.querySelectorAll("form").forEach((form) => {
        // Os formulários AJAX obtêm e enviam o CSRF no próprio controlador.
        if (form.dataset.authAjax === "true") {
            return;
        }

        if (form.method.toUpperCase() !== "POST") {
            return;
        }

        form.addEventListener("submit", async (evento) => {
            if (form.dataset.csrfReady === "true") {
                return;
            }

            evento.preventDefault();

            if (form.dataset.csrfPending === "true") {
                return;
            }

            form.dataset.csrfPending = "true";

            try {
                const resposta = await fetch("/csrf-token", {
                    credentials: "same-origin",
                    headers: { Accept: "application/json" }
                });

                if (!resposta.ok) {
                    throw new Error("Não foi possível obter o token.");
                }

                const dados = await resposta.json();

                if (!dados.csrf_token) {
                    throw new Error("A resposta não contém o token.");
                }

                let campo = form.querySelector('input[name="csrf_token"]');

                if (!campo) {
                    campo = document.createElement("input");
                    campo.type = "hidden";
                    campo.name = "csrf_token";
                    form.append(campo);
                }

                campo.value = dados.csrf_token;
                form.dataset.csrfReady = "true";
                form.requestSubmit();
            } catch {
                form.dataset.csrfPending = "false";

                let aviso = form.querySelector("[data-csrf-error]");

                if (!aviso) {
                    aviso = document.createElement("p");
                    aviso.dataset.csrfError = "true";
                    aviso.setAttribute("role", "alert");
                    form.prepend(aviso);
                }

                aviso.textContent =
                    "Não foi possível proteger o envio. Atualize a página e tente novamente.";
            }
        });
    });
})();
