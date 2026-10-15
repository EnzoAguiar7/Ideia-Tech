import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as servidor


class DadosEmpresaTest(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.banco = Path(self.temporario.name) / "teste.db"
        self.patch_banco = patch.object(servidor, "caminho_banco", self.banco)
        self.patch_banco.start()
        self.addCleanup(self.temporario.cleanup)
        self.addCleanup(self.patch_banco.stop)
        with closing(sqlite3.connect(self.banco)) as conexao, conexao:
            conexao.executescript(
                (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
            )
            conexao.executemany(
                "INSERT INTO usuarios (id, nome, email, telefone, senha_hash, tipo) VALUES (?, ?, ?, ?, ?, ?)",
                [(1, "Responsável A", "a@example.com", "111", "hash", "empresa"),
                 (2, "Responsável B", "b@example.com", "222", "hash", "empresa"),
                 (3, "Cliente", "c@example.com", "333", "hash", "cliente"),
                 (4, "Sem vínculo", "d@example.com", "444", "hash", "empresa")]
            )
            conexao.executemany(
                "INSERT INTO empresas (usuario_id, nome, telefone, cnpj) VALUES (?, ?, ?, ?)",
                [(1, "Assistência A", "111", "111"), (2, "Assistência B", "222", "222")]
            )
        self.cliente = servidor.app.test_client()

    def autenticar(self, usuario_id=1):
        with self.cliente.session_transaction() as sessao:
            sessao["usuario_id"] = usuario_id
            sessao["versao_sessao"] = 0
            sessao["csrf_token"] = "token-teste"

    def enviar(self, **alteracoes):
        dados = dict(nomeEmpresa="Empresa atualizada", nomeResponsavel="Novo responsável",
                     telefone="11999999999", cnpj="", csrf_token="token-teste")
        dados.update(alteracoes)
        return self.cliente.post("/Pages/Empresa/dadosEmpresa.html", data=dados)

    def consultar(self, tabela, usuario_id=1):
        with closing(sqlite3.connect(self.banco)) as conexao:
            conexao.row_factory = sqlite3.Row
            coluna = "id" if tabela == "usuarios" else "usuario_id"
            return dict(conexao.execute(f"SELECT * FROM {tabela} WHERE {coluna} = ?", (usuario_id,)).fetchone())

    def test_acesso_restrito(self):
        resposta = self.cliente.get("/Pages/Empresa/dadosEmpresa.html")
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/Pages/login.html?next=", resposta.location)
        self.autenticar(3)
        self.assertEqual(self.cliente.get("/Pages/Empresa/dadosEmpresa.html").status_code, 403)

    def test_carrega_apenas_empresa_autenticada(self):
        self.autenticar()
        resposta = self.cliente.get("/Pages/Empresa/dadosEmpresa.html")
        html = resposta.get_data(as_text=True)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.headers["Cache-Control"], "no-store")
        self.assertIn("Assistência A", html)
        self.assertIn("a@example.com", html)
        self.assertNotIn("Assistência B", html)
        self.assertNotIn("{{", html)

    def test_salva_somente_conta_atual_e_exibe_confirmacao(self):
        self.autenticar()
        resposta = self.enviar(usuario_id="2", email="intruso@example.com")
        self.assertEqual(resposta.status_code, 302)
        empresa = self.consultar("empresas")
        usuario = self.consultar("usuarios")
        self.assertEqual(empresa["nome"], "Empresa atualizada")
        self.assertIsNone(empresa["cnpj"])
        self.assertEqual(usuario["telefone"], empresa["telefone"])
        self.assertEqual(usuario["nome"], "Novo responsável")
        self.assertEqual(usuario["email"], "a@example.com")
        self.assertEqual(self.consultar("empresas", 2)["nome"], "Assistência B")
        self.assertIn("atualizados com sucesso", self.cliente.get(resposta.location).get_data(as_text=True))

    def test_rejeita_dados_invalidos_sem_perder_valores_digitados(self):
        self.autenticar()
        for campo, valor in [("nomeEmpresa", "X"), ("nomeResponsavel", ""),
                             ("telefone", ""), ("cnpj", "1" * 19)]:
            with self.subTest(campo=campo):
                resposta = self.enviar(**{campo: valor})
                self.assertEqual(resposta.status_code, 400)
                self.assertIn('role="alert"', resposta.get_data(as_text=True))
                self.assertEqual(self.consultar("empresas")["nome"], "Assistência A")
        resposta = self.enviar(nomeEmpresa='<script>alert("x")</script>', telefone="")
        self.assertIn("&lt;script&gt;", resposta.get_data(as_text=True))

    def test_cnpj_duplicado_nao_altera_responsavel(self):
        self.autenticar()
        self.assertEqual(self.enviar(cnpj="222").status_code, 409)
        self.assertEqual(self.consultar("empresas")["nome"], "Assistência A")
        self.assertEqual(self.consultar("usuarios")["nome"], "Responsável A")

    def test_csrf_obrigatorio(self):
        self.autenticar()
        self.assertEqual(self.enviar(csrf_token="").status_code, 400)
        self.assertEqual(self.consultar("empresas")["nome"], "Assistência A")

    def test_conta_sem_vinculo_nao_recebe_dados_de_outra_empresa(self):
        self.autenticar(4)
        self.assertEqual(self.cliente.get("/Pages/Empresa/dadosEmpresa.html").status_code, 404)


if __name__ == "__main__":
    unittest.main()
