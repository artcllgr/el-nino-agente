# -*- coding: utf-8 -*-
"""Compara o facts.json reprocessado no CI com a versao do repositorio.

Uso: python scripts/verificar_reprocessamento.py <facts_original.json> <facts_novo.json>

Falha (exit 1) se a data de confirmacao, o periodo de impacto ou o ranking de
estados mudarem. Diferencas de arredondamento (< 1e-9) sao ignoradas.
"""
import json
import math
import sys


def carregar(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def iguais(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(iguais(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(iguais(x, y) for x, y in zip(a, b))
    return a == b


def main(orig_path, novo_path):
    orig, novo = carregar(orig_path), carregar(novo_path)
    erros = []
    for chave in ("confirmacao", "periodo_impacto", "ranking_estados", "serie_nacional", "n_estacoes", "n_ufs"):
        if not iguais(orig.get(chave), novo.get(chave)):
            erros.append(chave)

    conf = novo["confirmacao"]
    print(f"Estacoes: {novo['n_estacoes']} | UFs: {novo['n_ufs']}")
    print(f"Anomalia confirmada em: {conf.get('mes_confirmacao')} (inicio {conf.get('mes_inicio_sustentado')})")
    print("Top 5 estados:", ", ".join(r["uf"] for r in novo["ranking_estados"][:5]))

    if erros:
        print("ERRO: resultado reprocessado difere do versionado em:", ", ".join(erros))
        return 1
    print("OK: reprocessamento reproduz o facts.json versionado.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
