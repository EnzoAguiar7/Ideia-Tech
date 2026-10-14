// Este arquivo usa defer: o HTML e a biblioteca já estão carregados.
const areaEmpresarial = document.documentElement.dataset.responsive
    ?.split(" ").includes("Empresa/painelEmpresa");

lucide.createIcons({
    icons: lucide.icons,
    attrs: {
        "stroke-width": areaEmpresarial ? 1.7 : 2
    }
});
