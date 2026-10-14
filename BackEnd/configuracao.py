"""Configuração local persistente; variáveis do ambiente têm prioridade."""

import json
import os
import secrets
from pathlib import Path


def carregar_configuracao(pasta=None):
    pasta = Path(pasta) if pasta is not None else Path(__file__).parent
    arquivo = pasta / "config.local.json"

    # Em produção, a configuração precisa ser fornecida explicitamente.
    if not arquivo.exists() and os.environ.get("APP_ENV") != "production":
        configuracao = {
            "IDEIATECH_SECRET_KEY": secrets.token_hex(32),
            "APP_ENV": "development",
            "RECUPERACAO_LOCAL": "1"
        }
        try:
            with arquivo.open("x", encoding="utf-8") as destino:
                json.dump(configuracao, destino, indent=4)
                destino.write("\n")
        except FileExistsError:
            pass

    if not arquivo.exists():
        return

    try:
        configuracao = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise RuntimeError(
            "Não foi possível ler BackEnd/config.local.json. Confira o formato JSON."
        ) from erro

    if not isinstance(configuracao, dict) or not all(
        isinstance(chave, str) and isinstance(valor, str)
        for chave, valor in configuracao.items()
    ):
        raise RuntimeError("config.local.json deve conter nomes e valores de texto.")

    for chave, valor in configuracao.items():
        os.environ.setdefault(chave, valor)
