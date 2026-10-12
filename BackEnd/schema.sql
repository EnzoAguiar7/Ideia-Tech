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