const parametros = new URLSearchParams(window.location.search);
const token = parametros.get("token");

const formularioPedido = document.querySelector("#formRecuperarSenha");
const formularioRedefinicao = document.querySelector("#formRedefinirSenha");
const campoToken = document.querySelector("#tokenRedefinicao");


if (token) {
    formularioPedido.hidden = true;
    formularioRedefinicao.hidden = false;
    campoToken.value = token;
}
