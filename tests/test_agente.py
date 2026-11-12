# -*- coding: utf-8 -*-
"""Testes do motor do agente (app_el_nino.responder) usando o facts.json real."""
import json
from pathlib import Path

import pytest

import app_el_nino as app

FACTS = Path(__file__).resolve().parent.parent / "saida" / "facts.json"


@pytest.fixture(scope="module")
def fatos():
    return json.loads(FACTS.read_text(encoding="utf-8"))


def test_confirmacao_informa_mes_e_criterio(fatos):
    resp = app.responder("Quando a anomalia foi confirmada?", fatos)
    assert fatos["confirmacao"]["mes_confirmacao"] in resp
    assert "Crit" in resp


def test_estados_mais_impactados_lista_top_do_ranking(fatos):
    resp = app.responder("Quais estados serao mais impactados?", fatos)
    for item in fatos["ranking_estados"][:3]:
        assert f"**{item['uf']}**" in resp
    assert fatos["periodo_impacto_label"] in resp


def test_pergunta_por_estado_pelo_nome(fatos):
    resp = app.responder("E no Rio Grande do Sul?", fatos)
    assert "RS - Rio Grande do Sul" in resp
    assert "enchentes" in resp  # impacto esperado para o Sul


def test_pergunta_por_estado_pela_sigla(fatos):
    resp = app.responder("Como esta o PE?", fatos)
    assert "PE - Pernambuco" in resp


def test_estado_sem_dados_no_periodo(fatos):
    resp = app.responder("E em Roraima?", fatos)
    assert "RR - Roraima" in resp
    assert "nao ha estacoes" in resp


def test_o_que_e_el_nino(fatos):
    resp = app.responder("O que é o El Niño?", fatos)
    assert "Pacifico Equatorial" in resp


def test_o_que_eu_devo_fazer_nao_vira_definicao(fatos):
    # Regressao: "o que e" casava com "o que eu devo fazer..."
    resp = app.responder("O que eu devo fazer numa onda de calor?", fatos)
    assert "Pacifico Equatorial" not in resp
    assert "Beba agua" in resp


def test_consultar_nao_e_confundido_com_regiao_sul(fatos):
    # Regressao: "consultar" contem "sul" e caia na ficha da Regiao Sul
    resp = app.responder("Quero consultar os estados mais afetados", fatos)
    assert "Regiao Sul" not in resp
    assert "Estados mais impactados" in resp


def test_regiao_nordeste(fatos):
    resp = app.responder("Quais os impactos no Nordeste?", fatos)
    assert "Regiao Nordeste" in resp
    assert "Seca" in resp


@pytest.mark.parametrize(
    "pergunta, trecho",
    [
        ("orientacoes para seca", "Economize agua"),
        ("tem risco de enchente?", "areas alagadas"),
        ("qual o link oficial?", app.FONTE_OFICIAL),
    ],
)
def test_orientacoes(fatos, pergunta, trecho):
    assert trecho in app.responder(pergunta, fatos)


def test_pergunta_desconhecida_devolve_resumo(fatos):
    resp = app.responder("xyz", fatos)
    assert "resumo" in resp
    assert fatos["ranking_estados"][0]["uf"] in resp


def test_versao_local_sem_arquivo(tmp_path):
    assert app.carregar_versao(tmp_path / "nao_existe.json")["versao"] == "local"


def test_versao_lida_do_arquivo_de_deploy(tmp_path):
    arq = tmp_path / "version.json"
    arq.write_text(
        json.dumps({"versao": "42", "commit": "abcdef1234567", "data_deploy": "2026-11-12 20:00 UTC"}),
        encoding="utf-8",
    )
    v = app.carregar_versao(arq)
    assert v == {"versao": "42", "commit": "abcdef1", "data_deploy": "2026-11-12 20:00 UTC"}
