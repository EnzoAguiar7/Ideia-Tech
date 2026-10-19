import secrets
import sqlite3
from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, session


def registrar_rotas_orcamentos(app, conectar_banco, buscar_usuario_sessao):
    @app.get("/Pages/MeusOrcamentos.html")
    def meus_orcamentos():
        usuario = buscar_usuario_sessao()
        if usuario is None:
            return redirect("/Pages/login.html?next=/Pages/MeusOrcamentos.html")
        if usuario["tipo"] != "cliente":
            abort(403)

        conexao = conectar_banco()
        try:
            orcamentos = conexao.execute(
                """
                SELECT o.id, o.diagnostico, o.servico, o.valor_centavos,
                       o.prazo_dias, o.status, o.criado_em,
                       s.aparelho, s.problema, e.nome AS empresa_nome,
                       EXISTS (SELECT 1 FROM ordens_servico AS os
                               WHERE os.orcamento_id = o.id) AS ordem_criada
                FROM orcamentos AS o
                JOIN solicitacoes AS s ON s.id = o.solicitacao_id
                JOIN empresas AS e ON e.id = s.empresa_id
                WHERE s.cliente_id = ?
                ORDER BY o.id DESC
                """,
                (usuario["id"],),
            ).fetchall()
        finally:
            conexao.close()

        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        resposta = app.make_response(render_template(
            "MeusOrcamentos.html", orcamentos=orcamentos,
            csrf_token=session["csrf_token"],
        ))
        resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.post("/Pages/MeusOrcamentos/<int:orcamento_id>/decisao")
    def decidir_orcamento(orcamento_id):
        usuario = buscar_usuario_sessao()
        if usuario is None:
            return redirect("/Pages/login.html?next=/Pages/MeusOrcamentos.html")
        if usuario["tipo"] != "cliente":
            abort(403)
        decisao = request.form.get("decisao", "")
        if decisao not in {"Aprovado", "Recusado"}:
            abort(400)

        conexao = conectar_banco()
        try:
            conexao.execute("BEGIN IMMEDIATE")
            orcamento = conexao.execute(
                """
                SELECT o.id, o.status, o.diagnostico, o.servico,
                       o.valor_centavos, o.prazo_dias, s.id AS solicitacao_id,
                       s.empresa_id, s.cliente_id, s.aparelho
                FROM orcamentos AS o
                JOIN solicitacoes AS s ON s.id = o.solicitacao_id
                WHERE o.id = ? AND s.cliente_id = ?
                """,
                (orcamento_id, usuario["id"]),
            ).fetchone()
            if orcamento is None:
                abort(404)
            if orcamento["status"] != "Aguardando aprovação":
                flash("Este orçamento já recebeu uma decisão.", "erro")
                return redirect("/Pages/MeusOrcamentos.html")

            conexao.execute(
                "UPDATE orcamentos SET status = ? WHERE id = ?",
                (decisao, orcamento_id),
            )
            if decisao == "Aprovado":
                problema = (
                    f"Orçamento #{orcamento_id} aprovado. "
                    f"Diagnóstico: {orcamento['diagnostico']} Serviço: "
                    f"{orcamento['servico']} Valor: R$ "
                    f"{orcamento['valor_centavos'] / 100:.2f}. "
                    f"Prazo estimado: {orcamento['prazo_dias']} dias."
                )
                cursor = conexao.execute(
                    """
                    INSERT INTO ordens_servico (
                        empresa_id, cliente_id, aparelho, problema, previsao,
                        orcamento_id
                    ) VALUES (?, ?, ?, ?, NULL, ?)
                    """,
                    (orcamento["empresa_id"], usuario["id"],
                     orcamento["aparelho"], problema, orcamento_id),
                )
                conexao.execute(
                    "INSERT INTO historico_ordens (ordem_id, status, observacao) "
                    "VALUES (?, 'Recebido', ?)",
                    (cursor.lastrowid, f"Criada a partir do orçamento #{orcamento_id}."),
                )
                mensagem = "Orçamento aprovado. A ordem de serviço foi criada."
            else:
                mensagem = "Orçamento recusado."
            conexao.execute(
                "UPDATE solicitacoes SET status = 'Concluída' WHERE id = ?",
                (orcamento["solicitacao_id"],),
            )
            conexao.commit()
        except sqlite3.Error:
            conexao.rollback()
            app.logger.exception("Erro ao registrar decisão do orçamento.")
            abort(500, description="Erro ao registrar decisão do orçamento.")
        finally:
            conexao.close()
        flash(mensagem, "sucesso")
        return redirect("/Pages/MeusOrcamentos.html")

    @app.route("/Pages/Empresa/orcamentos.html", methods=["GET", "POST"])
    def orcamentos_empresa():
        usuario = buscar_usuario_sessao()
        if usuario is None:
            return redirect("/Pages/login.html?next=/Pages/Empresa/orcamentos.html")
        if usuario["tipo"] != "empresa":
            abort(403)

        erro = None
        codigo = 200
        conexao = conectar_banco()
        try:
            empresa = conexao.execute(
                "SELECT id, nome FROM empresas WHERE usuario_id = ?",
                (usuario["id"],),
            ).fetchone()
            if empresa is None:
                abort(404, description="Empresa não encontrada.")

            if request.method == "POST":
                solicitacao_id = request.form.get("solicitacao_id", type=int)
                diagnostico = request.form.get("diagnostico", "").strip()
                servico = request.form.get("servico", "").strip()
                prazo = request.form.get("prazo_dias", type=int)
                valor_texto = request.form.get("valor", "").strip().replace(",", ".")
                try:
                    valor = Decimal(valor_texto)
                    if (not valor.is_finite()
                            or not Decimal("0.01") <= valor <= Decimal("999999.99")):
                        raise ValueError
                    centavos = valor * 100
                    if centavos != centavos.to_integral_value():
                        raise ValueError
                    valor_centavos = int(centavos)
                except (InvalidOperation, ValueError):
                    erro = ("Informe um valor entre 0,01 e 999999,99, "
                            "com até duas casas decimais, sem milhar.")

                if not erro:
                    if not 5 <= len(diagnostico) <= 2000:
                        erro = "O diagnóstico deve ter entre 5 e 2000 caracteres."
                    elif not 3 <= len(servico) <= 1000:
                        erro = "O serviço deve ter entre 3 e 1000 caracteres."
                    elif prazo is None or not 1 <= prazo <= 365:
                        erro = "Informe um prazo de 1 a 365 dias."

                if not erro:
                    conexao.execute("BEGIN IMMEDIATE")
                    solicitacao = conexao.execute(
                        """
                        SELECT s.id FROM solicitacoes AS s
                        WHERE s.id = ? AND s.empresa_id = ?
                          AND s.status IN ('Nova solicitação', 'Em análise')
                          AND NOT EXISTS (
                              SELECT 1 FROM orcamentos AS o
                              WHERE o.solicitacao_id = s.id
                          )
                        """,
                        (solicitacao_id, empresa["id"]),
                    ).fetchone()
                    if solicitacao is None:
                        conexao.rollback()
                        erro = ("Solicitação indisponível, encerrada "
                                "ou já possui orçamento.")
                    else:
                        conexao.execute(
                            """
                            INSERT INTO orcamentos (
                                solicitacao_id, diagnostico, servico,
                                valor_centavos, prazo_dias
                            ) VALUES (?, ?, ?, ?, ?)
                            """,
                            (solicitacao_id, diagnostico, servico, valor_centavos, prazo),
                        )
                        conexao.execute(
                            """
                            UPDATE solicitacoes SET status = 'Em análise'
                            WHERE id = ? AND empresa_id = ?
                            """,
                            (solicitacao_id, empresa["id"]),
                        )
                        conexao.commit()
                        flash("Orçamento cadastrado com sucesso.", "sucesso")
                        return redirect("/Pages/Empresa/orcamentos.html")
                if erro:
                    codigo = 400

            solicitacoes = conexao.execute(
                """
                SELECT s.id, s.aparelho, u.nome AS cliente_nome
                FROM solicitacoes AS s
                JOIN usuarios AS u ON u.id = s.cliente_id
                WHERE s.empresa_id = ?
                  AND s.status IN ('Nova solicitação', 'Em análise')
                  AND NOT EXISTS (
                      SELECT 1 FROM orcamentos AS o WHERE o.solicitacao_id = s.id
                  )
                ORDER BY s.id DESC
                """,
                (empresa["id"],),
            ).fetchall()
            orcamentos = conexao.execute(
                """
                SELECT o.id, o.diagnostico, o.servico, o.valor_centavos,
                       o.prazo_dias, o.status, s.aparelho, u.nome AS cliente_nome,
                       EXISTS (SELECT 1 FROM ordens_servico AS os
                               WHERE os.orcamento_id = o.id) AS ordem_criada
                FROM orcamentos AS o
                JOIN solicitacoes AS s ON s.id = o.solicitacao_id
                JOIN usuarios AS u ON u.id = s.cliente_id
                WHERE s.empresa_id = ?
                ORDER BY o.id DESC
                """,
                (empresa["id"],),
            ).fetchall()
        except sqlite3.Error:
            conexao.rollback()
            app.logger.exception("Erro ao processar orçamento.")
            abort(500, description="Erro ao processar orçamento.")
        finally:
            conexao.close()

        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        resposta = app.make_response((
            render_template(
                "Empresa/orcamentos.html", empresa=empresa,
                solicitacoes=solicitacoes, orcamentos=orcamentos,
                erro=erro, csrf_token=session["csrf_token"],
            ),
            codigo,
        ))
        resposta.headers["Cache-Control"] = "no-store"
        return resposta
