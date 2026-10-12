import sqlite3
from pathlib import Path

caminho = Path(__file__).parent / "dados" / "ideia_tech.db"

nome = input("Nome da sua empresa: ").strip()
telefone = input("Telefone: ").strip()
cnpj = input("CNPJ (opcional): ").strip() or None

if not nome or not telefone:
    print("Nome e telefone são campos obrigatorios.")
else:
    conexao = sqlite3.connect(caminho)

    try:
        conexao.execute(
            "INSERT INTO empresas (nome, telefone, cnpj) VALUES (?, ?, ?)",
            (nome, telefone, cnpj)
        )
        conexao.commit()
        print("Empresa cadastrada!")
    except sqlite3.IntegrityError:
        print("Não foi possível cadastrar. Confira se o CNPJ já existe.")
    finally:
        conexao.close()