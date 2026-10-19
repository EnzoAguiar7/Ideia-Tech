import json
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
                       o.prazo_dias, o.prazo_minimo_dias, o.prazo_maximo_dias,
                       o.taxa_devolucao_centavos, o.modalidade_saida,
                       o.status, o.criado_em, s.modalidade_entrada,
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
                       o.valor_centavos, o.prazo_dias, o.prazo_minimo_dias,
                       o.prazo_maximo_dias, o.taxa_devolucao_centavos,
                       s.modalidade_entrada, s.id AS solicitacao_id,
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

            modalidade_saida = request.form.get("modalidade_saida", "").strip()
            if decisao == "Recusado":
                opcoes_saida = {"retirada"}
                if (
                    orcamento["modalidade_entrada"] == "coleta"
                    and orcamento["taxa_devolucao_centavos"] is not None
                ):
                    opcoes_saida.add("devolucao")
                if modalidade_saida not in opcoes_saida:
                    flash("Escolha receber o aparelho de volta ou buscá-lo na assistência.", "erro")
                    return redirect("/Pages/MeusOrcamentos.html")
            else:
                modalidade_saida = ""

            conexao.execute(
                """UPDATE orcamentos
                   SET status = ?, modalidade_saida = ?, respondido_em = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (decisao, modalidade_saida, orcamento_id),
            )
            if decisao == "Aprovado":
                problema = (
                    f"Orçamento #{orcamento_id} aprovado. "
                    f"Diagnóstico: {orcamento['diagnostico']} Serviço: "
                    f"{orcamento['servico']} Valor: R$ "
                    f"{orcamento['valor_centavos'] / 100:.2f}. "
                    f"Prazo estimado: de {orcamento['prazo_minimo_dias']} a "
                    f"{orcamento['prazo_maximo_dias']} dias úteis."
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
                mensagem = (
                    "Orçamento recusado. Cliente escolheu "
                    + ("devolução ao endereço" if modalidade_saida == "devolucao"
                       else "retirada na assistência")
                    + (f" com taxa de R$ {orcamento['taxa_devolucao_centavos'] / 100:.2f}."
                       if modalidade_saida == "devolucao" else ".")
                )
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
                prazo_minimo = request.form.get("prazo_minimo_dias", type=int)
                prazo_maximo = request.form.get("prazo_maximo_dias", type=int)
                valor_texto = request.form.get("valor", "").strip().replace(",", ".")
                taxa_texto = request.form.get("taxa_devolucao", "0").strip().replace(",", ".")
                try:
                    valor = Decimal(valor_texto)
                    if (not valor.is_finite()
                            or not Decimal("0.01") <= valor <= Decimal("999999.99")):
                        raise ValueError
                    centavos = valor * 100
                    if centavos != centavos.to_integral_value():
                        raise ValueError
                    valor_centavos = int(centavos)
                    taxa = Decimal(taxa_texto)
                    if (not taxa.is_finite()
                            or not Decimal("0") <= taxa <= Decimal("999999.99")):
                        raise ValueError
                    taxa_centavos = taxa * 100
                    if taxa_centavos != taxa_centavos.to_integral_value():
                        raise ValueError
                    taxa_devolucao_centavos = int(taxa_centavos)
                except (InvalidOperation, ValueError):
                    erro = ("Informe um valor entre 0,01 e 999999,99, "
                            "com até duas casas decimais, sem milhar.")

                if not erro:
                    if not 5 <= len(diagnostico) <= 2000:
                        erro = "O diagnóstico deve ter entre 5 e 2000 caracteres."
                    elif not 3 <= len(servico) <= 1000:
                        erro = "O serviço deve ter entre 3 e 1000 caracteres."
                    elif (prazo_minimo is None or prazo_maximo is None
                            or not 1 <= prazo_minimo <= prazo_maximo <= 365):
                        erro = "Informe uma faixa de prazo entre 1 e 365 dias úteis."

                if not erro:
                    conexao.execute("BEGIN IMMEDIATE")
                    solicitacao = conexao.execute(
                        """
                        SELECT s.id, s.modalidade_entrada FROM solicitacoes AS s
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
                        if solicitacao["modalidade_entrada"] != "coleta":
                            taxa_devolucao_centavos = 0
                        conexao.execute(
                            """
                            INSERT INTO orcamentos (
                                solicitacao_id, diagnostico, servico,
                                valor_centavos, prazo_dias,
                                prazo_minimo_dias, prazo_maximo_dias,
                                taxa_devolucao_centavos
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (solicitacao_id, diagnostico, servico, valor_centavos,
                             prazo_maximo, prazo_minimo, prazo_maximo,
                             taxa_devolucao_centavos),
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
                SELECT s.id, s.aparelho, u.nome AS cliente_nome,
                       s.modalidade_entrada, s.prazo_minimo_dias,
                       s.prazo_maximo_dias, s.endereco_coleta
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
            solicitacoes = [dict(linha) for linha in solicitacoes]
            for solicitacao in solicitacoes:
                try:
                    endereco = json.loads(solicitacao["endereco_coleta"] or "{}")
                except (TypeError, ValueError):
                    endereco = {}
                solicitacao["endereco_coleta_formatado"] = ", ".join(
                    str(endereco.get(campo, "")).strip()
                    for campo in (
                        "logradouro_coleta", "numero_coleta", "bairro_coleta",
                        "cidade_coleta", "uf_coleta", "cep_coleta",
                    )
                    if endereco.get(campo)
                )
            orcamentos = conexao.execute(
                """
                SELECT o.id, o.diagnostico, o.servico, o.valor_centavos,
                       o.prazo_dias, o.prazo_minimo_dias, o.prazo_maximo_dias,
                       o.taxa_devolucao_centavos, o.modalidade_saida, o.status,
                       s.aparelho, s.modalidade_entrada, u.nome AS cliente_nome,
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
