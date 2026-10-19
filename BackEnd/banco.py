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

# Acrescenta os dados de orçamento e logística em bancos locais já existentes.
colunas_solicitacoes = {
    linha[1] for linha in conexao.execute("PRAGMA table_info(solicitacoes)")
}
colunas_novas_solicitacoes = {
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
 
colunas_historico = {
    linha[1] for linha in conexao.execute("PRAGMA table_info(historico_ordens)")
}
if "observacaoa" in colunas_historico and "observacao" not in colunas_historico:
    conexao.execute(
        "ALTER TABLE historico_ordens RENAME COLUMN observacaoa TO observacao"
    )

conexao.commit()
conexao.close()
