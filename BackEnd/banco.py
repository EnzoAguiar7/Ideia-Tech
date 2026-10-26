import sqlite3 
from pathlib import Path

pasta = Path(__file__).parent
pasta_dados = pasta / "dados"
pasta_dados.mkdir(parents=True, exist_ok=True)
caminho = pasta_dados / "ideia_tech.db"

conexao = sqlite3.connect(caminho)
conexao.execute("PRAGMA foreign_keys = ON")

sql = (pasta / "schema.sql").read_text(encoding="utf-8")
# Uma execução interrompida pode ter criado solicitacoes com a FK e o
# valor padrão incorretos. CREATE TABLE IF NOT EXISTS não os corrige.
tabela_solicitacoes = conexao.execute(
    "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'solicitacoes'"
).fetchone()
if tabela_solicitacoes:
    referencias = conexao.execute("PRAGMA foreign_key_list(solicitacoes)").fetchall()
    colunas = conexao.execute("PRAGMA table_info(solicitacoes)").fetchall()
    padrao_status = next(c[4] for c in colunas if c[1] == "status")
    if any(r[2] == "cliente" for r in referencias) or padrao_status != "'Nova solicitação'":
        inicio = sql.index("CREATE TABLE IF NOT EXISTS solicitacoes (")
        fim = sql.index(";", inicio)
        criar_tabela = sql[inicio:fim].replace(
            "IF NOT EXISTS solicitacoes (", "solicitacoes_corrigidas (", 1
        )
        # A substituição inteira é transacional e preserva os registros.
        with conexao:
            conexao.execute("BEGIN IMMEDIATE")
            conexao.execute(criar_tabela)
            conexao.execute("""
                INSERT INTO solicitacoes_corrigidas
                    (id, empresa_id, cliente_id, aparelho, problema, status, criado_em)
                SELECT id, empresa_id, cliente_id, aparelho, problema,
                       CASE WHEN status = 'Nova solicitacao'
                            THEN 'Nova solicitação' ELSE status END,
                       criado_em
                FROM solicitacoes
            """)
            conexao.execute("DROP TABLE solicitacoes")
            conexao.execute("ALTER TABLE solicitacoes_corrigidas RENAME TO solicitacoes")

conexao.executescript(sql)

# Compatibilidade com bancos que já tinham a tabela orcamentos anterior.
colunas_orcamentos = {
    linha[1] for linha in conexao.execute("PRAGMA table_info(orcamentos)")
}
colunas_novas_orcamentos = {
    "prazo_minimo_dias": "INTEGER NOT NULL DEFAULT 1",
    "prazo_maximo_dias": "INTEGER NOT NULL DEFAULT 3",
    "taxa_devolucao_centavos": "INTEGER NOT NULL DEFAULT 0",
    "modalidade_saida": "TEXT NOT NULL DEFAULT ''",
    "respondido_em": "TEXT",
    "modalidade_saida_pronto": "TEXT NOT NULL DEFAULT ''",
    "pagamento_modalidade": "TEXT NOT NULL DEFAULT ''",
    "chegada_confirmada": "INTEGER NOT NULL DEFAULT 0",
}
colunas_novas_orcamentos["prazo_dias"] = "INTEGER NOT NULL DEFAULT 3"
for coluna, definicao in colunas_novas_orcamentos.items():
    if coluna not in colunas_orcamentos:
        conexao.execute(
            f"ALTER TABLE orcamentos ADD COLUMN {coluna} {definicao}"
        )
conexao.execute(
    """UPDATE orcamentos
       SET prazo_minimo_dias = prazo_dias, prazo_maximo_dias = prazo_dias
       WHERE prazo_dias IS NOT NULL AND prazo_maximo_dias = 3
         AND prazo_minimo_dias = 1 AND prazo_dias != 3"""
)

# Acrescenta os dados de orçamento e logística em bancos locais já existentes.
colunas_solicitacoes = {
    linha[1] for linha in conexao.execute("PRAGMA table_info(solicitacoes)")
}
colunas_novas_solicitacoes = {
    "servico_sugerido": "TEXT NOT NULL DEFAULT ''",
    "dispositivo_recebido": "INTEGER NOT NULL DEFAULT 0",
    "modalidade_entrada": "TEXT NOT NULL DEFAULT 'loja'",
    "endereco_coleta": "TEXT NOT NULL DEFAULT ''",
    "prazo_minimo_dias": "INTEGER",
    "prazo_maximo_dias": "INTEGER",
    "valor_final_centavos": "INTEGER",
    "taxa_devolucao_centavos": "INTEGER",
    "mensagem_orcamento": "TEXT NOT NULL DEFAULT ''",
    "orcamento_status": "TEXT NOT NULL DEFAULT 'Aguardando análise'",
    "resposta_cliente": "TEXT NOT NULL DEFAULT ''",
    "modalidade_saida": "TEXT NOT NULL DEFAULT ''",
    "respondido_em": "TEXT",
    # SQLite não aceita CURRENT_TIMESTAMP como default em ADD COLUMN.
    "atualizado_em": "TEXT NOT NULL DEFAULT ''",
}
for coluna, definicao in colunas_novas_solicitacoes.items():
    if coluna not in colunas_solicitacoes:
        conexao.execute(
            f"ALTER TABLE solicitacoes ADD COLUMN {coluna} {definicao}"
        )
conexao.execute(
    "UPDATE solicitacoes SET atualizado_em = CURRENT_TIMESTAMP WHERE atualizado_em = ''"
)

# CREATE TABLE IF NOT EXISTS não adiciona colunas em bancos já existentes.
# Esta migração idempotente mantém o banco local compatível com o schema atual.
colunas_usuarios = {
    linha[1] for linha in conexao.execute("PRAGMA table_info(usuarios)")
}
if "versao_sessao" not in colunas_usuarios:
    conexao.execute(
        "ALTER TABLE usuarios ADD COLUMN versao_sessao INTEGER NOT NULL DEFAULT 0"
    )

if "tipo" not in colunas_usuarios:
    conexao.execute(
        """
        ALTER TABLE usuarios
        ADD COLUMN tipo TEXT NOT NULL DEFAULT 'cliente'
        CHECK (tipo IN('cliente', 'empresa'))
        """
    )

colunas_novos_usuarios = {
    "cep": "TEXT NOT NULL DEFAULT ''",
    "logradouro": "TEXT NOT NULL DEFAULT ''",
    "numero_endereco": "TEXT NOT NULL DEFAULT ''",
    "complemento": "TEXT NOT NULL DEFAULT ''",
    "bairro": "TEXT NOT NULL DEFAULT ''",
    "cidade": "TEXT NOT NULL DEFAULT ''",
    "uf": "TEXT NOT NULL DEFAULT ''",
}

for coluna, definicao in colunas_novos_usuarios.items():
    if coluna not in colunas_usuarios:
        conexao.execute(f"ALTER TABLE usuarios ADD COLUMN {coluna} {definicao}")


colunas_pedidos = {
    linha[1] for linha in conexao.execute("PRAGMA table_info(pedidos)")
}

colunas_novos_pedidos = {
    "modalidade_entrega": "TEXT NOT NULL DEFAULT 'retirada'",
    "endereco_entrega": "TEXT NOT NULL DEFAULT ''",
    "frete_centavos": "INTEGER NOT NULL DEFAULT 0",
}

for coluna, definicao in colunas_novos_pedidos.items():
    if coluna not in colunas_pedidos:
        conexao.execute(f"ALTER TABLE pedidos ADD COLUMN {coluna} {definicao}")

colunas_empresas = {
    linha [1]
    for linha in conexao.execute("PRAGMA table_info(empresas)")
}

if "usuario_id" not in colunas_empresas:
    conexao.execute(
        """
        ALTER TABLE empresas
        ADD COLUMN usuario_id INTEGER REFERENCES usuarios(id)
        """
    )

conexao.execute(
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_empresas_usuario
    ON empresas(usuario_id)
    """
)

conexao.execute(
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email
    ON usuarios(email)
    """
)

# Atualiza o CHECK de tipo em bancos locais criados antes do perfil dev.
sql_usuarios = conexao.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='usuarios'"
).fetchone()[0]
if "desenvolvedor" not in sql_usuarios:
    conexao.commit()
    conexao.execute("PRAGMA foreign_keys = OFF")
    conexao.execute("BEGIN IMMEDIATE")
    conexao.execute("""
        CREATE TABLE usuarios_novo (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            telefone TEXT NOT NULL,
            senha_hash TEXT NOT NULL,
            cep TEXT NOT NULL DEFAULT '',
            logradouro TEXT NOT NULL DEFAULT '',
            numero_endereco TEXT NOT NULL DEFAULT '',
            complemento TEXT NOT NULL DEFAULT '',
            bairro TEXT NOT NULL DEFAULT '',
            cidade TEXT NOT NULL DEFAULT '',
            uf TEXT NOT NULL DEFAULT '',
            versao_sessao INTEGER NOT NULL DEFAULT 0,
            tipo TEXT NOT NULL DEFAULT 'cliente'
                CHECK (tipo IN ('cliente', 'empresa', 'desenvolvedor')),
            criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conexao.execute("""
        INSERT INTO usuarios_novo
            (id,nome,email,telefone,senha_hash,cep,logradouro,numero_endereco,
             complemento,bairro,cidade,uf,versao_sessao,tipo,criado_em)
        SELECT id,nome,email,telefone,senha_hash,cep,logradouro,numero_endereco,
               complemento,bairro,cidade,uf,versao_sessao,tipo,criado_em
        FROM usuarios
    """)
    conexao.execute("DROP TABLE usuarios")
    conexao.execute("ALTER TABLE usuarios_novo RENAME TO usuarios")
    conexao.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email)"
    )
    conexao.commit()
    conexao.execute("PRAGMA foreign_keys = ON")

conexao.executescript("""
CREATE TABLE IF NOT EXISTS conversas_suporte (
    id INTEGER PRIMARY KEY,
    empresa_id INTEGER NOT NULL UNIQUE REFERENCES empresas(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta','encerrada')),
    criada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mensagens_suporte (
    id INTEGER PRIMARY KEY,
    conversa_id INTEGER NOT NULL REFERENCES conversas_suporte(id) ON DELETE CASCADE,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    texto TEXT NOT NULL CHECK (length(texto) BETWEEN 1 AND 4000),
    criada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_mensagens_suporte_conversa
    ON mensagens_suporte(conversa_id, id);
CREATE INDEX IF NOT EXISTS idx_conversas_suporte_atualizada
    ON conversas_suporte(atualizada_em DESC);
""")
 
colunas_historico = {
    linha[1] for linha in conexao.execute("PRAGMA table_info(historico_ordens)")
}
colunas_ordens = {
    linha[1] for linha in conexao.execute("PRAGMA table_info(ordens_servico)")
}
if "orcamento_id" not in colunas_ordens:
    conexao.execute(
        "ALTER TABLE ordens_servico ADD COLUMN orcamento_id INTEGER REFERENCES orcamentos(id)"
    )
conexao.execute(
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_ordens_orcamento "
    "ON ordens_servico(orcamento_id) WHERE orcamento_id IS NOT NULL"
)

if "observacaoa" in colunas_historico and "observacao" not in colunas_historico:
    conexao.execute(
        "ALTER TABLE historico_ordens RENAME COLUMN observacaoa TO observacao"
    )

conexao.commit()
conexao.close()
