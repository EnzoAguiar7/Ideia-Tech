import os
import hashlib
import time
import secrets
import sqlite3
from pathlib import Path
from flask import Flask, abort, redirect, send_from_directory, request, session, render_template, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(
    __name__,
    static_folder=None,
    template_folder="../Pages"
)
app.secret_key = secrets.token_hex(32)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["RECUPERACAO_LOCAL"] =(
    os.environ.get("RECUPERACAO_LOCAL") == "1"
)
raiz = Path(__file__).resolve().parent.parent
caminho_banco = raiz / "BackEnd" / "dados" / "ideia_tech.db"
def mostrar_erro(pagina, mensagem, codigo=400):
    flash(mensagem,"erro")

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return render_template(
        pagina,
        csrf_token=session["csrf_token"]
    ), codigo

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
        return mostrar_erro("cadastroCliente.html", "Informe o nome e telefone válidos.", 400)

    if "@" not in email or len(email) > 254:
        return mostrar_erro("cadastroCliente.html", "Informe um e-mail válido.", 400)

    if len(senha) < 8:
        return mostrar_erro("cadastroCliente.html", "A senha precisa ter pelo menos 8 caracteres.", 400)

    if senha != confirmacao:
        return mostrar_erro("cadastroCliente.html", "As senhas precisam ser iguais.", 400)

    if aceita_termos != "on":
        return mostrar_erro("cadastroCliente.html", "Você precisa aceitar os termos.", 400)

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
        return mostrar_erro("cadastroCliente.html", "Não foi possível cadastrar. O e-mail pode já estar em uso.", 409)
    finally:
        conexao.close()

    flash("Conta cadastrada com sucesso. Entre com seu e-mail e senha.", "sucesso")
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
        return mostrar_erro("login.html", "E-mail ou senha incorretos.", 401)

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


@app.post("/logout")
def sair():
    session.clear()
    flash("Você saiu da conta.", "sucesso")
    return redirect("/Pages/login.html")


@app.route("/Pages/editarPerfil.html", methods=["GET", "POST"])
def editar_perfil():
    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return redirect("/Pages/login.html")

    if request.method == "POST":
        token_enviado = request.form.get("csrf_token", "")
        token_esperado = session.get("csrf_token", "")

        if not token_esperado or not secrets.compare_digest(
            token_enviado, token_esperado
        ):
            abort(400)

    conexao = sqlite3.connect(caminho_banco)
    conexao.row_factory = sqlite3.Row
    erro = None

    try:
        usuario = conexao.execute(
            "SELECT nome, telefone FROM usuarios WHERE id = ?",
            (usuario_id,)
        ).fetchone()

        if usuario is None:
            session.clear()
            return redirect("/Pages/login.html")

        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            telefone = request.form.get("telefone", "").strip()

            usuario = {"nome": nome, "telefone": telefone}

            if not 3 <= len(nome) <= 120:
                erro = "O nome deve ter entre 3 e 120 caracteres."
            elif not telefone or len(telefone) > 20:
                erro = "Informe um telefone com até 20 caracteres."
            else:
                conexao.execute(
                    """
                    UPDATE usuarios
                    SET nome = ?, telefone = ?
                    WHERE id = ?
                    """,
                    (nome, telefone, usuario_id)
                )
                conexao.commit()

                flash("Perfil atualizado com sucesso.", "sucesso")
                return redirect("/Pages/Perfil.html")
    finally:
        conexao.close()

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    resposta = app.make_response(
        render_template(
            "editarPerfil.html",
            usuario=usuario,
            erro=erro,
            csrf_token=session["csrf_token"]
        )
    )
    resposta.headers["Cache-Control"] = "no-store"

    return resposta


@app.get("/Pages/cadastroEmpresa.html")
def pagina_cadastro_empresa():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return render_template(
        "cadastroEmpresa.html",
        csrf_token=session["csrf_token"]
    )


@app.post("/register/empresa")
def cadastrar_empresa():
    token_enviado = request.form.get("csrf_token", "")
    token_esperado = session.get("csrf_token", "")

    if not token_esperado or not secrets.compare_digest(
        token_enviado, token_esperado
    ):
        return mostrar_erro("cadastroEmpresa.html", "Atualize a página e tente novamente.", 400)

    nome_empresa = request.form.get("nomeEmpresa", "").strip()
    responsavel = request.form.get("nomeResponsavel", "").strip()
    telefone = request.form.get("telefone", "").strip()
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "")
    confirmacao = request.form.get("confirmarSenha", "")
    aceita_termos = request.form.get("aceitaTermos")

    cnpj = request.form.get("cnpj", "").strip()
    cnpj = "".join(c for c in cnpj if c.isalnum()).upper() or None

    if not 2 <= len(nome_empresa) <= 150:
        return mostrar_erro("cadastroEmpresa.html", "Informe um nome de empresa válido.", 400)

    if not 3 <= len(responsavel) <= 120:
        return mostrar_erro("cadastroEmpresa.html", "Informe um nome de responsável válido.", 400)

    if not telefone or len(telefone) > 20:
        return mostrar_erro("cadastroEmpresa.html", "Insira um número de telefone válido.", 400)

    if "@" not in email or len(email) > 254:
        return mostrar_erro("cadastroEmpresa.html", "Insira um e-mail válido.", 400)

    if cnpj and len(cnpj) != 14:
        return mostrar_erro("cadastroEmpresa.html", "Confira o tamanho do CNPJ.", 400)

    if len(senha) < 8 or senha != confirmacao:
        return mostrar_erro("cadastroEmpresa.html", "Use uma senha de pelo menos 8 caracteres e confirme se estão iguais.", 400)

    if aceita_termos != "on":
        return mostrar_erro("cadastroEmpresa.html", "Aceite os termos.", 400)

    senha_hash = generate_password_hash(senha)
    conexao = sqlite3.connect(caminho_banco)
    conexao.execute("PRAGMA foreign_keys = ON")

    try:
        with conexao:
            cursor = conexao.execute(
                """
                INSERT INTO usuarios (nome, email, telefone, senha_hash)
                VALUES (?, ?, ?, ?)
                """,
                (responsavel, email, telefone, senha_hash)
            )
            usuario_id = cursor.lastrowid

            cursor = conexao.execute(
                "INSERT INTO empresas (nome, telefone, cnpj) VALUES (?, ?, ?)",
                (nome_empresa, telefone, cnpj)
            )
            empresa_id = cursor.lastrowid

            conexao.execute(
                """
                INSERT INTO empresa_usuarios (empresa_id, usuario_id, papel)
                VALUES (?, ?, ?)
                """,
                (empresa_id, usuario_id, "administrador")
            )
    except sqlite3.IntegrityError:
        return mostrar_erro("cadastroEmpresa.html", "Cadastro não realizado. Confira se o e-mail ou CNPJ já existe.", 409)
    finally:
        conexao.close()

    flash("Empresa cadastrada com sucesso. Entre com seu e-mail e senha.", "sucesso")
    return redirect("/Pages/login.html")


@app.get("/Pages/login.html", defaults={"pagina": "login.html"})
@app.get("/Pages/cadastroCliente.html", defaults={"pagina": "cadastroCliente.html"})
def pagina_autenticação(pagina):
    return render_template(pagina)

@app.get("/Pages/recuperarSenha.html")
def pagina_recuperar_senha():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return render_template(
        "recuperarSenha.html",
        csrf_token=session["csrf_token"]
        )

@app.post("/recuperar-senha")
def solicitar_recuperacao():
    token_enviado = request.form.get("csrf_token", "")
    token_esperado = session.get("csrf_token", "")

    if not token_esperado or not secrets.compare_digest(
        token_enviado, token_esperado
    ):
        return mostrar_erro(
            "recuperarSenha.html",
            "Atualize a pagina e tente novamente.",
            400
        )
    email = request.form.get("email","").strip().lower()

    if "@" not in email or len(email) > 254:
        return mostrar_erro(
            "recuperarSenha.html",
            "Informe um e-mail válido.",
            400
        )

    conexao = sqlite3.connect(caminho_banco)
    conexao.execute("PRAGMA foreign_keys = ON")

    try:
        usuario = conexao.execute(
            "SELECT id FROM usuarios WHERE email = ?",
            (email,)
        ).fetchone()

        if usuario:
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            expira_em = int(time.time()) + 1800

            with conexao:
                conexao.execute(
                    "DELETE FROM recuperacao_senha WHERE usuario_id = ?",
                    (usuario[0],)
                )
                conexao.execute(
                    """
                    INSERT INTO recuperacao_senha
                            (usuario_id, token_hash, expira_em)
                    VALUES (?, ?, ?, ?)
                    """,
                    (usuario[0], token_hash, expira_em)
                )

            if app.config["RECUPERACAO_LOCAL"]:
                print(
                    "LINK LOCAL:"
                    f"http://127.0.0.1:5000/redefinir-senha/{token}",
                    flush=True
                )

    finally:
        conexao.close()

    flash(
        "Se o e-mail estiver cadastrado, você receberá instruções.",
        "sucesso"
    )   

    return redirect("/Pages/recuperarSenha.html")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
