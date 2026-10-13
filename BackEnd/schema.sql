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
