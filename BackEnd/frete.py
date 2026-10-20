"""Regra provisória de frete por faixa de CEP."""

FAIXAS = (
    ("0", "1", "Sudeste", 1500),
    ("2", "3", "Rio/Espírito Santo/Minas", 2000),
    ("4", "5", "Nordeste", 2500),
    ("6", "7", "Norte/Centro-Oeste", 3000),
    ("8", "9", "Sul", 3500),
)


def apenas_digitos(valor):
    return "".join(c for c in (valor or "") if c.isdigit())


def calcular_frete(cep):
    cep = apenas_digitos(cep)
    if len(cep) != 8:
        return None, None
    for inicio, fim, regiao, valor in FAIXAS:
        if inicio <= cep[0] <= fim:
            return valor, regiao
    return None, None


def formatar_endereco(usuario):
    cep = apenas_digitos(usuario["cep"])
    obrigatorios = ("logradouro", "numero_endereco", "bairro", "cidade", "uf")
    if len(cep) != 8 or not all(usuario[campo] for campo in obrigatorios):
        return None
    partes = [f'{usuario["logradouro"]}, {usuario["numero_endereco"]}']
    if usuario["complemento"]:
        partes.append(usuario["complemento"])
    partes += [usuario["bairro"], f'{usuario["cidade"]}/{usuario["uf"]}', f"CEP {cep}"]
    return " - ".join(partes)
