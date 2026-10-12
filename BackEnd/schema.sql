CREATE TABLE if  NOT EXISTS empresas(
    id INTEGER PRIMARY KEY,
    nome   TEXT NOT NULL,
    telefone TEXT NOT NULL,
    cnpj TEXT UNIQUE
);
    
CREATE TABLE if NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    telefone TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE if NOT EXISTS empresa_usuarios (
    empresa_id INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL,
    papel TEXT NOT NULL CHECK(
        papel IN ('administrador', 'gerente', 'tecnico', 'cliente')
    ),
    PRIMARY KEY (empresa_id, usuario_id),
    FOREIGN KEY(empresa_id) REFERENCES empresas(id),
    FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
);

CREATE TABLE if NOT EXISTS recuperacao_senha (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL, 
    token_hash TEXT NOT NULL UNIQUE,
    expira_em INTEGER NOT NULL,
    usado INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);