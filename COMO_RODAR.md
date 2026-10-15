# Rodar o IdeiaTech no Windows

Execute os comandos na raiz do projeto, onde ficam Pages e BackEnd.
É necessário ter Python instalado (`py --version`).

## Primeira vez em cada computador

Crie um ambiente Python e instale as dependências:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Se este computador ainda não possui o banco local, crie as tabelas:

```powershell
.\.venv\Scripts\python.exe BackEnd/banco.py
```

Cada computador terá seu próprio banco, inicialmente sem contas cadastradas.
O banco não é enviado ao GitHub.

## Sempre que quiser iniciar

```powershell
.\.venv\Scripts\python.exe BackEnd/app.py
```

Abra http://127.0.0.1:5000. Para parar, pressione Ctrl+C.
Não é necessário ativar o ambiente virtual nem usar Live Server.
Se Flask já estiver instalado no Python utilizado pelo comando `py`,
também é possível usar `py BackEnd/app.py`.

Na primeira execução local, o aplicativo cria automaticamente
`BackEnd/config.local.json`, com uma chave secreta persistente e
`RECUPERACAO_LOCAL=1`. Nesse modo, os links de recuperação aparecem
no terminal; nenhum e-mail é enviado. O arquivo é ignorado pelo Git.
Variáveis já definidas no ambiente têm prioridade sobre esse arquivo.

## Banco antigo

A configuração de inicialização não migra o banco automaticamente.
Execute `.\.venv\Scripts\python.exe BackEnd/banco.py` para adicionar as
colunas `usuarios.versao_sessao`, `usuarios.tipo` e `empresas.usuario_id`
que estiverem faltando, preservando os registros existentes. O comando
pode ser executado novamente sem duplicar as colunas.

Empresas antigas sem `usuario_id` continuam sem vínculo de acesso.
Esse vínculo precisa ser definido para a conta correta; a migração não
associa empresas automaticamente a usuários existentes.

## Dados da empresa

Após entrar com uma conta empresarial, abra **Dados da empresa** no menu.
A página carrega o cadastro da conta autenticada e permite atualizar o
nome da empresa, CNPJ opcional, telefone e nome do responsável. O e-mail
de acesso permanece somente para consulta.

## Erros comuns

- `No module named flask`: execute a instalação das dependências e use
  o Python da `.venv` indicado acima.
- `no such table`: em um banco novo, execute BackEnd/banco.py.
- `no such column`: o banco está desatualizado e precisa de migração.
- Porta 5000 em uso: pare o outro servidor Flask antes de iniciar outro.
- `config.local.json` inválido: confira vírgulas e aspas; os valores
  devem ser textos entre aspas duplas.

## Produção

Em produção, configure `APP_ENV=production`, `RECUPERACAO_LOCAL=0`,
uma `IDEIATECH_SECRET_KEY` persistente, `PUBLIC_BASE_URL` com HTTPS e
as variáveis SMTP. A chave não é gerada automaticamente em produção.
O comando app.py acima é para desenvolvimento local; o deploy terá
sua própria configuração de servidor.
