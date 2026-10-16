import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as servidor


class PedidosTest(unittest.TestCase):
    def setUp(self):
        temporario = tempfile.TemporaryDirectory()
        self.addCleanup(temporario.cleanup)
        self.banco = Path(temporario.name) / "pedidos.db"
        patch_banco = patch.object(servidor, "caminho_banco", self.banco)
        patch_banco.start()
        self.addCleanup(patch_banco.stop)
        with closing(sqlite3.connect(self.banco)) as conexao, conexao:
            conexao.executescript(
                (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
            )
            conexao.executemany(
                "INSERT INTO usuarios (id, nome, email, telefone, senha_hash, tipo) VALUES (?, ?, ?, '', 'hash', ?)",
                [(1, "Empresa A", "a@example.com", "empresa"),
                 (2, "Empresa B", "b@example.com", "empresa"),
                 (3, "Cliente", "c@example.com", "cliente")]
            )
            conexao.executemany(
                "INSERT INTO empresas (id, usuario_id, nome, telefone) VALUES (?, ?, ?, '')",
                [(1, 1, "Empresa A"), (2, 2, "Empresa B")]
            )
            conexao.executemany(
                "INSERT INTO produtos (id, empresa_id, nome, categoria, preco_centavos, estoque, ativo) VALUES (?, ?, ?, 'Peças', ?, ?, ?)",
                [(1, 1, "Teclado", 1500, 10, 1),
                 (2, 1, "Mouse", 1000, 8, 1),
                 (3, 2, "Monitor", 20000, 5, 1),
                 (4, 2, "Inativo", 500, 4, 0)]
            )
        self.cliente = servidor.app.test_client()
        self.autenticar(3)

    def autenticar(self, usuario_id):
        with self.cliente.session_transaction() as sessao:
            sessao.clear()
            if usuario_id is not None:
                sessao["usuario_id"] = usuario_id
                sessao["versao_sessao"] = 0
            sessao["csrf_token"] = "token-teste"

    def enviar(self, itens, token="token-teste"):
        return self.cliente.post("/pedidos", data={
            "itens": json.dumps(itens), "csrf_token": token
        })

    def consultar(self, sql):
        with closing(sqlite3.connect(self.banco)) as conexao:
            return conexao.execute(sql).fetchall()

    def verificar_sem_alteracoes(self):
        self.assertEqual(self.consultar("SELECT id FROM pedidos"), [])
        self.assertEqual(self.consultar("SELECT id FROM itens_pedido"), [])
        self.assertEqual(self.consultar("SELECT estoque FROM produtos ORDER BY id"),
                         [(10,), (8,), (5,), (4,)])

    def test_agrupa_por_empresa_sem_duplicar_pedidos_ou_baixas(self):
        resposta = self.enviar([
            {"id": "produto-1", "quantidade": 2},
            {"id": "produto-2", "quantidade": 3},
            {"id": "produto-3", "quantidade": 1}
        ])
        self.assertEqual(resposta.status_code, 201, resposta.get_data(as_text=True))
        pedidos = self.consultar("SELECT id, empresa_id, cliente_id, total_centavos FROM pedidos ORDER BY empresa_id")
        self.assertEqual([p[1:] for p in pedidos], [(1, 3, 6000), (2, 3, 20000)])
        self.assertEqual(resposta.get_json()["pedidos"], [p[0] for p in pedidos])
        self.assertEqual(self.consultar("SELECT produto_id, nome_produto, preco_unitario_centavos, quantidade FROM itens_pedido ORDER BY produto_id"),
                         [(1, "Teclado", 1500, 2), (2, "Mouse", 1000, 3), (3, "Monitor", 20000, 1)])
        self.assertEqual(self.consultar("SELECT estoque FROM produtos ORDER BY id"),
                         [(8,), (5,), (4,), (4,)])

    def test_rejeita_produto_inexistente_inativo_ou_sem_estoque(self):
        for produto_id, quantidade in [(999, 1), (4, 1), (3, 6)]:
            with self.subTest(produto_id=produto_id):
                resposta = self.enviar([
                    {"id": "produto-1", "quantidade": 1},
                    {"id": f"produto-{produto_id}", "quantidade": quantidade}
                ])
                self.assertEqual(resposta.status_code, 400)
                self.verificar_sem_alteracoes()

    def test_rejeita_carrinho_invalido(self):
        casos = [[], {}, [None], [{"id": "produto-x", "quantidade": 1}],
                 [{"id": "produto-0", "quantidade": 1}],
                 [{"id": "produto-1", "quantidade": 1}] * 2,
                 [{"id": "produto-1", "quantidade": 1}] * 51]
        casos.extend([[{"id": "produto-1", "quantidade": q}]
                      for q in [0, -1, True, "1", 1.5]])
        for itens in casos:
            with self.subTest(itens=itens):
                self.assertEqual(self.enviar(itens).status_code, 400)
                self.verificar_sem_alteracoes()
        resposta = self.cliente.post("/pedidos", data={
            "itens": "json inválido", "csrf_token": "token-teste"
        })
        self.assertEqual(resposta.status_code, 400)
        self.verificar_sem_alteracoes()

    def test_acesso_e_csrf(self):
        itens = [{"id": "produto-1", "quantidade": 1}]
        self.assertEqual(self.enviar(itens, token="").status_code, 400)
        self.autenticar(1)
        self.assertEqual(self.enviar(itens).status_code, 403)
        self.autenticar(None)
        self.assertEqual(self.enviar(itens).status_code, 401)
        self.verificar_sem_alteracoes()

    def test_confirma_com_token_obtido_pelo_endpoint(self):
        resposta_token = self.cliente.get("/csrf-token")
        self.assertEqual(resposta_token.status_code, 200)
        resposta = self.enviar(
            [{"id": "produto-1", "quantidade": 1}],
            token=resposta_token.get_json()["csrf_token"]
        )
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(len(resposta.get_json()["pedidos"]), 1)
        self.assertEqual(self.consultar("SELECT estoque FROM produtos WHERE id = 1"), [(9,)])

    def test_reverte_todas_empresas_se_baixa_de_estoque_falhar(self):
        with closing(sqlite3.connect(self.banco)) as conexao, conexao:
            conexao.executescript("""
                CREATE TRIGGER impedir_baixa BEFORE UPDATE OF estoque ON produtos
                WHEN OLD.id = 3 BEGIN SELECT RAISE(IGNORE); END;
            """)
        resposta = self.enviar([
            {"id": "produto-1", "quantidade": 1},
            {"id": "produto-3", "quantidade": 1}
        ])
        self.assertEqual(resposta.status_code, 400)
        self.verificar_sem_alteracoes()

    def test_reverte_todas_empresas_em_erro_sql(self):
        with closing(sqlite3.connect(self.banco)) as conexao, conexao:
            conexao.executescript("""
                CREATE TRIGGER falhar_item BEFORE INSERT ON itens_pedido
                WHEN NEW.produto_id = 3 BEGIN SELECT RAISE(ABORT, 'falha de teste'); END;
            """)
        with self.assertLogs(servidor.app.logger, level="ERROR"):
            resposta = self.enviar([
                {"id": "produto-1", "quantidade": 1},
                {"id": "produto-3", "quantidade": 1}
            ])
        self.assertEqual(resposta.status_code, 500)
        self.verificar_sem_alteracoes()


if __name__ == "__main__":
    unittest.main()
