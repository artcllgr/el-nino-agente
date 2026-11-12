# -*- coding: utf-8 -*-
"""Testes das funcoes de analise (analise_el_nino) com dados sinteticos
e verificacoes de consistencia do facts.json versionado."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import analise_el_nino as an

FACTS = Path(__file__).resolve().parent.parent / "saida" / "facts.json"


def _serie_estacao(chave, regiao, uf, temps, precs):
    meses = pd.period_range("2025-01", periods=len(temps), freq="M")
    return pd.DataFrame(
        {
            "chave": chave, "regiao": regiao, "uf": uf,
            "mes_str": meses.astype(str), "mes_num": meses.month, "ano": meses.year,
            "temp": temps, "tmax": np.array(temps) + 6, "tmin": np.array(temps) - 6,
            "precip": precs, "rh": 70.0, "hot_days": 0, "heavy_rain": 0,
        }
    )


def test_calcular_anomalias_remove_sazonalidade():
    # mesma temperatura em todos os anos -> anomalia zero em todos os meses
    temps = [20.0, 22.0, 25.0] * 4
    df = _serie_estacao("CO_DF_A001_X", "CO", "DF", temps, [100.0] * 12)
    df["mes_num"] = [1, 2, 3] * 4
    out = an.calcular_anomalias(df)
    assert np.allclose(out["temp_anom"], 0.0)


def test_calcular_anomalias_detecta_mes_quente():
    temps = [20.0] * 11 + [26.0]
    df = _serie_estacao("CO_DF_A001_X", "CO", "DF", temps, [100.0] * 12)
    df["mes_num"] = 1  # todos comparados com a mesma climatologia
    out = an.calcular_anomalias(df)
    assert out["temp_z"].iloc[-1] > an.Z_LIMIAR
    assert out["temp_z"].iloc[-1] == out["temp_z"].max()


def _nacional(temp_z, frac):
    meses = pd.period_range("2026-01", periods=len(temp_z), freq="M")
    return pd.DataFrame(
        {"mes_str": meses.astype(str), "ano": meses.year, "temp_z": temp_z,
         "frac_calor_1": frac, "n_est": 100}
    )


def _anom_vazia(meses):
    return pd.DataFrame({"mes_str": meses, "regiao": "CO", "temp_z": 1.0, "precip_z": 0.0})


def test_detectar_confirmacao_primeiro_mes_que_atende_criterio():
    nac = _nacional([-0.5, 0.4, 0.8, 1.2, 1.3], [0.0, 0.1, 0.3, 0.5, 0.6])
    conf = an.detectar_confirmacao(nac, _anom_vazia(list(nac["mes_str"])))
    assert conf["confirmado"] is True
    assert conf["mes_confirmacao"] == "2026-04"
    # inicio recua enquanto o mes anterior tem temp_z > 0,3
    assert conf["mes_inicio_sustentado"] == "2026-02"


def test_detectar_confirmacao_sem_sinal():
    nac = _nacional([0.2, 1.5, 0.1], [0.1, 0.2, 0.1])  # forte, mas nao amplo
    conf = an.detectar_confirmacao(nac, _anom_vazia(list(nac["mes_str"])))
    assert conf["confirmado"] is False


def test_ranquear_estados_respeita_perfil_regional():
    # Sul com excesso de chuva deve pontuar acima do Sul com seca
    umido = _serie_estacao("S_RS_A1_X", "S", "RS", [20.0] * 3, [300.0] * 3)
    seco = _serie_estacao("S_SC_A2_Y", "S", "SC", [20.0] * 3, [10.0] * 3)
    df = pd.concat([umido, seco], ignore_index=True)
    df["temp_z"] = 0.0
    df["precip_z"] = np.where(df["uf"] == "RS", 2.0, -2.0)
    ranking = an.ranquear_estados(df, list(df["mes_str"].unique()))
    assert [r["uf"] for r in ranking] == ["RS", "SC"]
    assert ranking[0]["ranking"] == 1


def test_facts_json_consistente():
    f = json.loads(FACTS.read_text(encoding="utf-8"))
    assert f["n_ufs"] == 27
    conf = f["confirmacao"]
    assert conf["confirmado"] is True
    assert conf["mes_confirmacao"] in f["periodo_impacto"]
    indices = [r["indice_impacto"] for r in f["ranking_estados"]]
    assert indices == sorted(indices, reverse=True)
    ufs = [r["uf"] for r in f["ranking_estados"]]
    assert len(ufs) == len(set(ufs))  # cada UF aparece uma vez
    # RR fica de fora: sua unica estacao nao tem dados no periodo de impacto
    assert "RR" not in ufs and len(ufs) == 26
