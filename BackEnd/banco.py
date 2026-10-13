import sqlite3 
from pathlib import Path

pasta = Path(__file__).parent 
caminho = pasta / "dados" / "ideia_tech.db"

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

conexao.commit()
conexao.close()

