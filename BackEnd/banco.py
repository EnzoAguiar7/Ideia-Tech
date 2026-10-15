import sqlite3 
from pathlib import Path

pasta = Path(__file__).parent
pasta_dados = pasta / "dados"
pasta_dados.mkdir(parents=True, exist_ok=True)
caminho = pasta_dados / "ideia_tech.db"

conexao = sqlite3.connect(caminho)
conexao.execute("PRAGMA foreign_keys = ON")

sql = (pasta / "schema.sql").read_text(encoding="utf-8")
conexao.executescript(sql)

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

