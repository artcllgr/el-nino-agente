# Agente El Niño – CitizenTech

**Problema:** o El Niño 2026/2027 traz calor, seca e enchentes para o Brasil, e o cidadão não sabe se o fenômeno já chegou, se o seu estado será afetado e como se proteger.

**Proposta:** analisamos os dados das estações do INMET (2024–2026) para descobrir quando a anomalia começou e quais estados serão mais afetados. O resultado aparece em um app web com um agente que responde dúvidas e dá orientações de proteção.

## Integrantes

| Nome | RM | Turma |
|---|---|---|
| Arthur Callegari | RM565476 | 2TSCPV |
| Lucas Zappia | RM560476 | 2TSCPV |
| Enos Cruz | RM561926 | 2TSCPV |

## Origem

Projeto criado pela equipe.

## Tecnologias e como executar

Python 3.12, pandas, Streamlit, pytest, GitHub Actions e Azure App Service.

```bash
pip install -r requirements-dev.txt
pytest
streamlit run app_el_nino.py
```

## Como usamos o GitHub

- **Issues e Project:** uma história de usuário (#1) e cinco tarefas (#2 a #6), cada uma com responsável. Elas passaram por Todo, In Progress e Done no [Project](https://github.com/users/artcllgr/projects/1).
- **Branches e commits:** a `main` só recebe código por Pull Request. Cada alteração foi feita em uma branch própria, como `feature/deploy-azure`.
- **Pull Requests:** [#7](https://github.com/artcllgr/el-nino-agente/pull/7) (testes e CI), [#8](https://github.com/artcllgr/el-nino-agente/pull/8) (deploy) e [#9](https://github.com/artcllgr/el-nino-agente/pull/9) (alteração de demonstração).
- **Credenciais:** ficam só no secret `AZURE_WEBAPP_PUBLISH_PROFILE`, nunca no código.

## Workflow (GitHub Actions)

Arquivo: [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml)

- **Gatilhos:** push em qualquer branch, Pull Request para a `main` e execução manual.
- **Build e testes:** instala as dependências, roda os testes, confere a análise e testa se o app sobe.
- **Deploy:** só roda na `main` e só se os testes passarem. Publica no Azure e grava no rodapé do app a versão e o commit publicados.

## Nuvem

Microsoft Azure App Service (Linux, plano gratuito).

**App:** https://agente-el-nino-2tscpv-g2e6a5a8erh3bfag.eastus2-01.azurewebsites.net

O primeiro acesso pode demorar cerca de 1 minuto, porque o plano gratuito desliga o app quando ninguém está usando.

## Evidências

Os prints estão em [`docs/evidencias/`](docs/evidencias/) e também reunidos, com legendas, em [`docs/Evidencias_GS_Cloud_2TSCPV.pdf`](docs/Evidencias_GS_Cloud_2TSCPV.pdf).

- **Issues e Project:** [lista de issues](docs/evidencias/02-issues-lista.png), [história #1](docs/evidencias/03-historia-1-checklist.png), [tabela](docs/evidencias/04-project-tabela.png), [quadro](docs/evidencias/04b-project-board.png), [#6 em andamento](docs/evidencias/15-project-6-in-progress.png), [tudo concluído](docs/evidencias/16-project-tudo-done.png)
- **Repositório e branch main:** [estrutura](docs/evidencias/05-repositorio-main.png)
- **Commits e PRs:** [commits](docs/evidencias/06-commits.png), [PRs](docs/evidencias/07-prs-fechados.png), [merge do PR #8](docs/evidencias/08-pr-8-merged.png)
- **Workflow:** [gatilhos e testes](docs/evidencias/09a-workflow-gatilhos.png), [deploy](docs/evidencias/09b-workflow-deploy.png), [execuções](docs/evidencias/10a-actions-execucoes.png), [execução com sucesso](docs/evidencias/10b-actions-build-e-deploy.png)
- **App publicado:** [app na versão 6](docs/evidencias/01-app-publicado-versao-6.webp), [Azure](docs/evidencias/11-azure-app-service.png)
- **Alteração atualizando o app:** adicionamos o botão "O que é o El Niño?". Depois do [PR #9](docs/evidencias/12-pr-9-ci-verde.png) veio o merge, o workflow [rodou de novo](docs/evidencias/13a-actions-execucoes-pr9.png) e [publicou](docs/evidencias/13b-actions-deploy-pr9.png), e o app passou para a [versão 12, já com o botão novo](docs/evidencias/14-app-atualizado-versao-12.png).
