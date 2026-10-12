import sqlite3 
from pathlib import Path

pasta = Path(__file__).parent 
caminho = pasta / "dados" / "ideia_tech.db"

conexao = sqlite3.connect(caminho)

sql = (pasta / "schema.sql").read_text(encoding="utf-8")
conexao.executescript(sql)
conexao.commit()
conexao.close()

