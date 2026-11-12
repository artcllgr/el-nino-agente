# -*- coding: utf-8 -*-
"""
Agente El Nino - Streamlit (100% offline, sem API key)
======================================================
Consome saida/facts.json (gerado por analise_el_nino.py) e responde
duvidas sobre: quando a anomalia foi confirmada, estados mais impactados,
impactos por regiao e orientacoes de saude/protecao.

Rodar:  streamlit run app_el_nino.py
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st

BASE = Path(__file__).resolve().parent
FACTS = BASE / "saida" / "facts.json"
# Gerado pelo workflow de deploy (GitHub Actions) com o commit e a data da publicacao
VERSION_FILE = BASE / "version.json"

# --------------------------------------------------------------------------- #
# Base de conhecimento (curada) - orientacoes e contexto
# --------------------------------------------------------------------------- #
FONTE_OFICIAL = "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/e/el-nino"

KB_IMPACTOS = {
    "S": "Chuvas muito acima da media, temporais frequentes e risco elevado de enchentes e alagamentos.",
    "N": "Aumento da seca e estiagem severa, com elevacao do risco de queimadas na Amazonia.",
    "NE": "Seca e estiagem severa, com reducao das chuvas e aumento do risco de queimadas e crise hidrica.",
    "CO": "Ocorrencia de ondas de calor e maior variabilidade nos volumes de chuva.",
    "SE": "Ondas de calor e maior variabilidade nos volumes de chuva.",
}

KB_REGIAO_NOME = {
    "N": "Norte", "NE": "Nordeste", "CO": "Centro-Oeste", "SE": "Sudeste", "S": "Sul",
}

KB_SAUDE_CALOR = (
    "**Ondas de calor / estresse termico**\n"
    "- Beba agua com frequencia, mesmo sem sede; evite bebidas alcoolicas e muito acucaradas.\n"
    "- Evite exposicao ao sol entre 10h e 16h; use roupas leves e protetor solar.\n"
    "- Atencao redobrada com idosos, criancas, gestantes e pessoas com doencas cronicas.\n"
    "- Sinais de alerta de insolacao/desidratacao: tontura, nausea, dor de cabeca intensa, "
    "pele quente e seca, confusao mental, desmaio. Procure atendimento imediatamente."
)

KB_SECA = (
    "**Seca / estiagem e queimadas**\n"
    "- Economize agua e evite desperdicio; priorize o consumo humano.\n"
    "- Nao faca queimadas; mantenha terrenos limpos e evite fogueiras perto de vegetacao.\n"
    "- Cuide da qualidade do ar: em dias com fumaca, feche janelas, use mascara se necessario "
    "e hidrate as vias respiratorias; procure atendimento se houver falta de ar.\n"
    "- Atencao a sinais de desidratacao e ao consumo de agua de fontes seguras."
)

KB_CHUVA = (
    "**Chuvas intensas / enchentes**\n"
    "- Nao atravesse areas alagadas a pe ou de carro; a agua pode esconder buracos e correnteza.\n"
    "- Afaste-se de encostas e margens de rios em caso de chuva forte e continua.\n"
    "- Prepare um kit de emergencia (agua, alimentos, documentos, lanternas, medicamentos).\n"
    "- Siga os alertas da Defesa Civil do seu municipio e evacue quando orientado."
)

EMERGENCIAS = "Emergencias: **Defesa Civil 199** | **SAMU 192** | **Bombeiros 193**."

AVISO_FONTE = (
    "A \"anomalia confirmada\" deste agente e o sinal de calor medido nas estacoes "
    "automaticas do INMET em relacao ao proprio periodo 2024-2026. A confirmacao oficial "
    "do El Nino vem do monitoramento do Oceano Pacifico (indice ONI / Nino 3.4), "
    "divulgado por INMET, CPTEC/INPE e NOAA."
)

# Palavras-chave de cada regiao (comparadas por palavra inteira, para que
# "consultar" nao seja confundido com "sul", por exemplo)
REGIAO_TOKENS = {
    "S": ["sul", "parana", "santa catarina", "rio grande do sul"],
    "NE": ["nordeste", "nordestino"],
    "N": ["norte", "amazonia", "amazonas"],
    "CO": ["centro-oeste", "centro oeste"],
    "SE": ["sudeste"],
}

UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapa", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceara", "DF": "Distrito Federal", "ES": "Espirito Santo", "GO": "Goias",
    "MA": "Maranhao", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Para", "PB": "Paraiba", "PR": "Parana", "PE": "Pernambuco", "PI": "Piaui",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
    "RO": "Rondonia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "Sao Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}
NOME_TO_UF = {v.lower(): k for k, v in UF_NOME.items()}
NOME_TO_UF.update({"paraiba": "PB", "piaui": "PI", "ceara": "CE", "goias": "GO",
                   "espirito santo": "ES", "rio grande do sul": "RS", "rio de janeiro": "RJ",
                   "sao paulo": "SP", "minas gerais": "MG", "mato grosso": "MT",
                   "mato grosso do sul": "MS", "distrito federal": "DF"})
# "para" (preposicao) colide com o estado Para; so casa se vier em MAIUSCULO via UFS_RE
NOME_TO_UF.pop("para", None)

# Codigos de UF em MAIUSCULO (ex.: "RS", "SP") para evitar colisoes com palavras comuns ("se", "to")
UFS_RE = re.compile(r"\b(" + "|".join(UF_NOME.keys()) + r")\b")


def _norm(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt.lower())
    return "".join(c for c in txt if not unicodedata.combining(c))


def _palavras(txt: str) -> set[str]:
    return set(re.findall(r"[a-z]+", _norm(txt)))


def _tem_termo(q: str, termo: str) -> bool:
    """True se `termo` aparece em `q` como palavra(s) inteira(s)."""
    return re.search(r"(?<![a-z])" + re.escape(termo) + r"(?![a-z])", q) is not None


def carregar_versao(path: Path = VERSION_FILE) -> dict:
    """Versao publicada: lida do version.json escrito pelo workflow de deploy.
    Sem o arquivo (execucao local), devolve 'local'."""
    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
        return {
            "versao": str(dados.get("versao", "local")),
            "commit": str(dados.get("commit", ""))[:7],
            "data_deploy": str(dados.get("data_deploy", "")),
        }
    except (OSError, ValueError):
        return {"versao": "local", "commit": "", "data_deploy": ""}


# --------------------------------------------------------------------------- #
# Carregamento dos fatos
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def carregar_fatos(path_str: str):
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Motor do agente (regras + recuperacao sobre os fatos calculados)
# --------------------------------------------------------------------------- #
def responder(pergunta: str, f: dict) -> str:
    q = _norm(pergunta)
    ranking = f["ranking_estados"]
    conf = f["confirmacao"]

    # localizar UF citada (codigo em MAIUSCULO, ex.: "RS"; ou nome completo, com limite de palavra)
    uf_citada = None
    m_uf = UFS_RE.search(pergunta)
    if m_uf:
        uf_citada = m_uf.group(1)
    if not uf_citada:
        for nome, cod in NOME_TO_UF.items():
            if re.search(r"(?<![a-z])" + re.escape(nome) + r"(?![a-z])", q):
                uf_citada = cod
                break

    # localizar regiao citada
    regiao_citada = None
    for key, tokens in REGIAO_TOKENS.items():
        if any(_tem_termo(q, t) for t in tokens):
            regiao_citada = key
            break

    # saudações / ajuda (comparacao por palavra, para nao casar com "foi", "coisa", etc.)
    palavras = _palavras(pergunta)
    if palavra_greeting := (palavras & {"oi", "ola", "help", "ajuda"}):
        return (
            "Ola! Sou o agente do El Nino. Posso responder sobre:\n"
            "- **Quando** a anomalia foi confirmada;\n"
            "- **Quais estados** serao mais impactados (e por que);\n"
            "- **Impactos por regiao** (chuva, seca, calor);\n"
            "- **Orientacoes** de saude e protecao (calor, seca, enchentes).\n\n"
            "Experimente: *\"Quando a anomalia foi confirmada?\"* ou *\"Quais estados mais impactados?\"*"
        )
    if any(t in q for t in ["bom dia", "boa tarde", "boa noite"]):
        return (
            "Ola! Sou o agente do El Nino. Posso responder sobre:\n"
            "- **Quando** a anomalia foi confirmada;\n"
            "- **Quais estados** serao mais impactados (e por que);\n"
            "- **Impactos por regiao** (chuva, seca, calor);\n"
            "- **Orientacoes** de saude e protecao (calor, seca, enchentes).\n\n"
            "Experimente: *\"Quando a anomalia foi confirmada?\"* ou *\"Quais estados mais impactados?\"*"
        )

    # "o que e El Nino?" / "explica o El Nino" (antes, "o que e" casava com "o que eu devo fazer...")
    pergunta_conceito = _tem_termo(q, "o que e") or _tem_termo(q, "o que significa") or "explica" in q
    if pergunta_conceito and "nino" in q:
        return (
            "**El Nino** e um fenomeno climatico natural caracterizado pelo aquecimento anormal das "
            "aguas superficiais do Oceano Pacifico Equatorial. Ele enfraquece os ventos alisios e "
            "altera a circulacao atmosferica global, modificando os padroes de chuva e temperatura.\n\n"
            "No Brasil: chuvas acima da media no **Sul**, seca no **Norte/Nordeste** e ondas de calor "
            "com chuva irregular no **Sudeste/Centro-Oeste**."
        )

    # pergunta sobre um estado especifico
    if uf_citada:
        item = next((r for r in ranking if r["uf"] == uf_citada), None)
        if item:
            return _ficha_estado(item, f)
        # UF sem estacoes com dados no periodo de impacto (ex.: RR, cuja unica estacao
        # parou de transmitir em 2025-10): explicar em vez de cair no resumo generico
        return (
            f"**{uf_citada} - {UF_NOME.get(uf_citada, '')}**: nao ha estacoes do INMET com dados "
            f"no periodo de impacto ({f.get('periodo_impacto_label', '-')}), por isso o estado "
            "nao entra no ranking.\n\n"
            f"Consulte os boletins oficiais: {FONTE_OFICIAL}\n\n{EMERGENCIAS}"
        )

    # quando confirmada
    if any(t in q for t in ["quando", "confirmad", "data", "inicio", "comecou", "detectad"]):
        if conf.get("confirmado"):
            det = conf.get("detalhe_regional", {})
            nomes = {"CO": "Centro-Oeste", "S": "Sul", "SE": "Sudeste", "N": "Norte", "NE": "Nordeste"}
            linhas = "\n".join(
                f"- {nomes[r]}: temp {det[r]['temp_z']:+.2f}\u03c3, chuva {det[r]['precip_z']:+.2f}\u03c3"
                for r in ["CO", "S", "SE", "N", "NE"] if r in det
            )
            return (
                f"A anomalia foi **confirmada em {conf['mes_confirmacao']}**, com in\u00edcio do "
                f"aquecimento em {conf.get('mes_inicio_sustentado','-')}.\n\n"
                f"Nesse m\u00eas, **{conf['frac_quente']*100:.0f}%** das {conf['n_estacoes']} esta\u00e7\u00f5es "
                f"apresentaram anomalia de temperatura z \u2265 {f['z_calor_conf']} "
                f"(z m\u00e9dio nacional = {conf['temp_z']:+.2f}\u03c3).\n\n"
                f"Crit\u00e9rio: `{conf.get('criterio','')}` (amplo e forte).\n\n"
                f"**Assinatura regional na janela** ({', '.join(conf.get('meses_janela', []))}):\n{linhas}"
            )
        return f"Ainda nao houve sinal sustentado no periodo analisado. {conf.get('motivo','')}"

    # regiao especifica (antes do ranking generico, p/ "quais impactos no Nordeste?" etc.)
    if regiao_citada:
        return _ficha_regiao(regiao_citada, ranking, f)

    # estados mais impactados
    if any(t in q for t in ["estado", "uf", "impactad", "afetad", "ranking", "onde", "quais"]):
        top = ranking[:8]
        linhas = "\n".join(
            f"{r['ranking']}. **{r['uf']}** ({r['regiao_nome']}) - indice {r['indice_impacto']:.2f} "
            f"| calor z={r['calor_z']:.2f}, seca z={r['seca_z']:.2f}, chuva z={r['chuva_z']:.2f}"
            for r in top
        )
        return (
            f"Estados mais impactados ({f.get('periodo_impacto_label', '-')}), "
            f"pelo indice region-aware:\n\n{linhas}\n\n{EMERGENCIAS}"
        )

    # temas de orientacao
    if any(t in q for t in ["calor", "onda de calor", "temperatura alta", "insolacao", "estresse termico"]):
        return KB_SAUDE_CALOR + "\n\n" + EMERGENCIAS
    if any(t in q for t in ["seca", "estiagem", "queimada", "fumaca", "ar seco"]):
        return KB_SECA + "\n\n" + EMERGENCIAS
    if any(t in q for t in ["chuva", "enchente", "alagamento", "temporal", "inundac"]):
        return KB_CHUVA + "\n\n" + EMERGENCIAS
    if any(t in q for t in ["saude", "cuidado", "prevenc", "orientac", "hidrat", "protecao"]):
        return KB_SAUDE_CALOR + "\n\n" + KB_SECA + "\n\n" + KB_CHUVA
    if any(t in q for t in ["oficial", "gov", "portal", "ministerio", "link", "fonte"]):
        return f"Orientacoes oficiais de saude e avisos de calor extremo: **Portal Gov.br - El Nino**\n{FONTE_OFICIAL}"
    if any(t in q for t in ["dado", "estatistic", "metodolog", "z-score", "amostra", "quantas estac"]):
        return (
            f"Foram analisadas **{f['n_estacoes']} estacoes** automaticas do INMET em **{f['n_ufs']} UFs**, "
            f"no periodo de {f['periodo_dados']['min']} a {f['periodo_dados']['max']} "
            f"({f['n_observacoes_mensais']:,} observacoes mensais).\n\n"
            f"Metodo: z-score interno (anomalia em relacao a climatologia do mes-do-ano, dividida "
            f"pelo desvio-padrao da propria estacao). Limiar de anomalia: |z| >= {f['z_limiar']}."
        )

    # fallback inteligente: resumo geral
    top3 = ", ".join(r["uf"] for r in ranking[:3])
    return (
        "Nao entendi exatamente a pergunta, mas aqui vai um resumo:\n\n"
        f"- Anomalia confirmada em **{conf.get('mes_confirmacao','-')}** "
        f"({conf.get('frac_quente',0)*100:.0f}% das estacoes com calor anomalo).\n"
        f"- Estados mais impactados: **{top3}**.\n"
        f"- Padrao: chuva no Sul, seca no Norte/Nordeste, calor no Sudeste/Centro-Oeste.\n\n"
        "Pergunte, por exemplo: *\"E no Rio Grande do Sul?\"*, *\"orientacoes para onda de calor\"* "
        f"ou *\"quando foi confirmada?\"*. {EMERGENCIAS}"
    )


def _ficha_estado(item: dict, f: dict) -> str:
    reg = item["regiao"]
    return (
        f"**{item['uf']} - {UF_NOME.get(item['uf'], '')} ({item['regiao_nome']})**\n\n"
        f"- Indice de impacto ({f.get('periodo_impacto_label', '-')}): "
        f"**{item['indice_impacto']:.2f}** (ranking #{item['ranking']}).\n"
        f"- Anomalia de calor (z medio): {item['calor_z']:.2f} | seca: {item['seca_z']:.2f} "
        f"| chuva: {item['chuva_z']:.2f}.\n"
        f"- Meses com calor anomalo: {item['perc_meses_quentes']:.0f}% | "
        f"dias com Tmax >= 35C: {item['dias_calor_extremo']}.\n"
        f"- Estacoes analisadas: {item['n_estacoes']}.\n\n"
        f"**Impacto esperado:** {KB_IMPACTOS[reg]}\n\n"
        f"**Orientacoes:** veja a aba *Orientacoes* ou pergunte sobre calor, seca ou chuva.\n\n{EMERGENCIAS}"
    )


def _ficha_regiao(reg: str, ranking: list[dict], f: dict) -> str:
    estados = [r for r in ranking if r["regiao"] == reg]
    lista = ", ".join(f"{r['uf']} ({r['indice_impacto']:.2f})" for r in estados[:8])
    return (
        f"**Regiao {KB_REGIAO_NOME[reg]}**\n\n"
        f"- Impacto esperado: {KB_IMPACTOS[reg]}\n"
        f"- Estados da regiao no ranking: {lista}.\n\n"
        f"**Orientacoes:** "
        + (KB_CHUVA if reg == "S" else KB_SECA if reg in ("N", "NE") else KB_SAUDE_CALOR)
        + f"\n\n{EMERGENCIAS}"
    )


# --------------------------------------------------------------------------- #
# Interface
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="Agente El Nino", page_icon="🌡️", layout="wide")
    st.title("🌡️ Agente El Nino")
    st.caption(
        "Solucao CitizenTech: analise das estacoes automaticas do INMET (2024-2026) "
        "e orientacoes de protecao ao cidadao."
    )

    if not FACTS.exists():
        st.error("Arquivo saida/facts.json nao encontrado. Rode `python analise_el_nino.py` primeiro.")
        st.stop()

    f = carregar_fatos(str(FACTS))
    conf = f["confirmacao"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estacoes", f["n_estacoes"])
    c2.metric("Estados (UFs)", f["n_ufs"])
    c3.metric("Anomalia confirmada", conf.get("mes_confirmacao", "n/a") if conf.get("confirmado") else "nao")
    c4.metric("Limiar z-score", f["z_limiar"])

    aba_agente, aba_painel, aba_orient = st.tabs(["💬 Agente", "📊 Painel de dados", "🛡️ Orientacoes"])

    with aba_agente:
        if "chat" not in st.session_state:
            st.session_state.chat = [
                {"role": "assistant", "content": (
                    "Ola! Sou o agente do El Nino. Pergunte sobre quando a anomalia foi confirmada, "
                    "quais estados serao mais impactados, ou peca orientacoes (calor, seca, enchentes)."
                )}
            ]

        sugestoes = [
            "Quando a anomalia foi confirmada?",
            "Quais estados serao mais impactados?",
            "E no Rio Grande do Sul?",
            "Orientacoes para onda de calor",
        ]
        cols = st.columns(len(sugestoes))
        for col, s in zip(cols, sugestoes):
            if col.button(s, use_container_width=True):
                st.session_state.chat.append({"role": "user", "content": s})
                st.session_state.chat.append({"role": "assistant", "content": responder(s, f)})

        st.caption(AVISO_FONTE + f" Fonte oficial de orientacoes: {FONTE_OFICIAL}")

        for msg in st.session_state.chat:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if pergunta := st.chat_input("Digite sua duvida sobre o El Nino..."):
            st.session_state.chat.append({"role": "user", "content": pergunta})
            with st.chat_message("user"):
                st.markdown(pergunta)
            with st.chat_message("assistant"):
                st.markdown(responder(pergunta, f))

    with aba_painel:
        st.subheader(f"Ranking de estados mais impactados ({f.get('periodo_impacto_label', '-')})")
        df = pd.DataFrame(f["ranking_estados"])
        st.dataframe(
            df[["ranking", "uf", "regiao_nome", "indice_impacto", "calor_z", "seca_z",
                "chuva_z", "perc_meses_quentes", "dias_calor_extremo", "n_estacoes"]],
            use_container_width=True, hide_index=True,
        )
        st.subheader("Evolucao mensal (anomalias nacionais)")
        serie = pd.DataFrame(f["serie_nacional"]).set_index("mes_str")
        st.line_chart(serie[["temp_z", "precip_z"]])
        st.bar_chart(serie[["frac_quente"]].rename(columns={"frac_quente": "% estacoes quentes"}))

    with aba_orient:
        st.subheader("Orientacoes de protecao")
        st.markdown(KB_SAUDE_CALOR)
        st.markdown(KB_SECA)
        st.markdown(KB_CHUVA)
        st.markdown(EMERGENCIAS)
        st.markdown(
            f"Fonte oficial: [Portal Gov.br - El Nino]({FONTE_OFICIAL})"
        )
        st.info(
            "Este agente usa dados do INMET e orientacoes gerais de saude/protecao. "
            "Nao substitui boletins oficiais de monitoramento (INMET, ANA, CPTEC/INPE, Defesa Civil)."
        )

    # Rodape com a versao publicada: comprova que o deploy automatizado atualizou o app
    v = carregar_versao()
    if v["versao"] == "local":
        st.caption("Versao: local (execucao fora do Azure)")
    else:
        st.caption(
            f"Versao {v['versao']} | commit {v['commit']} | publicado em {v['data_deploy']} "
            "via GitHub Actions -> Azure App Service"
        )


if __name__ == "__main__":
    main()
