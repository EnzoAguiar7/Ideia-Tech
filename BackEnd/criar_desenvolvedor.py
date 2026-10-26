"""Cria uma conta interna de desenvolvedor sem expor cadastro público."""
import getpass
import re
import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash


if __name__ == "__main__":
    raiz = Path(__file__).resolve().parent
    banco = raiz / "dados" / "ideia_tech.db"
    nome = input("Nome do desenvolvedor: ").strip()
    email = input("E-mail de acesso: ").strip().lower()
    telefone = input("Telefone: ").strip() or "Não informado"
    senha = getpass.getpass("Senha (mínimo 12 caracteres): ")
    confirmacao = getpass.getpass("Confirme a senha: ")
    if not 3 <= len(nome) <= 120 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise SystemExit("Informe nome e e-mail válidos.")
    if len(senha) < 12 or len(senha) > 128 or senha != confirmacao:
        raise SystemExit("As senhas devem coincidir e ter de 12 a 128 caracteres.")
    conexao = sqlite3.connect(banco)
    try:
        conexao.execute("PRAGMA foreign_keys = ON")
        conexao.execute(
            "INSERT INTO usuarios (nome,email,telefone,senha_hash,tipo) VALUES (?,?,?,?, 'desenvolvedor')",
            (nome, email, telefone[:20], generate_password_hash(senha)),
        )
        conexao.commit()
    except sqlite3.IntegrityError as erro:
        conexao.rollback()
        raise SystemExit("Não foi possível criar a conta. O e-mail pode já estar cadastrado.") from erro
    finally:
        conexao.close()
    print("Conta de desenvolvedor criada. Entre pela página de login do IdeiaTech.")
