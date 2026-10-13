import sqlite3 
from pathlib import Path

pasta = Path(__file__).parent 
pasta_dados = pasta / "dados"
pasta_dados.mkdir(parents=True, exist_ok=True)
caminho = pasta_dados /"ideia_tech.db"

conexao = sqlite3.connect(caminho)

sql = (pasta / "schema.sql").read_text(encoding="utf-8")
conexao.executescript(sql)
conexao.commit()
conexao.close()

