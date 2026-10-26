(() => {
    const root = document.body;
    const id = Number(root.dataset.conversaId);
    const form = document.getElementById("chatForm");
    const list = document.getElementById("chatMessages");
    if (!id || !form || !list) return;

    const input = document.getElementById("messageInput");
    const button = form.querySelector("button[type='submit']");
    if (typeof window.io !== "function") {
        const error = document.createElement("p");
        error.className = "connection-notice";
        error.textContent = "Não foi possível carregar o cliente de mensagens. Verifique sua conexão e recarregue a página.";
        list.prepend(error);
        input.disabled = true;
        button.disabled = true;
        return;
    }
    const socket = window.io("/suporte", { auth: { csrf_token: root.dataset.csrfToken } });
    const seen = new Set();

    function appendMessage(message) {
        if (seen.has(message.id)) return;
        seen.add(message.id);
        const row = document.createElement("article");
        row.className = `message-row ${message.tipo === root.dataset.papel ? "mine" : "theirs"}`;
        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        const author = document.createElement("strong");
        author.className = "message-author";
        author.textContent = message.tipo === "desenvolvedor" ? "Suporte IdeiaTech" : message.autor;
        const text = document.createElement("p");
        text.textContent = message.texto;
        const time = document.createElement("time");
        time.dateTime = message.criada_em;
        time.textContent = message.criada_em;
        bubble.append(author, text, time);
        row.append(bubble);
        list.append(row);
        list.scrollTop = list.scrollHeight;
    }

    function setClosed() {
        input.disabled = true;
        button.disabled = true;
        input.placeholder = "Esta conversa foi encerrada.";
        const closeButton = document.getElementById("closeConversation");
        const badge = document.getElementById("closedBadge");
        if (closeButton) closeButton.hidden = true;
        if (badge) badge.hidden = false;
    }

    fetch(`/api/suporte/conversas/${id}/mensagens`, { credentials: "same-origin" })
        .then((response) => {
            if (!response.ok) throw new Error("Não foi possível carregar as mensagens.");
            return response.json();
        })
        .then((data) => {
            data.mensagens.forEach(appendMessage);
            if (data.conversa.status !== "aberta") setClosed();
        })
        .catch(() => {
            const error = document.createElement("p");
            error.className = "chat-error";
            error.textContent = "Não foi possível carregar o histórico. Atualize a página para tentar novamente.";
            list.append(error);
        });

    socket.on("connect", () => socket.emit("entrar_conversa", { conversa_id: id }));
    socket.on("nova_mensagem", appendMessage);
    socket.on("conversa_encerrada", (data) => { if (data.conversa_id === id) setClosed(); });
    socket.on("connect_error", () => {
        const notice = document.createElement("p");
        notice.className = "connection-notice";
        notice.textContent = "Reconectando ao suporte…";
        if (!list.querySelector(".connection-notice")) list.prepend(notice);
    });
    socket.on("connect", () => list.querySelector(".connection-notice")?.remove());

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const texto = input.value.trim();
        if (!texto || socket.disconnected) return;
        button.disabled = true;
        socket.emit("enviar_mensagem", { conversa_id: id, texto }, (result) => {
            button.disabled = false;
            if (result?.ok) {
                input.value = "";
                input.style.height = "auto";
            } else {
                input.setCustomValidity(result?.erro || "Não foi possível enviar a mensagem.");
                input.reportValidity();
                input.setCustomValidity("");
            }
        });
    });
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });
    input.addEventListener("input", () => {
        input.style.height = "auto";
        input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
    });

    document.getElementById("closeConversation")?.addEventListener("click", () => {
        if (!window.confirm("Encerrar esta conversa de suporte?")) return;
        socket.emit("encerrar_conversa", { conversa_id: id }, (result) => {
            if (result?.ok) setClosed();
        });
    });
})();
