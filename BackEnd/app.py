import secrets
import sqlite3
from pathlib import Path
from flask import Flask, abort, redirect, send_from_directory, request, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(
    __name__,
    static_folder=None,
    template_folder="../Pages"
)
app.secret_key = secrets.token_hex(32)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
raiz = Path(__file__).resolve().parent.parent
caminho_banco = raiz / "Backend" / "dados" / "ideia_tech.db"


@app.get("/")
def inicio():
    return redirect("/Pages/index.html")


@app.get("/<pasta>/<path:arquivo>")
def arquivos_publicos(pasta, arquivo):
    if pasta not in {"Pages", "Style", "Script", "Assets"}:
        abort(404)

    return send_from_directory(raiz / pasta, arquivo)


@app.post("/register/cliente")
def cadastrar_cliente():
    nome = request.form.get("nome", "").strip()
    email = request.form.get("email", "").strip().lower()
    telefone = request.form.get("telefone", "").strip()
    senha = request.form.get("senha", "")
    confirmacao = request.form.get("confirmarSenha", "")
    aceita_termos = request.form.get("aceitaTermos", "")

    if len(nome) < 3 or not telefone:
        return "Informe o nome e telefone válidos.", 400

    if "@" not in email or len(email) > 254:
        return "Informe um e-mail válido.", 400

    if len(senha) < 8:
        return "A senha precisa ter pelo menos 8 caracteres.", 400

    if senha != confirmacao:
        return "As senhas precisam ser iguais.", 400

    if aceita_termos != "on":
        return "Você precisa aceitar os termos.", 400

    senha_hash = generate_password_hash(senha)
    conexao = sqlite3.connect(caminho_banco)

    try:
        conexao.execute(
            """
            INSERT INTO usuarios (nome, email, telefone, senha_hash)
            VALUES (?, ?, ?, ?)
            """,
            (nome, email, telefone, senha_hash)
        )
        conexao.commit()
    except sqlite3.IntegrityError:
        return "Não foi possível cadastrar. O e-mail pode já estar em uso.", 409
    finally:
        conexao.close()

    return redirect("/Pages/login.html")


@app.post("/login")
def entrar():
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("password", "")

    conexao = sqlite3.connect(caminho_banco)
    conexao.row_factory = sqlite3.Row

    try:
        usuario = conexao.execute(
            "SELECT id, senha_hash FROM usuarios WHERE email = ?",
            (email,)
        ).fetchone()
    finally:
        conexao.close()

    if not usuario or not check_password_hash(usuario["senha_hash"], senha):
        return "E-mail ou senha incorretos.", 401

    session.clear()
    session["usuario_id"] = usuario["id"]

    return redirect("/Pages/Perfil.html")


@app.get("/Pages/Perfil.html")
def perfil():
    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return redirect("/Pages/login.html")

    conexao = sqlite3.connect(caminho_banco)
    conexao.row_factory = sqlite3.Row

    try:
        usuario = conexao.execute(
            "SELECT nome, email, telefone FROM usuarios WHERE id = ?",
            (usuario_id,)
        ).fetchone()
    finally:
        conexao.close()

    if usuario is None:
        session.clear()
        return redirect("/Pages/login.html")

    resposta = app.make_response(
        render_template("Perfil.html", usuario=usuario)
    )
    resposta.headers["Cache-Control"] = "no-store"

    return resposta


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)