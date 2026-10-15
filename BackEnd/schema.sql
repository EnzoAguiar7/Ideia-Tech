CREATE TABLE if  NOT EXISTS empresas(
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL UNIQUE,
    nome   TEXT NOT NULL,
    telefone TEXT NOT NULL,
    cnpj TEXT UNIQUE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);
    
CREATE TABLE if NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    telefone TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    versao_sessao INTEGER NOT NULL DEFAULT 0,
    tipo TEXT NOT NULL DEFAULT 'cliente'
    CHECK (tipo IN ('cliente', 'empresa')),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tokens_recuperacao_senha (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expira_em INTEGER NOT NULL,
    usado_em INTEGER,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tokens_recuperacao_usuario
    ON tokens_recuperacao_senha(usuario_id);

CREATE TABLE IF NOT EXISTS tentativas_login (
    id INTEGER PRIMARY KEY,
    escopo TEXT NOT NULL CHECK (escopo IN ('email', 'ip')),
    chave_hash TEXT NOT NULL,
    tentado_em INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tentativas_login_chave_tempo
    ON tentativas_login(escopo, chave_hash, tentado_em);

CREATE TABLE IF NOT EXISTS tentativas_recuperacao (
    id INTEGER PRIMARY KEY,
    escopo TEXT NOT NULL CHECK (escopo IN ('email', 'ip')),
    chave_hash TEXT NOT NULL,
    tentado_em INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tentativas_recuperacao_chave_tempo
    ON tentativas_recuperacao(escopo, chave_hash, tentado_em);


CREATE TABLE IF NOT EXISTS ordens_servico (
    id INTEGER PRIMARY KEY,
    empresa_id INTEGER NOT NULL,
    cliente_id INTEGER NOT NULL,
    aparelho TEXT NOT NULL, 
    problema TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Recebido'
        CHECK(status IN (
            'Recebido',
            'Em diagnóstico',
            'Aguardando aprovação',
            'Em reparo',
            'Pronto para retirada',
            'Entregue'
        )),
        previsao TEXT,
        criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (empresa_id) REFERENCES empresas(id),
        FOREIGN KEY (cliente_id) REFERENCES usuarios(id)
);

CREATE INDEX IF NOT EXISTS idx_ordens_empresa
    ON ordens_servico(empresa_id);

CREATE INDEX IF NOT EXISTS idx_ordens_cliente
    ON ordens_servico(cliente_id);


CREATE TABLE IF NOT EXISTS historico_ordens (
    id INTEGER PRIMARY KEY,
    ordem_id INTEGER NOT NULL, 
    status TEXT NOT NULL, 
    observacao TEXT NOT NULL DEFAULT '',
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ordem_id)
    REFERENCES ordens_servico(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_historico_ordem
    ON historico_ordens(ordem_id);

CREATE TABLE IF NOT EXISTS produtos(
    id INTEGER PRIMARY KEY,
    empresa_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    categoria TEXT NOT NULL,
    preco_centavos INTEGER NOT NULL
        CHECK (preco_centavos > 0),
    estoque INTEGER NOT NULL DEFAULT 0
        CHECK (estoque >=0),
    imagem TEXT,
    ativo INTEGER NOT NULL DEFAULT 1
        CHECK (ativo IN (0, 1)),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id)
);

CREATE INDEX IF NOT EXISTS idx_produtos_empresa
    ON produtos(empresa_id)