import secrets
import sqlite3
import os
import hashlib
import hmac
import smtplib
import ssl
import time
import json
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from flask import Flask, abort, flash, redirect, send_from_directory, request, session, render_template, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlsplit
from configuracao import carregar_configuracao
from decimal import Decimal, InvalidOperation
import banco
from frete import calcular_frete, formatar_endereco

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

    token_enviado = (
        request.form.get("csrf_token", "")
        or request.headers.get("X-CSRF-Token", "")
    )
    token_esperado = session.get("csrf_token", "")

    if not token_enviado or not token_esperado:
        abort(400)

    if not secrets.compare_digest(token_enviado, token_esperado):
        abort(400)


@app.get("/")
def inicio():
    return redirect("/Pages/index.html")

@app.get("/Pages/Empresa/painelEmpresa.html")
def painel_empresa():
    usuario = buscar_usuario_sessao()
    if usuario is None:
        return redirect("/Pages/login.html")
    if usuario["tipo"] != "empresa":
        abort(403)

    conexao = conectar_banco()
    try:
        empresa = conexao.execute(
            "SELECT id, nome FROM empresas WHERE usuario_id = ?",
            (usuario["id"],)
        ).fetchone()
        if empresa is None:
            abort(404, description="Empresa não encontrada.")

        metricas = dict(conexao.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE status != 'Entregue') AS servicos_ativos,
                COUNT(*) FILTER (WHERE status = 'Pronto para retirada') AS prontos_retirada
            FROM ordens_servico WHERE empresa_id = ?
            """,
            (empresa["id"],)
        ).fetchone())
        metricas["orcamentos_pendentes"] = conexao.execute(
            """SELECT COUNT(*) FROM solicitacoes
               WHERE empresa_id = ? AND orcamento_status = 'Aguardando aprovação'""",
            (empresa["id"],),
        ).fetchone()[0]
        ordens_recentes = conexao.execute(
            """SELECT id, aparelho, status, previsao FROM ordens_servico
               WHERE empresa_id = ? ORDER BY id DESC LIMIT 5""",
            (empresa["id"],),
        ).fetchall()

    finally:
        conexao.close()

    return render_template(
        "Empresa/painelEmpresa.html",
        empresa=empresa,
        metricas=metricas,
        ordens_recentes=ordens_recentes,
    )


@app.post("/api/orcamento/analisar")
def analisar_orcamento():
    dados = request.get_json(silent=True) or {}
    descricao = dados.get("descricao_problema", "").strip()
    if len(descricao) < 10:
        return jsonify({"erro": "Descreva melhor o problema."}), 400

    categoria = dados.get("categoria_problema")
    servicos = {
        "tela": "Avaliação de tela e touch", "bateria": "Avaliação de bateria",
        "carga": "Avaliação do conector de carga", "camera": "Avaliação de câmera",
        "audio": "Avaliação de áudio ou microfone", "placa": "Avaliação de placa",
    }
    # Faixas públicas de referência para reparos comuns no Brasil (2026).
    # São apenas uma perspectiva: o modelo, a peça e a análise técnica alteram o valor.
    referencias = {
        "tela": (28000, 60000, 1, 3),
        "bateria": (19000, 45000, 1, 2),
        "carga": (12000, 26000, 1, 3),
        "camera": (18000, 60000, 1, 3),
        "placa": (40000, 60000, 3, 7),
    }
    faixa = None
    prazo = None
    if categoria in referencias:
        minimo, maximo, dias_min, dias_max = referencias[categoria]
        faixa = {
            "minimo_centavos": minimo,
            "maximo_centavos": maximo,
            "medio_centavos": round((minimo + maximo) / 2),
            "fonte": "Faixa indicativa compilada de referências públicas de assistências brasileiras em 2026; os preços variam por modelo e peça.",
        }
        prazo = {
            "minimo_dias_uteis": dias_min,
            "maximo_dias_uteis": dias_max,
            "medio_dias_uteis": round((dias_min + dias_max) / 2, 1),
            "aviso": "Tempo médio de referência observado em assistências brasileiras; é apenas uma perspectiva. A empresa confirma o prazo após análise técnica e consulta de peças.",
        }
    return jsonify({
        "servico": servicos.get(categoria, "Avaliação técnica do aparelho"),
        "explicacao": "A análise é preliminar; o técnico confirmará após avaliar o aparelho.",
        "orientacao": "Envie uma solicitação para receber o orçamento definitivo.",
        "faixa_preco": faixa, "prazo_estimado": prazo, "perguntas": [],
    })

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

def buscar_usuario_sessao():
    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return None

    conexao = conectar_banco()

    try:
        usuario = conexao.execute(
            """
            SELECT id, nome, email, telefone, cep, logradouro,
                   numero_endereco, complemento, bairro, cidade, uf,
                   versao_sessao, tipo
            FROM usuarios
            WHERE id = ?
            """,
            (usuario_id,)
        ).fetchone()
    finally:
        conexao.close()
    
    if (
        usuario is None or usuario["versao_sessao"] != session.get("versao_sessao")
    ):
        session.clear()
        return None

    return usuario

def pagina_inicial_usuario(tipo):
    if tipo == "empresa":
        return "/Pages/Empresa/painelEmpresa.html"
    
    return "/Pages/Perfil.html"

def destino_permitido_para_usuario(destino, tipo):
    if not destino:
        return None

    caminho = urlsplit(destino).path

    if caminho.startswith ("/Pages/Empresa/") and tipo != "empresa":
        return None
    
    paginas_cliente = {
        "/Pages/Perfil.html",
        "/Pages/editarPerfil.html",
        "/Pages/MeusPedidos.html",
    }

    if caminho in paginas_cliente and tipo != "cliente":
        return None 
    
    return destino

@app.before_request
def proteger_area_empresarial():
    if not request.path.startswith("/Pages/Empresa/"):
        return

    usuario = buscar_usuario_sessao()

    if usuario is None:
        destino = quote(request.full_path.rstrip("?"), safe="/?=&")
        return redirect (f"/Pages/login.html?next={destino}")

    if usuario["tipo"] != "empresa":
        abort(403)

@app.route("/Pages/Empresa/dadosEmpresa.html", methods=["GET", "POST"])
def dados_empresa():
    usuario = buscar_usuario_sessao()
    erro = None
    status = 200
    conexao = conectar_banco()

    try:
        empresa = conexao.execute(
            "SELECT nome, telefone, cnpj FROM empresas WHERE usuario_id = ?",
            (usuario["id"],)
        ).fetchone()

        if empresa is None:
            abort(404, description="Não há uma empresa vinculada a esta conta.")

        if request.method == "POST":
            empresa = {
                "nome": request.form.get("nomeEmpresa", "").strip(),
                "telefone": request.form.get("telefone", "").strip(),
                "cnpj": request.form.get("cnpj", "").strip() or None,
            }
            usuario = dict(usuario)
            usuario["nome"] = request.form.get("nomeResponsavel", "").strip()

            if not 2 <= len(empresa["nome"]) <= 150:
                erro = "O nome da empresa deve ter entre 2 e 150 caracteres."
            elif not 3 <= len(usuario["nome"]) <= 120:
                erro = "O nome do responsável deve ter entre 3 e 120 caracteres."
            elif not empresa["telefone"] or len(empresa["telefone"]) > 20:
                erro = "Informe um telefone com até 20 caracteres."
            elif empresa["cnpj"] and len(empresa["cnpj"]) > 18:
                erro = "O CNPJ deve ter até 18 caracteres."

            if erro:
                status = 400
            else:
                try:
                    conexao.execute(
                        "UPDATE empresas SET nome = ?, telefone = ?, cnpj = ? WHERE usuario_id = ?",
                        (empresa["nome"], empresa["telefone"], empresa["cnpj"], usuario["id"])
                    )
                    conexao.execute(
                        "UPDATE usuarios SET nome = ?, telefone = ? WHERE id = ?",
                        (usuario["nome"], empresa["telefone"], usuario["id"])
                    )
                    conexao.commit()
                except sqlite3.IntegrityError:
                    conexao.rollback()
                    erro = "Não foi possível salvar. O CNPJ pode já estar em uso."
                    status = 409
                else:
                    flash("Dados da empresa atualizados com sucesso.", "sucesso")
                    return redirect("/Pages/Empresa/dadosEmpresa.html")
    finally:
        conexao.close()

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return render_template(
        "Empresa/dadosEmpresa.html", empresa=empresa, usuario=usuario,
        erro=erro, csrf_token=session["csrf_token"]
    ), status


@app.after_request
def impedir_cache_area_protegida(resposta):
    if request.path.startswith("/Pages/Empresa/"):
        resposta.headers["Cache-Control"] = "no-store"

    return resposta



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
            """
            SELECT id, senha_hash, versao_sessao, tipo
            FROM usuarios
            WHERE email = ?
            """,
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
    destino = destino_permitido_para_usuario(destino, usuario["tipo"])

    return redirect(
        destino or pagina_inicial_usuario(usuario["tipo"])
    )


@app.route("/Pages/Perfil.html", methods=["GET", "POST"])
def perfil():
    usuario = buscar_usuario_sessao()

    if usuario is None:
        return redirect("/Pages/login.html")

    if usuario["tipo"] != "cliente":
        return redirect(pagina_inicial_usuario(usuario["tipo"]))

    if request.method == "POST":
        dados = {campo: request.form.get(campo, "").strip() for campo in ("cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf")}
        dados["cep"] = "".join(char for char in dados["cep"] if char.isdigit())
        dados["uf"] = dados["uf"].upper()
        if len(dados["cep"]) != 8 or not all(dados[campo] for campo in ("logradouro", "numero", "bairro", "cidade")) or len(dados["uf"]) != 2:
            flash("Preencha um endereço válido e completo.", "erro")
            return redirect("/Pages/Perfil.html")
        conexao = conectar_banco()
        try:
            conexao.execute(
                """UPDATE usuarios SET cep=?, logradouro=?, numero_endereco=?,
                   complemento=?, bairro=?, cidade=?, uf=? WHERE id=?""",
                (dados["cep"], dados["logradouro"], dados["numero"], dados["complemento"], dados["bairro"], dados["cidade"], dados["uf"], usuario["id"]),
            )
            conexao.commit()
        finally:
            conexao.close()
        flash("Endereço atualizado com sucesso.", "sucesso")
        return redirect("/Pages/Perfil.html")

    resposta = app.make_response(
        render_template("Perfil.html", usuario=usuario)
    )
    resposta.headers["Cache-Control"] = "no-store"

    return resposta


@app.route("/api/endereco", methods=["GET", "POST"])
def endereco_usuario():
    usuario = buscar_usuario_sessao()
    if usuario is None:
        return jsonify({"erro": "Faça login para acessar seu endereço."}), 401
    if usuario["tipo"] != "cliente":
        abort(403)

    campos = ("cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf")
    if request.method == "GET":
        return jsonify({campo: usuario["numero_endereco"] if campo == "numero" else usuario[campo] for campo in campos})
    dados = {campo: request.form.get(campo, "").strip() for campo in campos}
    dados["cep"] = "".join(char for char in dados["cep"] if char.isdigit())
    dados["uf"] = dados["uf"].upper()
    obrigatorios = ("logradouro", "numero", "bairro", "cidade")
    if len(dados["cep"]) != 8 or not all(dados[campo] for campo in obrigatorios) or len(dados["uf"]) != 2:
        return jsonify({"erro": "Preencha um endereço válido e completo."}), 400
    conexao = conectar_banco()
    try:
        conexao.execute(
            """UPDATE usuarios SET cep=?, logradouro=?, numero_endereco=?,
               complemento=?, bairro=?, cidade=?, uf=? WHERE id=?""",
            (dados["cep"], dados["logradouro"], dados["numero"], dados["complemento"], dados["bairro"], dados["cidade"], dados["uf"], usuario["id"]),
        )
        conexao.commit()
    finally:
        conexao.close()
    return jsonify({"mensagem": "Endereço salvo na conta.", **dados})


@app.get("/api/frete")
def consultar_frete():
    valor, regiao = calcular_frete(request.args.get("cep", ""))
    if valor is None:
        return jsonify({"erro": "Informe um CEP válido com 8 números."}), 400

    resposta = jsonify({"frete_centavos": valor, "regiao": regiao})
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.post("/logout")
def sair ():
    session.clear()
    flash("Você saiu da conta.", "sucesso")
    return redirect ("/Pages/login.html")


@app.route("/Pages/editarPerfil.html", methods=["GET", "POST"] )
def editar_perfil():
    usuario = buscar_usuario_sessao()
    
    if usuario is None:
        return redirect ("/Pages/login.html")

    if usuario["tipo"] != "cliente":
        return redirect(pagina_inicial_usuario(usuario["tipo"]))

    usuario_id = usuario["id"]    

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


STATUS_ORDENS = (
    "Recebido",
    "Em diagnóstico",
    "Em reparo",
    "Pronto para retirada",
    "Entregue",
)

@app.route(
    "/Pages/Empresa/ordensServico.html",
    methods=["GET", "POST"]
)

def ordens_servico():
    usuario = buscar_usuario_sessao()

    if request.method == "POST":
        abort(405, description="Ordens de serviço são criadas após a aprovação de um orçamento pelo cliente.")

    #verifica o login e tipo da conta
    conexao = conectar_banco()
    erro = None
    codigo_resposta = 200

    try:
        empresa = conexao.execute(
            "SELECT id, nome FROM empresas WHERE usuario_id = ?",
            (usuario["id"],)
        ).fetchone()

        if empresa is None:
            abort(
                404,
                description="Não há empresa vinculada a esta conta."
            )

        if request.method == "POST":
            email = request.form.get(
                "cliente_email", ""
            ).strip().lower()

            aparelho = request.form.get("aparelho", "").strip()
            problema = request.form.get("problema", "").strip()
            previsao = request.form.get("previsao", "").strip()

            cliente = None

            if not email or len(email) > 254 or "@" not in email:
                erro = "Informe um e-mail válido."

            elif not 2 <= len(aparelho) <= 120:
                erro = "O aparelho debe ter entre 2 e 120 caracteres."

            elif not 5 <= len(problema) <=  1000:
                erro = "Descreva o problema com 5 a 1000 caracteres."


            if erro is None and previsao:
                try:
                    previsao = date.fromisoformat(previsao).isoformat()
                except ValueError:
                    erro = "Informe uma previsão de data válida."

            if erro is None:
                cliente = conexao.execute(
                    """
                    SELECT id 
                    FROM usuarios
                    WHERE email = ? AND tipo = 'cliente'
                    """,
                    (email,)
                ).fetchone()

                if cliente is None:
                    erro = ("Não encontramos uma conta de cliente com esse"
                            "e-mail. Peça ao cliente para se cadastrar.")

            if erro:
                codigo_resposta = 400
            else:
                conexao.execute(
                    """
                    INSERT INTO ordens_servico (
                        empresa_id, cliente_id, aparelho, problema, previsao
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        empresa["id"], cliente["id"], aparelho,
                        problema, previsao or None
                    )
                )
                conexao.commit()

                flash("Ordem cadastrada com sucesso.", "sucesso")
                return redirect("/Pages/Empresa/ordensServico.html")

        ordens = conexao.execute(
            """
            SELECT o.id, o.aparelho, o.problema, o.status, o.previsao,
                   u.nome AS cliente_nome
            FROM ordens_servico AS o
            JOIN usuarios AS u ON u.id = o.cliente_id
            WHERE o.empresa_id = ?
            ORDER BY o.id DESC
            """,
            (empresa["id"],)
        ).fetchall()
    finally:
        conexao.close()

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return render_template(
        "Empresa/ordensServico.html",
        empresa=empresa,
        ordens=ordens,
        erro=erro,
        csrf_token=session["csrf_token"],
        status_disponiveis=STATUS_ORDENS
    ), codigo_resposta


@app.get("/Pages/Empresa/aparelhosCadastrados.html")
def aparelhos_cadastrados():
    usuario = buscar_usuario_sessao()  # before_request já exige empresa
    conexao = conectar_banco()
    try:
        empresa = conexao.execute(
            "SELECT id, nome FROM empresas WHERE usuario_id = ?",
            (usuario["id"],),
        ).fetchone()

        if empresa is None:
            abort(404, description="Não há empresa vinculada a esta conta.")

        aparelhos = conexao.execute(
            """
            SELECT o.id, o.aparelho, o.problema, o.status, o.previsao,
                   u.nome AS cliente_nome
            FROM ordens_servico AS o
            JOIN usuarios AS u ON u.id = o.cliente_id
            WHERE o.empresa_id = ?
            ORDER BY o.id DESC
            """,
            (empresa["id"],),
        ).fetchall()
    finally:
        conexao.close()

    resposta = app.make_response(render_template(
        "Empresa/aparelhosCadastrados.html",
        empresa=empresa,
        aparelhos=aparelhos,
    ))
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.post("/Pages/Empresa/ordens/<int:ordem_id>/status")
def atualizar_status_ordem(ordem_id):
    usuario = buscar_usuario_sessao()

    novo_status = request.form.get("status", "").strip()
    observacao = request.form.get("observacao", "").strip()

    if novo_status not in STATUS_ORDENS:
        flash("Selecione um status válido.", "erro")
        return redirect("/Pages/Empresa/ordensServico.html")


    if len(observacao) > 1000:
        flash("A observação debe ter até 1000 caracteres.", "erro")
        return redirect("/Pages/Empresa/ordensServico.html")


    conexao = conectar_banco()

    try:
        conexao.execute("BEGIN IMMEDIATE")

        ordem = conexao.execute(
            """
            SELECT o.id, o.status
            FROM ordens_servico AS o
            JOIN empresas AS e ON e.id = o.empresa_id
            WHERE o.id = ? AND e.usuario_id = ?
            """,
            (ordem_id, usuario["id"])
        ).fetchone()
    

        if ordem is None:
            abort(404)

        if novo_status == ordem["status"]:
            flash("A ordem já está nesse status.", "erro")
            return redirect("/Pages/Empresa/ordensServico.html")

        conexao.execute(
            """
            UPDATE ordens_servico
            SET status  = ?
            WHERE id = ?
            """,
            (novo_status, ordem_id)
        )

        conexao.execute(
            """
            INSERT INTO historico_ordens (
                ordem_id, status, observacao, criado_em
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (ordem_id, novo_status, observacao)
        )

        conexao.commit()
    finally:
        conexao.close()

    flash ("Status atualizado com sucesso.", "sucesso")
    return redirect("/Pages/Empresa/ordensServico.html")


@app.get("/Pages/Acompanhar.html")
def acompanhar_ordens():
    usuario = buscar_usuario_sessao()

    if usuario is None:
        return redirect("/Pages/login.html?next=/Pages/Acompanhar.html")

    if usuario ["tipo"] != "cliente":
        return redirect(pagina_inicial_usuario(usuario["tipo"]))

    conexao = conectar_banco()

    try:
        ordens = conexao.execute(
            """
            SELECT 
                o.id,
                o.aparelho,
                o.problema,
                o.status,
                o.previsao,
                o.orcamento_id,
                orc.servico AS servico_orcamento,
                orc.valor_centavos AS valor_orcamento_centavos,
                orc.modalidade_saida_pronto,
                orc.pagamento_modalidade,
                e.nome AS empresa_nome
            FROM ordens_servico AS o
            LEFT JOIN orcamentos AS orc ON orc.id = o.orcamento_id
            JOIN empresas AS e ON e.id = o.empresa_id
            WHERE o.cliente_id = ?
            ORDER BY o.id DESC
            """,
            (usuario["id"],)
        ).fetchall()

        registros = conexao.execute(
            """
            SELECT 
                h.id,
                h.ordem_id,
                h.status,
                h.observacao
            FROM historico_ordens AS h
            JOIN ordens_servico AS o ON o.id = h.ordem_id
            WHERE o.cliente_id = ?
            ORDER BY h.id DESC
            """,
            (usuario["id"],)
        ).fetchall()

        solicitacoes_pendentes = conexao.execute(
            """
            SELECT s.id, s.aparelho, s.problema, s.servico_sugerido,
                   s.modalidade_entrada, s.criado_em, e.nome AS empresa_nome
            FROM solicitacoes AS s
            JOIN empresas AS e ON e.id = s.empresa_id
            WHERE s.cliente_id = ?
              AND s.status IN ('Nova solicitação', 'Em análise')
              AND NOT EXISTS (
                  SELECT 1 FROM orcamentos AS o WHERE o.solicitacao_id = s.id
              )
            ORDER BY s.id DESC
            """,
            (usuario["id"],),
        ).fetchall()

        orcamentos_pendentes = conexao.execute(
            """SELECT o.id, o.diagnostico, o.servico, o.valor_centavos,
                      o.prazo_minimo_dias, o.prazo_maximo_dias,
                      o.taxa_devolucao_centavos, s.aparelho, s.problema,
                      s.modalidade_entrada, s.endereco_coleta, e.nome AS empresa_nome,
                      u.cep, u.logradouro, u.numero_endereco, u.bairro, u.cidade, u.uf
               FROM orcamentos o
               JOIN solicitacoes s ON s.id = o.solicitacao_id
               JOIN empresas e ON e.id = s.empresa_id
               JOIN usuarios u ON u.id = s.cliente_id
               WHERE s.cliente_id = ? AND o.status = 'Aguardando aprovação'
               ORDER BY o.id DESC""",
            (usuario["id"],),
        ).fetchall()

    finally:
        conexao.close()

    historicos = {}

    for registro in registros:
        historicos.setdefault(
            registro["ordem_id"], []
        ).append(registro)

    resposta = app.make_response(
        render_template(
            "Acompanhar.html",
            ordens=ordens, 
            historicos=historicos,
            solicitacoes_pendentes=solicitacoes_pendentes,
            orcamentos_pendentes=orcamentos_pendentes,
            csrf_token=session.setdefault("csrf_token", secrets.token_urlsafe(32)),
        )
    )

    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.post("/Pages/Acompanhar/ordem/<int:ordem_id>/preferencias-entrega")
def salvar_preferencias_entrega_ordem(ordem_id):
    usuario = buscar_usuario_sessao()
    if usuario is None:
        return redirect("/Pages/login.html?next=/Pages/Acompanhar.html")
    if usuario["tipo"] != "cliente":
        abort(403)

    modalidade = request.form.get("modalidade_saida", "")
    pagamento = request.form.get("pagamento_modalidade", "")
    if modalidade not in {"retirada", "devolucao"} or pagamento not in {"site", "presencial"}:
        flash("Escolha como receber o aparelho e como pretende pagar.", "erro")
        return redirect("/Pages/Acompanhar.html")

    conexao = conectar_banco()
    try:
        cursor = conexao.execute(
            """UPDATE orcamentos SET modalidade_saida_pronto = ?, pagamento_modalidade = ?
               WHERE id = (
                   SELECT os.orcamento_id FROM ordens_servico os
                   JOIN solicitacoes s ON s.id = (SELECT solicitacao_id FROM orcamentos WHERE id = os.orcamento_id)
                   WHERE os.id = ? AND s.cliente_id = ? AND os.status = 'Pronto para retirada'
               )""",
            (modalidade, pagamento, ordem_id, usuario["id"]),
        )
        if cursor.rowcount != 1:
            abort(409, description="A escolha só pode ser registrada quando o serviço estiver pronto.")
        conexao.commit()
    finally:
        conexao.close()
    flash("Preferências de entrega e pagamento registradas.", "sucesso")
    return redirect("/Pages/Acompanhar.html")


def imagens_disponiveis_produto():
    pasta = raiz / "Assets" / "img"
    extensoes = {".png", ".jpg", ".jpeg", ".webp"}

    return sorted (
        arquivo.name
        for arquivo in pasta.iterdir()
        if arquivo.is_file()
        and arquivo.suffix.lower() in extensoes
    )

@app.route(
    "/Pages/Empresa/produtos.html",
    methods=["GET", "POST"]
)

def produtos_empresa():
    usuario = buscar_usuario_sessao()
    imagens = imagens_disponiveis_produto()

    erro = None
    codigo_resposta = 200
    produto_edicao = None
    campos = {}
    conexao = conectar_banco()

    try:
        empresa = conexao.execute(
            "SELECT id, nome FROM empresas WHERE usuario_id = ?",
            (usuario["id"],)
        ).fetchone()

        if empresa is None:
            abort(404, description="Empresa não encontrada.")

        if "editar" in request.args:
            produto_id = request.args.get("editar", type=int)

            if produto_id is None:
                abort(404)

            produto_edicao = conexao.execute(
                """
                SELECT *
                FROM produtos
                WHERE id = ? AND empresa_id = ?
                """,
                (produto_id, empresa["id"])
            ).fetchone()

            if produto_edicao is None:
                abort(404)

        if produto_edicao is not None:
            campos = {
                "nome": produto_edicao["nome"],
                "descricao": produto_edicao["descricao"],
                "categoria": produto_edicao["categoria"],
                "preco": format(
                    Decimal(produto_edicao["preco_centavos"]) / 100,
                    ".2f"
                ),
                "estoque": produto_edicao["estoque"],
                "imagem": (
                    produto_edicao["imagem"].rsplit("/", 1)[-1]
                    if produto_edicao["imagem"]
                    else ""
                )
            }

        if request.method == "POST":
            campos = request.form

            nome = request.form.get("nome", "").strip()
            descricao = request.form.get("descricao", "").strip()
            categoria = request.form.get("categoria", "").strip()
            imagem = request.form.get("imagem", "").strip()

            preco_texto = request.form.get("preco", "").strip()
            estoque_texto = request.form.get("estoque", "").strip()

            preco_centavos = None
            estoque= None

            if not 2 <= len (nome) <= 120:
                erro = "O nome deve ter entre 2 e 120 caracteres."

            elif len (descricao) > 1000:
                erro = "A descrição deve ter até 1000 caracteres."

            elif not 2 <= len (categoria) <= 60:
                erro = "A categoria deve ter entre 2 e 60 caracteres."

            elif imagem and imagem not in imagens:
                erro = "Selecione uma imagem disponível."

            if erro is None:
                try:
                    preco = Decimal(preco_texto.replace(",", "."))

                    if(
                        not preco.is_finite()
                        or not Decimal("0.01") <= preco <= Decimal ("999999.99")
                    ):
                        raise ValueError

                    centavos = preco * 100 

                    if centavos != centavos.to_integral_value():
                        raise ValueError

                    preco_centavos = int (centavos)
                except (InvalidOperation, ValueError):
                    erro = (
                        "Informe um preço de 0,01 a  999999,99,"
                        "com até duas casas decimais."
                    )

            if erro is None:
                try:
                    estoque = int(estoque_texto)
                    if not 0 <= estoque <= 999999:
                        raise ValueError
                except ValueError:
                    erro = "Informe um estoque inteiro de 0 a 999999."

            if erro:
                codigo_resposta = 400

            else:
                caminho_imagem = (
                    f"/Assets/img/{imagem}" if imagem else None
                )

                if produto_edicao is not None:
                    conexao.execute(
                        """
                        UPDATE produtos
                        SET nome = ?,
                             descricao = ?,
                             categoria = ?,
                             preco_centavos = ?,
                             estoque = ?,
                             imagem = ?
                        WHERE id = ? AND empresa_id = ?
                        """,
                        (
                            nome,
                            descricao,
                            categoria,
                            preco_centavos,
                            estoque,
                            caminho_imagem,
                            produto_edicao["id"],
                            empresa["id"]
                        )
                    )
                    mensagem = "Produto atualizado com sucesso."
                else:
                    conexao.execute(
                        """
                        INSERT INTO produtos (
                        empresa_id, nome, descricao, categoria,
                        preco_centavos, estoque, imagem)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            empresa["id"],
                            nome,
                            descricao,
                            categoria,
                            preco_centavos,
                            estoque,
                            caminho_imagem
                        )
                    )
                    mensagem = "Produto cadastrado com sucesso."

                conexao.commit()
                flash(mensagem, "sucesso")
                return redirect("/Pages/Empresa/produtos.html")

        produtos = conexao.execute(
            """
            SELECT id, nome, descricao, categoria, preco_centavos,
                   estoque, imagem, ativo
            FROM produtos
            WHERE empresa_id = ?
            ORDER BY id DESC
            """,
            (empresa["id"],)
        ).fetchall()

    finally:
        conexao.close()

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return render_template(
        "Empresa/produtos.html",
        empresa=empresa,
        produtos=produtos,
        imagens=imagens,
        erro=erro,
        csrf_token=session["csrf_token"],
        produto_edicao=produto_edicao,
        campos=campos
    ), codigo_resposta

    
@app.post("/Pages/Empresa/produtos/<int:produto_id>/situacao")
def alterar_situacao_produto(produto_id):
    usuario = buscar_usuario_sessao()
    ativo = request.form.get("ativo", "")

    if ativo not in {"0", "1"}:
        abort(400)

    conexao = conectar_banco()

    try:
        produto = conexao.execute(
            """
            SELECT p.id
            FROM produtos AS p
            JOIN empresas AS e ON e.id = p.empresa_id
            WHERE p.id = ? AND e.usuario_id = ?
            """,
            (produto_id, usuario["id"])
        ).fetchone()



        if produto is None:
            abort(404)

        conexao.execute(
            "UPDATE produtos SET ativo = ? WHERE id = ?",
            (int(ativo), produto_id)
        )
        conexao.commit()
    finally:
        conexao.close()

    mensagem = (
        "Produto reativado."
        if ativo == "1"
        else "Produto desativado."
    )

    flash(mensagem, "sucesso")
    return redirect("/Pages/Empresa/produtos.html")


def buscar_produtos_publicos():
    conexao = conectar_banco()

    try:
        return conexao.execute(
            """
            SELECT
                p.id,
                p.empresa_id,
                p.nome,
                p.descricao,
                p.categoria,
                p.preco_centavos,
                p.estoque,
                p.imagem,
                e.nome AS empresa_nome
            FROM produtos AS p
            JOIN empresas AS e ON e.id = p.empresa_id
            WHERE p.ativo = 1
            ORDER BY p.id DESC
            """
        ).fetchall()
    finally:
        conexao.close()


@app.get("/Pages/vitrine.html")
def vitrine():
    resposta = app.make_response(
        render_template(
            "vitrine.html",
            produtos=buscar_produtos_publicos()
        )
    )
    resposta.headers["Cache-Control"] = 'no-store'
    return resposta

@app.get("/Script/catalogoProdutos.js")
def catalogo_produtos_banco():
    produtos = buscar_produtos_publicos()

    catalogo = {
        f"produto-{produto['id']}":{
            "empresa_id": produto["empresa_id"],
            "nome":produto["nome"],
            "preco":produto["preco_centavos"],
            "estoque":produto["estoque"],
            "cor":"Não informada",
            "imagem":produto["imagem"]
        }
        for produto in produtos
    }

    dados_json = jsonify(catalogo).get_data(as_text=True)
    resposta = app.response_class(
        "window.CatalogoProdutos = Object.freeze("
        + dados_json
        + ");",
        mimetype="application/javascript"
    )

    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


@app.post("/pedidos")
def criar_pedido():
    usuario = buscar_usuario_sessao()

    if usuario is None:
        return jsonify({
            "erro":"Entre na sua conta para confirmar o pedido."
        }),401

    if usuario["tipo"] != "cliente":
        return jsonify({
            "erro": "Somente cliente podem realizar pedidos."
        }),403

    itens_texto = request.form.get("itens", "")

    try:
        itens_recebidos = json.loads(itens_texto)
    except (json.JSONDecodeError, TypeError):
        return jsonify({
            "erro": "Os itens do pedido são inválidos"
        }),400

    if not isinstance (itens_recebidos, list) or not itens_recebidos:
        return jsonify({
            "erro": "O carrinho está vazio."
        }), 400

    if len (itens_recebidos) > 50:
        return jsonify({
            "erro": "O pedido possui itens demais."
        }),400

    quantidades = {}

    for item in itens_recebidos:
        if not isinstance (item, dict):
            return jsonify({
                "erro": "Existe um item inválido no carrinho."
            }), 400

        identificador = item.get("id")
        quantidade = item.get("quantidade")

        if(
            not isinstance(identificador, str)
            or not identificador.startswith("produto-")
            or not isinstance(quantidade, int)
            or isinstance(quantidade, bool)
            or quantidade <= 0
        ):

            return jsonify({
                "erro": "Existe um item inválido no carrinho."
            }), 400

        try:
            produto_id = int (identificador.removeprefix("produto-"))

        except ValueError:
            return jsonify({
                "erro": "Existe um produto inválido no carrinho"
            }), 400

        if produto_id <= 0 or produto_id in quantidades:
            return jsonify({
                "erro": "Existem produtos repetidos ou inválidos."
            }),400

        quantidades[produto_id] = quantidade

    marcadores = ",".join("?" for _ in quantidades)

    endereco_entrega = formatar_endereco(usuario)
    modalidade_entrega = "entrega" if endereco_entrega else "retirada"
    frete_centavos = (calcular_frete(usuario["cep"])[0] or 0) if endereco_entrega else 0

    conexao = conectar_banco()

    try:
        conexao.execute("BEGIN IMMEDIATE")

        produtos = conexao.execute(
            f"""
            SELECT id, empresa_id, nome, preco_centavos, estoque, ativo
            FROM produtos
            WHERE id IN ({marcadores})
            """,
            tuple(quantidades)
        ).fetchall()

        if len (produtos) != len(quantidades):
            conexao.rollback()
            return jsonify({
                "erro": "Um dos produtos não está mais disponível."
            }),400

        produtos_por_empresa = {}

        for produto in produtos:
            quantidade = quantidades[produto["id"]]

            if not produto["ativo"]:
                conexao.rollback()
                return jsonify({
                    "erro": f"{produto['nome']} não está mais disponivel."
                }),400

            if produto ["estoque"] < quantidade:
                conexao.rollback()
                return jsonify({
                    "erro": (
                        f"Estoque insuficiente para {produto['nome']}."
                        f"Disponível: {produto['estoque']}."
                    )
                }),400

            produtos_por_empresa.setdefault(
                produto["empresa_id"], []
            ).append((produto, quantidade))

        pedidos_criados = []

        for empresa_id, itens_empresa in produtos_por_empresa.items():
            total_produtos = sum(
                produto["preco_centavos"] * quantidade
                for produto, quantidade in itens_empresa
            )
            total_centavos = total_produtos + frete_centavos

            cursor = conexao.execute(
                """
                INSERT INTO pedidos (
                    empresa_id, cliente_id, total_centavos,
                    modalidade_entrega, endereco_entrega, frete_centavos
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    empresa_id,
                    usuario["id"],
                    total_centavos,
                    modalidade_entrega,
                    endereco_entrega or "",
                    frete_centavos,
                )
            )

            pedido_id = cursor.lastrowid

            for produto, quantidade in itens_empresa:
                conexao.execute(
                    """
                    INSERT INTO itens_pedido(
                    pedido_id,
                    produto_id,
                    nome_produto,
                    preco_unitario_centavos,
                    quantidade)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        pedido_id,
                        produto["id"],
                        produto["nome"],
                        produto["preco_centavos"],
                        quantidade
                    )
                )

                atualizacao = conexao.execute(
                    """
                    UPDATE produtos
                    SET estoque = estoque - ?
                    WHERE id = ?
                        AND ativo = 1
                        AND estoque >= ?
                    """,
                    (
                        quantidade,
                        produto["id"],
                        quantidade
                    )
                )

                if atualizacao.rowcount != 1:
                    raise ValueError(
                        f"Não foi possivel reservar {produto['nome']}."
                    )

            pedidos_criados.append(pedido_id)

        conexao.commit()

    except sqlite3.Error:
        conexao.rollback()
        app.logger.exception("Erro ao criar pedido.")
        return jsonify({
            "erro": "Não foi possível criar o pedido."
        }), 500

    except ValueError as erro:
        conexao.rollback()
        return jsonify({
            "erro": str(erro)
        }), 400

    finally:
        conexao.close()

    return jsonify({
        "mensagem": "Pedido confirmado com sucesso.",
        "pedidos": pedidos_criados,
        "frete_centavos": frete_centavos,
        "modalidade_entrega": modalidade_entrega
    }), 201


@app.get("/Pages/MeusPedidos.html")
def meus_pedidos():
    usuario = buscar_usuario_sessao()

    if usuario is None:
        return redirect("/Pages/login.html?next=/Pages/MeusPedidos.html")

    if usuario["tipo"] != "cliente":
        return redirect(pagina_inicial_usuario(usuario["tipo"]))

    conexao = conectar_banco()

    try:
        pedidos = conexao.execute(
            """
            SELECT p.id, p.status, p.total_centavos, p.modalidade_entrega,
                    p.endereco_entrega, p.frete_centavos,
                    e.nome AS empresa_nome
            FROM pedidos AS p
            JOIN empresas AS e ON e.id = p.empresa_id
            WHERE p.cliente_id = ?
            ORDER BY p.id DESC
            """,
            (usuario["id"],)
        ).fetchall()

        itens = conexao.execute(
            """
            SELECT i.pedido_id, i.nome_produto,
                    i.preco_unitario_centavos, i.quantidade
            FROM itens_pedido AS i
            JOIN pedidos AS p ON p.id = i.pedido_id
            WHERE p.cliente_id = ?
            ORDER BY i.id
            """,
            (usuario["id"],)
        ).fetchall()

    finally:
        conexao.close()

    itens_por_pedido = {}

    for item in itens:
        itens_por_pedido.setdefault(
            item["pedido_id"], []
        ).append(item)

    resposta = app.make_response(
        render_template(
            "MeusPedidos.html",
            pedidos=pedidos,
            itens_por_pedido=itens_por_pedido
        )
    )

    resposta.headers["Cache-Control"] = "no-store"
    return resposta


TRANSICOES_PEDIDOS = {
    "Recebido": ("Em separação", "Cancelado"),
    "Em separação": ("Pronto para retirada", "Cancelado"),
    "Pronto para retirada": ("Entregue", "Cancelado"),
    "Entregue": (),
    "Cancelado":(),
    }

@app.get("/Pages/Empresa/pedidos.html")
def listar_pedidos_empresa():
    usuario = buscar_usuario_sessao()

    if usuario is None:
        return redirect(
            "/Pages/login.html?next=/Pages/Empresa/pedidos.html"
        )


    if usuario ["tipo"] != "empresa":
        abort(403)

    conexao =  conectar_banco()

    try:
        empresa = conexao.execute(
                        """
            SELECT id, nome
            FROM empresas
            WHERE usuario_id = ?
            """,
            (usuario["id"],)
        ).fetchone()

        if empresa is None:
            abort(404, description = "Empresa não encontrada.")

        pedidos = conexao.execute(
                  """
            SELECT p.id, p.status, p.total_centavos, p.modalidade_entrega,
                   p.endereco_entrega, p.frete_centavos,
                   u.nome AS cliente_nome
            FROM pedidos AS p
            JOIN usuarios AS u ON u.id = p.cliente_id
            WHERE p.empresa_id = ?
            ORDER BY p.id DESC
            """,
            (empresa["id"],)
        ).fetchall()

        itens = conexao.execute(
                        """
            SELECT i.pedido_id, i.nome_produto,
                   i.preco_unitario_centavos, i.quantidade
            FROM itens_pedido AS i
            JOIN pedidos AS p ON p.id = i.pedido_id
            WHERE p.empresa_id = ?
            ORDER BY i.id
            """,
            (empresa["id"],)
        ).fetchall()

    finally:
        conexao.close()

    itens_por_pedido = {}

    for item in itens:
        itens_por_pedido.setdefault(
            item["pedido_id"],[]
        ).append(item)

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    resposta = app.make_response(
        render_template(
            "Empresa/pedidos.html",
            empresa=empresa,
            pedidos=pedidos,
            itens_por_pedido=itens_por_pedido,
            transicoes_pedidos=TRANSICOES_PEDIDOS,
            csrf_token=session["csrf_token"],
        )
    )

    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.post("/Pages/Empresa/pedidos/<int:pedido_id>/status")
def atualizar_status_pedido(pedido_id):
    usuario = buscar_usuario_sessao()

    if usuario is None:
        return redirect(
            "/Pages/login.html?next=/Pages/Empresa/pedidos.html"
        )

    if usuario["tipo"] != "empresa":
        abort(403)

    novo_status = request.form.get("status", "").strip()
    conexao = conectar_banco()

    try:
        conexao.execute("BEGIN IMMEDIATE")

        pedido = conexao.execute(
            """
            SELECT p.id, p.status
            FROM pedidos AS p
            JOIN empresas AS e ON e.id = p.empresa_id
            WHERE p.id = ? AND e.usuario_id = ?
            """,
            (pedido_id, usuario["id"]),
        ).fetchone()

        if pedido is None:
            abort(404)

        permitidos = TRANSICOES_PEDIDOS.get(pedido["status"], ())

        if novo_status not in permitidos:
            conexao.rollback()
            flash(
                "Essa mudança não é permitida. "
                "Confira a situação atual do pedido.",
                "erro",
            )
            return redirect("/Pages/Empresa/pedidos.html")

        if novo_status == "Cancelado":
            itens = conexao.execute(
                """
                SELECT produto_id, quantidade
                FROM itens_pedido
                WHERE pedido_id = ?
                """,
                (pedido_id,),
            ).fetchall()

            for item in itens:
                atualizacao = conexao.execute(
                    """
                    UPDATE produtos
                    SET estoque = estoque + ?
                    WHERE id = ?
                    """,
                    (item["quantidade"], item["produto_id"]),
                )

                if atualizacao.rowcount != 1:
                    raise ValueError(
                        "Não foi possível devolver um produto ao estoque."
                    )

        conexao.execute(
            """
            UPDATE pedidos
            SET status = ?, atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (novo_status, pedido_id),
        )

        conexao.commit()

    except (sqlite3.Error, ValueError):
        conexao.rollback()
        app.logger.exception("Erro ao atualizar o pedido.")
        flash(
            "Não foi possível atualizar o pedido. Tente novamente.",
            "erro",
        )

        return redirect("/Pages/Empresa/pedidos.html")

    finally:
        conexao.close()

    if novo_status == "Cancelado":
        flash(
            "Pedido cancelado. Os produtos foram devolvidos ao estoque.",
            "sucesso"
        )

    else:
        flash("Status do pedido atualizado com sucesso.", "sucesso")

    return redirect("/Pages/Empresa/pedidos.html")


@app.route("/Pages/solicitarAtendimento.html", methods=["GET", "POST"],)
def solicitar_atendimento():
    usuario = buscar_usuario_sessao()

    if usuario is None:
        return redirect(
            "/Pages/login.html?next=/Pages/solicitarAtendimento.html"
        )

    if usuario["tipo"] != "cliente":
        abort(403)

    erro = None
    codigo_resposta = 200
    conexao = conectar_banco()

    try:
        empresas = conexao.execute(
            """
            SELECT e.id, e.nome
            FROM empresas AS e
            JOIN usuarios AS u ON u.id = e.usuario_id
            WHERE u.tipo = 'empresa'
            ORDER BY e.nome, e.id
            """
        ).fetchall()

        if request.method == "POST":
            empresa_id = request.form.get(
                "empresa_id", type=int
            )
            aparelho = request.form.get("aparelho", "").strip()

            problema = request.form.get("problema", "").strip()
            servico_sugerido = request.form.get("servico_sugerido", "").strip()
            modalidade_entrada = request.form.get("modalidade_entrada", "")
            endereco_campos = {campo: request.form.get(campo, "").strip() for campo in (
                "cep_coleta", "logradouro_coleta", "numero_coleta", "complemento_coleta",
                "bairro_coleta", "cidade_coleta", "uf_coleta")}

            empresas_validas = {
                empresa["id"] for empresa in empresas
            }

            if modalidade_entrada not in {"coleta", "loja"}:
                erro = "Escolha como o aparelho chegará à assistência."
            elif modalidade_entrada == "coleta" and any(not endereco_campos[c] for c in (
                    "cep_coleta", "logradouro_coleta", "numero_coleta", "bairro_coleta", "cidade_coleta", "uf_coleta")):
                erro = "Preencha o endereço para buscar o aparelho."
            elif empresa_id not in empresas_validas:
                erro = "Selecione uma assistência válida."
            elif not 2 <= len(aparelho) <= 150:
                erro = (
                    "Informe o aparelho usando entre"
                    "2 e '50 caracteres."
                )
            elif not 10 <= len(problema) <= 2000:
                erro =(
                    "Descreva o problema usando entre "
                    "10 e 2000 caracteres."
                )
            elif not 3 <= len(servico_sugerido) <= 200:
                erro = "Informe o serviço desejado ou sugerido pela IA."

            if erro:
                codigo_resposta = 400
            else:
                conexao.execute(
                     """
                    INSERT INTO solicitacoes (
                        empresa_id, cliente_id, aparelho, problema, servico_sugerido,
                        modalidade_entrada, endereco_coleta
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        empresa_id,
                        usuario["id"],
                        aparelho,
                        problema,
                        servico_sugerido,
                        modalidade_entrada,
                        json.dumps(endereco_campos if any(endereco_campos.values()) else {}, ensure_ascii=False),
                    ),
                )
                conexao.commit()

                flash(
                    "Solicitação enviada à assistência com sucesso.",
                    "sucesso",
                )
                return redirect("/Pages/Acompanhar.html")


    except sqlite3.Error:
        conexao.rollback()
        app.logger.exception("Erro ao registrar solicitação.")
        erro = (
            "Não foi possível processar a solicitação."
            " Tente novamente."
        )
        codigo_resposta = 500
        empresas = []

    finally:
        conexao.close()

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    resposta = app.make_response((
        render_template(
            "solicitarAtendimento.html",
            empresas=empresas,
            erro=erro,
            csrf_token=session["csrf_token"],
            rascunho={},
        ),
        codigo_resposta,
    ))
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.get("/Pages/Empresa/solicitacoes.html")
def listar_solicitacoes_empresa():
    usuario = buscar_usuario_sessao()

    if usuario is None:
        return redirect(
            "/Pages/login.html?next=/Pages/Empresa/solicitacoes.html"
        )

    if usuario["tipo"] != "empresa":
        abort(403)

    conexao = conectar_banco()

    try:
        empresa = conexao.execute(
            """
            SELECT id, nome
            FROM empresas
            WHERE usuario_id = ?
            """,
            (usuario["id"],),
        ).fetchone()

        if empresa is None:
            abort(
                404,
                description="Empresa não encontrada.",
            )

        solicitacoes = conexao.execute(
            """
            SELECT
            s.id, s.aparelho, s.problema, s.status, s.criado_em,
          s.modalidade_entrada, s.endereco_coleta,
         s.valor_final_centavos, s.prazo_minimo_dias, s.prazo_maximo_dias,
          s.resposta_cliente, s.modalidade_saida,
          o.status AS status_orcamento,
            o.valor_centavos AS valor_orcamento_centavos,
           o.prazo_minimo_dias AS prazo_orcamento_minimo,
           o.prazo_maximo_dias AS prazo_orcamento_maximo,
           u.nome AS cliente_nome, u.email AS cliente_email,
           u.telefone AS cliente_telefone
            FROM solicitacoes AS s
            JOIN usuarios AS u ON u.id = s.cliente_id
            LEFT JOIN orcamentos AS o ON o.solicitacao_id = s.id
            WHERE s.empresa_id = ?
            ORDER BY s.id DESC
            """,
            (empresa["id"],),
        ).fetchall()
        solicitacoes = [dict(item) for item in solicitacoes]
        for solicitacao in solicitacoes:
            try:
                endereco = json.loads(solicitacao["endereco_coleta"] or "{}")
            except (TypeError, ValueError):
                endereco = {}
            solicitacao["endereco_coleta_formatado"] = ", ".join(
                endereco.get(campo, "").strip()
                for campo in ("logradouro_coleta", "numero_coleta", "bairro_coleta",
                              "cidade_coleta", "uf_coleta", "cep_coleta")
                if endereco.get(campo)
            )

    finally:
        conexao.close()

    resposta = app.make_response(
        render_template(
            "Empresa/solicitacoes.html",
            empresa=empresa,
            solicitacoes=solicitacoes,
        )
    )
    resposta.headers["Cache-Control"] = "no-store"
    return resposta

from orcamentos import registrar_rotas_orcamentos

registrar_rotas_orcamentos(
    app, conectar_banco, buscar_usuario_sessao
)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
