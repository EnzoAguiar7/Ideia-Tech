"""Rotas e eventos do chat entre empresas e equipe de desenvolvimento."""
from flask import abort, jsonify, redirect, render_template, request, session
from flask_socketio import emit, join_room


LIMITE_MENSAGEM = 4000


def registrar_suporte(app, socketio, conectar_banco, buscar_usuario_sessao):
    def empresa_do_usuario(usuario, conexao):
        return conexao.execute(
            "SELECT id, nome FROM empresas WHERE usuario_id = ?",
            (usuario["id"],),
        ).fetchone()

    def conversa_acessivel(usuario, conversa_id, conexao):
        conversa = conexao.execute(
            """SELECT c.id, c.empresa_id, c.status, e.nome AS empresa_nome,
                      u.nome AS responsavel_nome
               FROM conversas_suporte c
               JOIN empresas e ON e.id = c.empresa_id
               JOIN usuarios u ON u.id = e.usuario_id
               WHERE c.id = ?""",
            (conversa_id,),
        ).fetchone()
        if conversa is None:
            return None
        if usuario["tipo"] == "desenvolvedor":
            return conversa
        empresa = empresa_do_usuario(usuario, conexao) if usuario["tipo"] == "empresa" else None
        return conversa if empresa and empresa["id"] == conversa["empresa_id"] else None

    def buscar_ou_criar_conversa(empresa_id, conexao):
        conexao.execute(
            """INSERT INTO conversas_suporte (empresa_id) VALUES (?)
               ON CONFLICT(empresa_id) DO UPDATE SET status='aberta',
               atualizada_em=CURRENT_TIMESTAMP
               WHERE conversas_suporte.status='encerrada'""",
            (empresa_id,),
        )
        conexao.commit()
        return conexao.execute(
            "SELECT id, status FROM conversas_suporte WHERE empresa_id = ?",
            (empresa_id,),
        ).fetchone()

    @app.get("/Pages/Empresa/suporte.html")
    def pagina_suporte_empresa():
        usuario = buscar_usuario_sessao()
        if usuario is None:
            return redirect("/Pages/login.html?next=/Pages/Empresa/suporte.html")
        if usuario["tipo"] != "empresa":
            abort(403)
        conexao = conectar_banco()
        try:
            empresa = empresa_do_usuario(usuario, conexao)
            if empresa is None:
                abort(404)
            conversa = buscar_ou_criar_conversa(empresa["id"], conexao)
        finally:
            conexao.close()
        if "csrf_token" not in session:
            import secrets
            session["csrf_token"] = secrets.token_urlsafe(32)
        resposta = app.make_response(render_template(
            "Empresa/suporte.html", empresa=empresa, conversa=conversa,
            usuario=usuario, csrf_token=session["csrf_token"],
        ))
        resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.get("/Pages/Desenvolvedor/suporte.html")
    def pagina_suporte_desenvolvedor():
        usuario = buscar_usuario_sessao()
        if usuario is None:
            return redirect("/Pages/login.html?next=/Pages/Desenvolvedor/suporte.html")
        if usuario["tipo"] != "desenvolvedor":
            abort(403)
        conexao = conectar_banco()
        try:
            conversas = conexao.execute(
                """SELECT c.id, c.status, c.atualizada_em, e.nome AS empresa_nome,
                          u.nome AS responsavel_nome,
                          (SELECT texto FROM mensagens_suporte m
                           WHERE m.conversa_id = c.id ORDER BY m.id DESC LIMIT 1) AS ultima_mensagem
                   FROM conversas_suporte c
                   JOIN empresas e ON e.id = c.empresa_id
                   JOIN usuarios u ON u.id = e.usuario_id
                   ORDER BY CASE c.status WHEN 'aberta' THEN 0 ELSE 1 END,
                            c.atualizada_em DESC"""
            ).fetchall()
        finally:
            conexao.close()
        if "csrf_token" not in session:
            import secrets
            session["csrf_token"] = secrets.token_urlsafe(32)
        selecionada = request.args.get("conversa", type=int)
        if selecionada not in {c["id"] for c in conversas}:
            selecionada = conversas[0]["id"] if conversas else None
        resposta = app.make_response(render_template(
            "Desenvolvedor/suporte.html", conversas=conversas,
            selecionada=selecionada, usuario=usuario,
            csrf_token=session["csrf_token"],
        ))
        resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.get("/api/suporte/conversas/<int:conversa_id>/mensagens")
    def listar_mensagens_suporte(conversa_id):
        usuario = buscar_usuario_sessao()
        if usuario is None:
            return jsonify({"erro": "Entre novamente para continuar."}), 401
        conexao = conectar_banco()
        try:
            conversa = conversa_acessivel(usuario, conversa_id, conexao)
            if conversa is None:
                abort(403)
            mensagens = conexao.execute(
                """SELECT m.id, m.usuario_id, u.nome AS autor, u.tipo,
                          m.texto, m.criada_em
                   FROM mensagens_suporte m JOIN usuarios u ON u.id = m.usuario_id
                   WHERE m.conversa_id = ? ORDER BY m.id DESC LIMIT 100""",
                (conversa_id,),
            ).fetchall()
            mensagens = [dict(m) for m in reversed(mensagens)]
            return jsonify({"conversa": dict(conversa), "mensagens": mensagens})
        finally:
            conexao.close()

    @socketio.on("connect", namespace="/suporte")
    def conectar_suporte(auth=None):
        usuario = buscar_usuario_sessao()
        token = (auth or {}).get("csrf_token", "")
        esperado = session.get("csrf_token", "")
        import secrets
        if (usuario is None or not token or not esperado
                or not secrets.compare_digest(token, esperado)
                or usuario["tipo"] not in {"empresa", "desenvolvedor"}):
            return False

    @socketio.on("entrar_conversa", namespace="/suporte")
    def entrar_conversa(dados):
        usuario = buscar_usuario_sessao()
        conversa_id = (dados or {}).get("conversa_id")
        if usuario is None or not isinstance(conversa_id, int):
            return {"ok": False, "erro": "Acesso não autorizado."}
        conexao = conectar_banco()
        try:
            conversa = conversa_acessivel(usuario, conversa_id, conexao)
            if conversa is None:
                return {"ok": False, "erro": "Conversa não encontrada."}
        finally:
            conexao.close()
        join_room(f"suporte-{conversa_id}")
        return {"ok": True}

    @socketio.on("enviar_mensagem", namespace="/suporte")
    def enviar_mensagem(dados):
        usuario = buscar_usuario_sessao()
        dados = dados or {}
        conversa_id = dados.get("conversa_id")
        texto = dados.get("texto", "")
        if (usuario is None or not isinstance(conversa_id, int)
                or not isinstance(texto, str)):
            return {"ok": False, "erro": "Mensagem inválida."}
        texto = texto.strip()
        if not texto or len(texto) > LIMITE_MENSAGEM:
            return {"ok": False, "erro": "A mensagem deve ter até 4.000 caracteres."}
        conexao = conectar_banco()
        try:
            conversa = conversa_acessivel(usuario, conversa_id, conexao)
            if conversa is None:
                return {"ok": False, "erro": "Conversa não encontrada."}
            if conversa["status"] != "aberta":
                return {"ok": False, "erro": "Esta conversa está encerrada."}
            cursor = conexao.execute(
                "INSERT INTO mensagens_suporte (conversa_id, usuario_id, texto) VALUES (?, ?, ?)",
                (conversa_id, usuario["id"], texto),
            )
            conexao.execute(
                "UPDATE conversas_suporte SET atualizada_em = CURRENT_TIMESTAMP WHERE id = ?",
                (conversa_id,),
            )
            conexao.commit()
            mensagem = conexao.execute(
                """SELECT m.id, m.usuario_id, u.nome AS autor, u.tipo,
                          m.texto, m.criada_em FROM mensagens_suporte m
                   JOIN usuarios u ON u.id = m.usuario_id WHERE m.id = ?""",
                (cursor.lastrowid,),
            ).fetchone()
            payload = dict(mensagem)
        except Exception:
            conexao.rollback()
            raise
        finally:
            conexao.close()
        emit("nova_mensagem", payload, to=f"suporte-{conversa_id}", namespace="/suporte")
        return {"ok": True}

    @socketio.on("encerrar_conversa", namespace="/suporte")
    def encerrar_conversa(dados):
        usuario = buscar_usuario_sessao()
        conversa_id = (dados or {}).get("conversa_id")
        if usuario is None or usuario["tipo"] != "desenvolvedor" or not isinstance(conversa_id, int):
            return {"ok": False, "erro": "Acesso não autorizado."}
        conexao = conectar_banco()
        try:
            conexao.execute(
                "UPDATE conversas_suporte SET status='encerrada', atualizada_em=CURRENT_TIMESTAMP WHERE id=?",
                (conversa_id,),
            )
            conexao.commit()
        finally:
            conexao.close()
        emit("conversa_encerrada", {"conversa_id": conversa_id},
             to=f"suporte-{conversa_id}", namespace="/suporte")
        return {"ok": True}
