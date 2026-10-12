import sqlite3
from pathlib import Path
from getpass import getpass
from werkzeug.security import generate_password_hash

caminho = Path(__file__).parent / "dados" / "ideia_tech.db"

nome = input("Nome: ").strip()
email = input("E-mail: ").strip().lower()
telefone = input("Telefone: ").strip()
senha = getpass("Senha: ")
confirmacao = getpass("Confirme a senha: ")

if not nome or not email or not telefone:
    print("Preencha todos os campos.")
elif len(senha) < 8:
    print("Use pelo menos 8 caracteres na sua senha.")
elif senha != confirmacao:
    print("As senhas não são iguais.")
else:
    senha_hash = generate_password_hash(senha)
    conexao = sqlite3.connect(caminho)

    try:
        conexao.execute(
            """
            INSERT INTO usuarios (nome, email, telefone, senha_hash)
            VALUES (?, ?, ?, ?)
            """,
            (nome, email, telefone, senha_hash)
        )
        conexao.commit()
        print("Usuário cadastrado!")
    except sqlite3.IntegrityError:
        print("Não foi possível cadastrar. Confira se o e-mail já existe.")
    finally:
        conexao.close()

        