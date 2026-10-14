import secrets
import sqlite3
import os
import hashlib
import hmac
import smtplib
import ssl
import time
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from flask import Flask, abort, flash, redirect, send_from_directory, request, session, render_template, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlsplit
from configuracao import carregar_configuracao

carregar_configuracao()

app = Flask(
    __name__,
    static_folder=None,
    template_folder="../Pages"
)
chave_secreta = os.environ.get("IDEIATECH_SECRET_KEY")

if not chave_secreta:
    raise RuntimeError(
        "Defina a variável de ambiente IDEIATECH_SECRET_KEY antes de iniciar o servidor."
    )

app.config["SECRET_KEY"] = chave_secreta
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("APP_ENV") == "production"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
app.config["SESSION_REFRESH_EACH_REQUEST"] = False
app.config["RECUPERACAO_LOCAL"] = os.environ.get("RECUPERACAO_LOCAL") == "1"

if app.config["RECUPERACAO_LOCAL"] and os.environ.get("APP_ENV") == "production":
    raise RuntimeError("RECUPERACAO_LOCAL não pode ser habilitado em produção.")

LIMITE_LOGIN_EMAIL = 5
LIMITE_LOGIN_IP = 20
JANELA_LOGIN_SEGUNDOS = 15 * 60
LIMITE_RECUPERACAO_EMAIL = 3
LIMITE_RECUPERACAO_IP = 10
JANELA_RECUPERACAO_SEGUNDOS = 60 * 60
LIMITE_REDEFINICAO_IP = 10
HASH_SENHA_FALSA = generate_password_hash(secrets.token_urlsafe(32))
raiz = Path(__file__).resolve().parent.parent
caminho_banco = raiz / "BackEnd" / "dados" / "ideia_tech.db"
caminho_banco.parent.mkdir(parents=True, exist_ok=True)




def conectar_banco():
    conexao = sqlite3.connect(caminho_banco)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


@app.get("/csrf-token")
def obter_token_csrf():
    token = session.get("csrf_token")

    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token

    resposta = jsonify({"csrf_token": token})
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def enviar_email_recuperacao(destinatario, link_redefinicao):
    if app.config["RECUPERACAO_LOCAL"]:
        app.logger.warning("Link local de redefinição de senha: %s", link_redefinicao)
        return

    servidor_smtp = os.environ.get("SMTP_HOST")
    porta_smtp = int(os.environ.get("SMTP_PORT", "587"))
    usuario_smtp = os.environ.get("SMTP_USERNAME")
    senha_smtp = os.environ.get("SMTP_PASSWORD")
    remetente = os.environ.get("SMTP_FROM")

    if not all((servidor_smtp, usuario_smtp, senha_smtp, remetente)):
        raise RuntimeError("As configurações SMTP estão incompletas.")

    base_publica = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    partes_url = urlsplit(base_publica)

    if partes_url.scheme not in {"http", "https"} or not partes_url.netloc:
        raise RuntimeError("PUBLIC_BASE_URL não é uma URL válida.")

    if os.environ.get("APP_ENV") == "production" and partes_url.scheme != "https":
        raise RuntimeError("PUBLIC_BASE_URL precisa usar HTTPS em produção.")

    mensagem = EmailMessage()
    mensagem["Subject"] = "Redefinição de senha | IdeiaTech"
    mensagem["From"] = remetente
    mensagem["To"] = destinatario
    mensagem.set_content(
        "Recebemos uma solicitação para redefinir sua senha.\n\n"
        f"Use este link em até 30 minutos: {link_redefinicao}\n\n"
        "Se você não solicitou a redefinição, ignore este e-mail."
    )

    contexto_tls = ssl.create_default_context()
    with smtplib.SMTP(servidor_smtp, porta_smtp, timeout=15) as servidor:
        servidor.ehlo()
        servidor.starttls(context=contexto_tls)
        servidor.ehlo()
        servidor.login(usuario_smtp, senha_smtp)
        servidor.send_message(mensagem)


def hash_token_recuperacao(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def segundos_bloqueio_recuperacao(conexao, escopo, chave_hash, agora, limite, janela):
    registro = conexao.execute(
        """
        SELECT COUNT(*) AS total, MIN(tentado_em) AS tentativa_mais_antiga
        FROM tentativas_recuperacao
        WHERE escopo = ? AND chave_hash = ? AND tentado_em > ?
        """,
        (escopo, chave_hash, agora - janela)
    ).fetchone()

    if registro["total"] < limite:
        return 0

    return max(1, janela - (agora - registro["tentativa_mais_antiga"]))


def registrar_tentativa_recuperacao(conexao, escopo, chave_hash, agora):
    conexao.execute(
        """
        INSERT INTO tentativas_recuperacao (escopo, chave_hash, tentado_em)
        VALUES (?, ?, ?)
        """,
        (escopo, chave_hash, agora)
    )


@app.post("/recuperar-senha")
def solicitar_recuperacao_senha():
    email = request.form.get("email", "").strip().lower()
    mensagem_generica = (
        "Se o e-mail estiver cadastrado, enviaremos instruções para redefinir sua senha."
    )

    agora = int(time.time())
    endereco_ip = request.remote_addr or "desconhecido"
    chave_email = hash_identificador_login("recuperacao_email", email[:254])
    chave_ip = hash_identificador_login("recuperacao_ip", endereco_ip)

    conexao = conectar_banco()

    try:
        conexao.execute(
            "DELETE FROM tentativas_recuperacao WHERE tentado_em < ?",
            (agora - 24 * 60 * 60,)
        )
        espera_email = segundos_bloqueio_recuperacao(
            conexao, "email", chave_email, agora,
            LIMITE_RECUPERACAO_EMAIL, JANELA_RECUPERACAO_SEGUNDOS
        )
        espera_ip = segundos_bloqueio_recuperacao(
            conexao, "ip", chave_ip, agora,
            LIMITE_RECUPERACAO_IP, JANELA_RECUPERACAO_SEGUNDOS
        )

        if espera_email or espera_ip:
            conexao.rollback()
            return mensagem_generica, 200

        registrar_tentativa_recuperacao(conexao, "email", chave_email, agora)
        registrar_tentativa_recuperacao(conexao, "ip", chave_ip, agora)
        conexao.commit()

        if not email or len(email) > 254 or "@" not in email:
            return mensagem_generica, 200

        usuario = conexao.execute(
            "SELECT id, email FROM usuarios WHERE email = ?",
            (email,)
        ).fetchone()

        if usuario is None:
            return mensagem_generica, 200

        token = secrets.token_urlsafe(32)
        token_hash = hash_token_recuperacao(token)
        agora = int(time.time())

        conexao.execute(
            """
            UPDATE tokens_recuperacao_senha
            SET usado_em = ?
            WHERE usuario_id = ? AND usado_em IS NULL
            """,
            (agora, usuario["id"])
        )
        conexao.execute(
            """
            INSERT INTO tokens_recuperacao_senha
                (usuario_id, token_hash, expira_em)
            VALUES (?, ?, ?)
            """,
            (usuario["id"], token_hash, agora + 30 * 60)
        )
        conexao.commit()
    finally:
        conexao.close()

    base_publica = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    link_redefinicao = (
        f"{base_publica}/redefinir-senha?token={quote(token, safe='')}"
    )

    try:
        enviar_email_recuperacao(usuario["email"], link_redefinicao)
    except Exception:
        app.logger.exception("Falha ao enviar e-mail de recuperação de senha.")
        conexao = conectar_banco()
        try:
            conexao.execute(
                """
                UPDATE tokens_recuperacao_senha
                SET usado_em = ?
                WHERE token_hash = ? AND usado_em IS NULL
                """,
                (int(time.time()), token_hash)
            )
            conexao.commit()
        finally:
            conexao.close()

    return mensagem_generica, 200


@app.get("/redefinir-senha")
def validar_link_redefinicao_senha():
    token = request.args.get("token", "")

    if not 20 <= len(token) <= 128:
        return "Este link de redefinição é inválido ou expirou.", 400

    conexao = conectar_banco()

    try:
        registro = conexao.execute(
            """
            SELECT id FROM tokens_recuperacao_senha
            WHERE token_hash = ? AND usado_em IS NULL AND expira_em > ?
            """,
            (hash_token_recuperacao(token), int(time.time()))
        ).fetchone()
    finally:
        conexao.close()

    if registro is None:
        return "Este link de redefinição é inválido ou expirou.", 400

    resposta = redirect(
        f"/Pages/recuperarSenha.html?token={quote(token, safe='')}"
    )
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    return resposta


@app.post("/redefinir-senha")
def redefinir_senha():
    token = request.form.get("token", "")
    senha = request.form.get("senha", "")
    confirmacao = request.form.get("confirmarSenha", "")

    if not 20 <= len(token) <= 128:
        return "Este link de redefinição é inválido ou expirou.", 400

    if not 8 <= len(senha) <= 128:
        return "A senha precisa ter entre 8 e 128 caracteres.", 400

    if senha != confirmacao:
        return "As senhas precisam ser iguais.", 400

    token_hash = hash_token_recuperacao(token)
    agora = int(time.time())
    chave_ip = hash_identificador_login(
        "redefinicao_ip", request.remote_addr or "desconhecido"
    )
    senha_hash = generate_password_hash(senha)
    conexao = conectar_banco()

    try:
        conexao.execute("BEGIN IMMEDIATE")
        conexao.execute(
            "DELETE FROM tentativas_recuperacao WHERE tentado_em < ?",
            (agora - 24 * 60 * 60,)
        )
        espera_ip = segundos_bloqueio_recuperacao(
            conexao, "ip", chave_ip, agora,
            LIMITE_REDEFINICAO_IP, JANELA_RECUPERACAO_SEGUNDOS
        )

        if espera_ip:
            conexao.rollback()
            resposta = app.make_response(
                ("Muitas tentativas. Aguarde antes de tentar novamente.", 429)
            )
            resposta.headers["Retry-After"] = str(espera_ip)
            return resposta

        registrar_tentativa_recuperacao(conexao, "ip", chave_ip, agora)
        registro = conexao.execute(
            """
            SELECT usuario_id FROM tokens_recuperacao_senha
            WHERE token_hash = ? AND usado_em IS NULL AND expira_em > ?
            """,
            (token_hash, agora)
        ).fetchone()

        if registro is None:
            # A tentativa inválida também precisa ficar registrada para limitar
            # tentativas de adivinhação do token.
            conexao.commit()
            return "Este link de redefinição é inválido ou expirou.", 400

        conexao.execute(
            "UPDATE usuarios SET senha_hash = ?, versao_sessao = versao_sessao + 1 WHERE id = ?",
            (senha_hash, registro["usuario_id"])
        )
        conexao.execute(
            """
            UPDATE tokens_recuperacao_senha
            SET usado_em = ?
            WHERE usuario_id = ? AND usado_em IS NULL
            """,
            (agora, registro["usuario_id"])
        )
        conexao.commit()
    except sqlite3.Error:
        conexao.rollback()
        raise
    finally:
        conexao.close()

    session.clear()
    return redirect("/Pages/login.html")


@app.before_request
def validar_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    token_enviado = request.form.get("csrf_token", "")
    token_esperado = session.get("csrf_token", "")

    if not token_enviado or not token_esperado:
        abort(400)

    if not secrets.compare_digest(token_enviado, token_esperado):
        abort(400)


@app.get("/")
def inicio():
    return redirect("/Pages/index.html")


@app.get("/<pasta>/<path:arquivo>")
def arquivos_publicos(pasta, arquivo):
    if pasta not in {"Pages", "Style", "Script", "Assets"}:
        abort(404)

    resposta = send_from_directory(raiz / pasta, arquivo)

    if pasta == "Pages" and arquivo == "recuperarSenha.html":
        resposta.headers["Cache-Control"] = "no-store"
        resposta.headers["Referrer-Policy"] = "no-referrer"

    return resposta


@app.get("/Pages/login.html")
def pagina_login():
    resposta = app.make_response(render_template("login.html"))
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.post("/register/cliente")
def cadastrar_cliente():
    nome = request.form.get("nome", "").strip()
    email = request.form.get("email", "").strip().lower()
    telefone = request.form.get("telefone", "").strip()
    senha = request.form.get("senha", "")
    confirmacao = request.form.get("confirmarSenha", "")
    aceita_termos = request.form.get("aceitaTermos", "")

    if not 3 <= len(nome) <= 120 or not telefone or len(telefone) > 20:
        return "Informe nome e telefone válidos (limites: 120 e 20 caracteres).", 400

    if "@" not in email or len(email) > 254:
        return "Informe um e-mail válido.", 400

    if not 8 <= len(senha) <= 128:
        return "A senha precisa ter entre 8 e 128 caracteres.", 400

    if senha != confirmacao:
        return "As senhas precisam ser iguais.", 400

    if aceita_termos != "on":
        return "Você precisa aceitar os termos.", 400

    senha_hash = generate_password_hash(senha)
    conexao = conectar_banco()

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

    flash("Conta cadastrada com sucesso. Entre com seu e-mail e senha.", "sucesso")
    return redirect("/Pages/login.html")

@app.post("/register/empresa")
def cadastrar_empresa():
    nome_empresa = request.form.get("nomeEmpresa", "").strip()
    cnpj = request.form.get("cnpj", "").strip() or None
    telefone = request.form.get("telefone", "").strip()
    nome_responsavel = request.form.get("nomeResponsavel", "").strip()
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "")
    confirmacao = request.form.get("confirmarSenha", "")
    aceita_termos = request.form.get("aceitaTermos", "")

    if not 2 <= len(nome_empresa) <= 150:
        return "O nome da empresa deve ter entre 2 e 150 caracteres.", 400

    if not 3 <= len(nome_responsavel) <= 120:
        return "Informe o nome completo do responsável.", 400

    if not telefone or len(telefone) > 20:
        return "Informe um telefone válido.", 400

    if not email or "@" not in email or len(email) > 254:
        return "Informe um e-mail válido.", 400

    if cnpj and len(cnpj) > 18:
        return "O CNPJ deve ter até 18 caracteres.", 400

    if not 8 <= len(senha) <= 128:
        return "A senha precisa ter entre 8 e 128 caracteres.", 400

    if senha != confirmacao:
        return "As senhas precisam ser iguais.", 400

    if aceita_termos != "on":
        return "Você precisa aceitar os termos.", 400

    senha_hash = generate_password_hash(senha)
    conexao = conectar_banco()

    try:
        cursor = conexao.execute(
            """
            INSERT INTO usuarios (nome, email, telefone, senha_hash, tipo)
            VALUES (?, ?, ?, ?, ?)
            """,
            (nome_responsavel, email, telefone, senha_hash, "empresa")
        )
        usuario_id = cursor.lastrowid

        conexao.execute(
            """
            INSERT INTO empresas (usuario_id, nome, telefone, cnpj)
            VALUES (?, ?, ?, ?)
            """,
            (usuario_id, nome_empresa, telefone, cnpj)
        )
        conexao.commit()
    except sqlite3.IntegrityError:
        conexao.rollback()
        return "Não foi possível cadastrar. O e-mail ou CNPJ pode já estar em uso.", 409
    finally:
        conexao.close()

    flash("Empresa cadastrada com sucesso. Entre com seu e-mail e senha.", "sucesso")
    return redirect("/Pages/login.html")

def destino_local_seguro(valor):
    if not valor or len(valor) > 2048:
        return None

    try:
        destino = urlsplit(valor)
    except ValueError:
        return None

    if destino.scheme and destino.scheme not in {"http", "https"}:
        return None

    if destino.netloc and (
        not destino.scheme
        or destino.netloc.lower() != request.host.lower()
        or destino.username is not None
        or destino.password is not None
    ):
        return None

    caminho = unquote(destino.path)
    if not caminho.startswith("/Pages/") or "\\" in caminho:
        return None

    if any(parte in {".", ".."} for parte in caminho.split("/")):
        return None

    return urlunsplit(("", "", destino.path, destino.query, destino.fragment))


def hash_identificador_login(escopo, valor):
    mensagem = f"{escopo}:{valor}".encode("utf-8")
    chave = app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(chave, mensagem, hashlib.sha256).hexdigest()


def segundos_bloqueio_login(conexao, escopo, chave_hash, agora, limite):
    registro = conexao.execute(
        """
        SELECT COUNT(*) AS total, MIN(tentado_em) AS tentativa_mais_antiga
        FROM tentativas_login
        WHERE escopo = ? AND chave_hash = ? AND tentado_em > ?
        """,
        (escopo, chave_hash, agora - JANELA_LOGIN_SEGUNDOS)
    ).fetchone()

    if registro["total"] < limite:
        return 0

    return max(
        1,
        JANELA_LOGIN_SEGUNDOS - (agora - registro["tentativa_mais_antiga"])
    )


def registrar_tentativa_login(conexao, escopo, chave_hash, agora):
    conexao.execute(
        """
        INSERT INTO tentativas_login (escopo, chave_hash, tentado_em)
        VALUES (?, ?, ?)
        """,
        (escopo, chave_hash, agora)
    )


@app.post("/login")
def entrar():
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("password", "")
    agora = int(time.time())
    chave_email = hash_identificador_login("email", email)
    endereco_ip = request.remote_addr or "desconhecido"
    chave_ip = hash_identificador_login("ip", endereco_ip)

    conexao = conectar_banco()

    try:
        conexao.execute(
            "DELETE FROM tentativas_login WHERE tentado_em < ?",
            (agora - 24 * 60 * 60,)
        )

        espera_email = segundos_bloqueio_login(
            conexao, "email", chave_email, agora, LIMITE_LOGIN_EMAIL
        )
        espera_ip = segundos_bloqueio_login(
            conexao, "ip", chave_ip, agora, LIMITE_LOGIN_IP
        )

        if espera_email or espera_ip:
            resposta = app.make_response(
                ("Não foi possível entrar. Aguarde antes de tentar novamente.", 429)
            )
            resposta.headers["Retry-After"] = str(max(espera_email, espera_ip))
            return resposta

        if len(senha) > 128:
            registrar_tentativa_login(conexao, "email", chave_email, agora)
            registrar_tentativa_login(conexao, "ip", chave_ip, agora)
            conexao.commit()
            return "E-mail ou senha incorretos.", 401

        usuario = conexao.execute(
            "SELECT id, senha_hash, versao_sessao FROM usuarios WHERE email = ?",
            (email,)
        ).fetchone()

        hash_armazenado = usuario["senha_hash"] if usuario else HASH_SENHA_FALSA
        senha_valida = check_password_hash(hash_armazenado, senha)

        if not usuario or not senha_valida:
            registrar_tentativa_login(conexao, "email", chave_email, agora)
            registrar_tentativa_login(conexao, "ip", chave_ip, agora)
            conexao.commit()
            return "E-mail ou senha incorretos.", 401

        conexao.execute(
            "DELETE FROM tentativas_login WHERE escopo = 'email' AND chave_hash = ?",
            (chave_email,)
        )
        conexao.commit()
    finally:
        conexao.close()

    session.clear()
    session["usuario_id"] = usuario["id"]
    session["versao_sessao"] = usuario["versao_sessao"]
    session.permanent = True

    destino = destino_local_seguro(request.form.get("next", ""))
    return redirect(destino or "/Pages/Perfil.html")


@app.get("/Pages/Perfil.html")
def perfil():
    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return redirect("/Pages/login.html")

    conexao = conectar_banco()

    try:
        usuario = conexao.execute(
            "SELECT nome, email, telefone, versao_sessao FROM usuarios WHERE id = ?",
            (usuario_id,)
        ).fetchone()
    finally:
        conexao.close()

    if (
        usuario is None
        or usuario["versao_sessao"] != session.get("versao_sessao")
    ):
        session.clear()
        return redirect("/Pages/login.html")

    resposta = app.make_response(
        render_template("Perfil.html", usuario=usuario)
    )
    resposta.headers["Cache-Control"] = "no-store"

    return resposta


@app.post("/logout")
def sair ():
    session.clear()
    flash("Você saiu da conta.", "sucesso")
    return redirect ("/Pages/login.html")


@app.route("/Pages/editarPerfil.html", methods=["GET", "POST"] )
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

    conexao = conectar_banco()
    erro = None

    try:
        usuario = conexao.execute(
            "SELECT nome, telefone, versao_sessao FROM usuarios WHERE id = ?",
            (usuario_id,)
        ).fetchone()

        if (
            usuario is None
            or usuario["versao_sessao"] != session.get("versao_sessao")
        ):
            session.clear()
            return redirect("/Pages/login.html")

        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            telefone = request.form.get("telefone", "").strip()

            usuario = {"nome": nome, "telefone": telefone}

            if not 3 <= len(nome) <=120:
                erro = "O nome deve  ter entre 3 e 120 caracteres."
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

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
