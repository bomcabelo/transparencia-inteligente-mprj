# Transparência Inteligente — MPRJ

Plataforma de **monitoramento contínuo** da conformidade de portais públicos com o checklist de transparência (`checklistPortalTransp.xlsx`). Para cada entidade, o sistema:

- localiza o portal;
- navega pelas páginas relevantes;
- avalia cada critério aplicável com **evidências verificáveis** e grau de confiança;
- calcula um **score ponderado com intervalo de incerteza**;
- guarda o **histórico**;
- publica tudo numa **API** consumida por um **dashboard**.

Desafio técnico GATE/MPRJ — Cientista de Dados. Autor: Anderson da Silva Rodrigues.

| Documento | Conteúdo |
|---|---|
| [docs/DOCUMENTACAO_TECNICA.md](docs/DOCUMENTACAO_TECNICA.md) | Problema, arquitetura, abordagem, metodologia de avaliação e de pontuação, não aplicáveis, erros, atualização, escalabilidade, IA, limitações e evolução |
| [docs/DOCUMENTACAO_TECNICA.md §5.5.1](docs/DOCUMENTACAO_TECNICA.md#551-resultados-da-validação-17102026) | Resultados da validação manual (robô × humano) e ajustes feitos |
| [docs/CRITERIOS.md](docs/CRITERIOS.md) | Os 27 critérios automatizados, a justificativa da seleção e como adicionar novos |

## Destaques

- **Checklist como dado.** Os 142 quesitos são importados da planilha original, com matriz (comum × Poder Executivo), fundamentação, classificação (essencial/obrigatória/recomendada), peso e aplicabilidade por tipo de entidade.
- **27 critérios automatizados** cobrindo os seis níveis de complexidade do desafio: existência, navegação, dados estruturados, documentos, atualização e interpretação semântica.
- **Ausência ≠ não conformidade.** Falha de acesso, conteúdo dinâmico ou baixa confiança viram `inconclusivo`, nunca `nao_atende`.
- **Score explicável.** Média ponderada só dos critérios conclusivos, com intervalo `[mínimo–máximo]`, cobertura e classificação que exige os critérios essenciais.
- **Reprodutível.** Snapshots HTML endereçados por SHA-256 permitem reprocessar coletas antigas com regras novas, sem acessar os portais.
- **IA opcional e controlada.** Recebe só trechos pré-filtrados, precisa citar texto literal, tem cache e teto de chamadas, e divergência com a regra vai para revisão humana.

## Início rápido

Requer **Python 3.10 ou mais novo** (testado do 3.10 ao 3.14) e Git. Os comandos são os mesmos no CMD, no PowerShell, no Linux e no macOS:

```
git clone https://github.com/bomcabelo/transparencia-inteligente-mprj.git
cd transparencia-inteligente-mprj
python -m pip install -r requirements.txt
python iniciar.py
```

O `iniciar.py` confere o ambiente, prepara os dados, sobe a API e o painel e abre o navegador. Ctrl+C encerra tudo.

- **Painel:** <http://localhost:8501>
- **API e Swagger:** <http://127.0.0.1:8000/docs>

Os dados vêm da avaliação real, se ela já tiver sido executada nesta máquina. Senão, vêm de uma **base de demonstração** com quatro entidades fictícias (`[DEMO] ...`) e três meses de histórico, criada na hora e sem acesso à internet. A pasta `data/` não vai para o repositório, então um clone novo começa pela demonstração.

No Linux e no macOS, se `python` não existir, use `python3`. Se preferir isolar as dependências num ambiente virtual, crie-o antes do `pip install`:

| Terminal | Criar e ativar o ambiente virtual |
|---|---|
| CMD | `python -m venv .venv` e `.venv\Scripts\activate.bat` |
| PowerShell | `python -m venv .venv` e `.venv\Scripts\Activate.ps1` |
| Linux/macOS | `python3 -m venv .venv` e `source .venv/bin/activate` |

Para conferir a instalação sem abrir nada: `python iniciar.py --verificar`. Para rodar os testes: `python -m pytest -q`.

### Avaliar os municípios reais

Exige internet e leva cerca de 10 minutos por município, porque o robô espera entre as requisições para não sobrecarregar os portais:

```
python -m src.pipeline run --workers 3
python iniciar.py
```

Para avaliar só alguns: `python -m src.pipeline run --entity japeri --entity rio-de-janeiro`.

### Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| `No module named ...` ao iniciar | Dependências instaladas em outro Python. Rode `python -m pip install -r requirements.txt` com o mesmo `python` usado no `iniciar.py` |
| `Activate.ps1 não pode ser carregado` (PowerShell) | Política de execução do Windows. Rode `Set-ExecutionPolicy -Scope Process Bypass` no mesmo terminal, ou use o CMD, ou pule o ambiente virtual |
| Painel abre, mas sem entidades | O banco está vazio. Use `python iniciar.py --demo` |
| Porta 8000 ou 8501 ocupada | O `iniciar.py` escolhe a próxima porta livre e mostra o endereço |
| `pip install` falha na rede institucional | Configure o proxy: `python -m pip install --proxy http://usuario:senha@proxy:porta -r requirements.txt` |

### Iniciar API e painel separadamente

O `iniciar.py` faz isto por você. Para controlar cada parte, use dois terminais:

```
python -m uvicorn api.main:app            # terminal 1 (MPRJ_DB_PATH escolhe o banco)
python -m streamlit run app/dashboard.py  # terminal 2 (MPRJ_API_URL aponta a API)
```

## Comandos

| Comando | O que faz |
|---|---|
| `python iniciar.py [--demo] [--banco arquivo] [--verificar]` | Sobe API e painel com dados (avaliação real ou demonstração) |
| `python -m src.pipeline run [--entity id] [--workers N] [--no-probes]` | Coleta, avalia, pontua e grava uma nova execução |
| `python -m src.pipeline reevaluate --latest` | Reaplica as regras atuais às últimas coletas, a partir dos snapshots (sem rede) |
| `python -m src.scheduler --interval-hours 720` | Execução periódica residente. Para `schtasks` e `cron`, veja `src/scheduler.py` |
| `python -m src.pipeline diagnostico --entity id` | Mostra o que o robô viu na última coleta: páginas, erros, links da capa por domínio, páginas que dependem de JavaScript |
| `python -m src.validacao [--entity id] [--saida arquivo.xlsx] [--anterior conferida.xlsx]` | Planilha de validação manual robô × humano, com métricas calculadas (concordância, falsos "não atende", kappa) |
| `python -m src.checklist` | Reimporta a planilha para `config/checklist.json` |
| `python -m src.demo` | Base de demonstração sintética |

### Configuração

| Variável / arquivo | Efeito |
|---|---|
| `config/municipios.json` | Entidades, tipo, site, portal e `ativo`. Por entidade, também `render_js`, `intervalo_segundos` e `max_paginas` (para sites com firewall sensível). Niterói e Maricá estão inativos até confirmar o domínio |
| `config/metodologia.json` | Pesos, faixas de classificação, confiança mínima, limites de atualização, orçamento de coleta |
| `MPRJ_DB_PATH` | Caminho do banco SQLite (padrão `data/transparencia.sqlite3`) |
| `MPRJ_RENDER_JS=1` ou `"render_js": true` na entidade | Renderiza JavaScript com Playwright (para todas as entidades ou só para uma) e salva screenshots. Requer `pip install -r requirements-opcional.txt` e `python -m playwright install chromium` |
| `MPRJ_LLM_PROVIDER`, `MPRJ_LLM_MODEL`, `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, `MPRJ_LLM_MAX_CALLS` | Ativa a camada de IA opcional (§11 da documentação) |

## API

| Rota | Descrição |
|---|---|
| `GET /overview` | Visão geral: média, melhor/pior, ranking, distribuição, critérios por status |
| `GET /entities` | Entidades com o resultado mais recente |
| `GET /entities/{id}` | Cadastro |
| `GET /entities/{id}/evaluations/latest` | Última avaliação com critérios e evidências |
| `GET /entities/{id}/evaluations/history` | Série histórica de scores |
| `GET /entities/{id}/evaluations/diff` | O que melhorou, piorou e segue pendente |
| `GET /entities/{id}/criteria` | Situação por critério, com `atende_desde` |
| `GET /entities/{id}/criteria/{criterio}/history` | Linha do tempo de um critério |
| `GET /criteria` | Catálogo do checklist e situação da automação |
| `GET /runs` | Execuções |

## Estrutura

```
iniciar.py      inicia API + painel com um comando
api/            API FastAPI (somente leitura)
app/            Dashboard Streamlit (consome só a API)
config/         checklist.json (gerado da planilha), metodologia.json, municipios.json, fonte/*.xlsx
src/
  checklist.py  importação do checklist, pesos e aplicabilidade
  entities.py   cadastro e inferência do tipo de entidade
  fetch.py      HTTP educado (robots, rate limit, retries) + Playwright opcional
  collector.py  crawler focado por temas
  page.py       snapshot estruturado da página
  themes.py     vocabulário temático (nomenclaturas diferentes → mesmo tema)
  fingerprint.py, adapters/   fornecedor do portal e sondas de API (GeoSIAP)
  rules/        uma regra por critério (evidência + confiança)
  ai/llm.py     juiz de IA opcional e validado
  engine.py     aplica o catálogo inteiro (aplicável / não aplicável / não avaliado)
  scoring.py    score ponderado, intervalo, cobertura, classificação
  repository.py persistência histórica, snapshots, diff
  pipeline.py, scheduler.py   orquestração e agendamento
  validacao.py  planilha de validação robô × avaliador humano
  demo.py       portal sintético para testes e demonstração
  crawler.py, discovery.py, evidence.py, evaluator.py, database.py, geosiap_*   etapas exploratórias anteriores
tests/          89 testes (regras, score, IA, fetch, pipeline ponta a ponta, API, painel)
docs/           documentação técnica, critérios, histórico das etapas
```

## Ética e segurança

O robô se identifica no User-Agent e respeita o robots.txt e os limites de requisição. Não contorna autenticação nem CAPTCHA, não submete formulários e não armazena dados pessoais de credores. Os resultados são indicadores técnicos que apoiam, e não substituem, a análise jurídica.
