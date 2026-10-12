import sqlite3
from pathlib import Path
from getpass import getpass
from werkzeug.security import check_password_hash

caminho = Path(__file__).parent / "dados" / "ideia_tech.db"

email = input ("E-mail: ").strip().lower()
senha = getpass ("Senha: ")

conexao = sqlite3.connect(caminho)
conexao.row_factory = sqlite3.Row

try:
    usuario = conexao.execute(
        "SELECT nome, senha_hash FROM usuarios WHERE email = ?",
        (email, )
    ).fetchone()

    if usuario and check_password_hash(usuario["senha_hash"], senha):
        print (f"Login correto! Olá, {usuario['nome']}.")
    else:
        print("Email ou senha incorretos.")
finally:
    conexao.close()