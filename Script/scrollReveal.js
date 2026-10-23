(() => {
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");

    if (motionPreference.matches || !("IntersectionObserver" in window)) return;

    const progressBar = document.createElement("div");
    progressBar.className = "scroll-progress";
    progressBar.setAttribute("aria-hidden", "true");
    document.body.append(progressBar);

    let progressFrame = 0;
    const updateScrollProgress = () => {
        if (progressFrame) return;
        progressFrame = window.requestAnimationFrame(() => {
            const scrollableHeight = document.documentElement.scrollHeight - window.innerHeight;
            const progress = scrollableHeight > 0 ? window.scrollY / scrollableHeight : 0;
            progressBar.style.setProperty("--scroll-progress", String(Math.min(1, Math.max(0, progress))));
            progressFrame = 0;
        });
    };

    window.addEventListener("scroll", updateScrollProgress, { passive: true });
    window.addEventListener("resize", updateScrollProgress, { passive: true });
    updateScrollProgress();

    const selectors = [
        "main > section",
        "main > article",
        "main.atendimento-card",
        "main > .carrinho-conteudo > section",
        "main.auth-layout > *",
        "body > section",
        ".card-acao",
        ".card-servico",
        ".card-produto",
        ".card-atalho",
        ".perfil-card",
        ".ordem-servico",
        ".orcamento-pendente",
        ".card-cliente",
        ".auth-card",
        ".etapa-card"
    ].join(",");

    const observer = new IntersectionObserver((entries, currentObserver) => {
        entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add("is-visible");
            currentObserver.unobserve(entry.target);
        });
    }, {
        threshold: 0.12,
        rootMargin: "0px 0px -36px 0px"
    });

    document.querySelectorAll(selectors).forEach((element, index) => {
        element.classList.add("scroll-reveal");
        element.style.setProperty("--scroll-reveal-delay", `${(index % 4) * 55}ms`);
        observer.observe(element);
    });
})();
