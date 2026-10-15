# Critérios implementados e justificativa da seleção

O checklist (`config/fonte/checklistPortalTransp.xlsx`) tem **142 quesitos**: 122 na matriz comum e 20 na matriz específica do Poder Executivo. Esta versão automatiza **27**. Eles foram escolhidos para cobrir os seis níveis de complexidade pedidos no item 13 do desafio. Todos os temas centrais da Transparência Ativa e Passiva estão representados.

| Nível (item 13 do desafio) | Critérios | O que exercita |
|---|---|---|
| Existência simples de informação | 1.1, 2.4, 2.5, 2.6 | HTTP + padrões textuais (CEP, telefone com DDD, horário) |
| Estrutura da página | 1.2, 1.3, 16.1, 16.2, 16.3 | Análise do DOM: links, formulários, trilha de navegação e controles de acessibilidade |
| Navegação | 2.9, 15.1 | Crawler focado precisa chegar à página certa (contato, e-SIC) |
| Dados estruturados | 3.1, 4.1, 3.5, 4.5, 18.3 | Cabeçalhos de tabelas, formatos de exportação, API do fornecedor (GeoSIAP) |
| Documentos | 12.1, 20.1, 19.1, 19.3, 19.5 | Arquivos (PDF etc.), rótulo, exercício e formato |
| Atualização e histórico | 4.6, 4.7 | Datas no conteúdo comparadas à data da coleta; seletor de exercícios |
| Interpretação semântica | 15.2, 15.4, 18.1, 2.1 | Leitura de texto e de requisitos de formulário. A IA é opcional e entra só quando a regra não decide |

Por que estes critérios:

- **Peso jurídico.** Onze dos 27 são *essenciais*: 1.1, 1.2, 1.3, 3.1, 4.1, 12.1, 15.1, 19.1, 19.3, 19.5 e 20.1. São os itens da LC 101/2000 e da LAI que mais pesam numa avaliação real.
- **Generalização.** As regras de *formatos* (3.5/4.5), *atualização* (4.6) e *histórico* (4.7) repetem-se no checklist para receita, transferências, pessoal, diárias, licitações e contratos. Os mesmos helpers (`_formats`, `_dates`, `_document`) passam a cobrir os critérios equivalentes (5.8–5.10, 6.8–6.11, 7.8–7.10, 8.4–8.6…) trocando apenas o tema. A arquitetura escala em critérios, não só em entidades.
- **Aplicabilidade.** Os critérios 19.x e 20.1 só existem na matriz do Executivo, o que permite testar o tratamento de `nao_aplicavel` (ex.: Câmara Municipal na demonstração).
- **Onde a IA agrega valor.** 15.2 e 18.1 dependem de interpretar exigências escritas em texto livre. Por isso, são os únicos que acionam a camada de IA.

## Tabela completa

| Critério | Descrição (planilha) | Classificação (peso) | Complexidade | Técnica | Regra |
|---|---|---|---|---|---|
| 1.1 | Possui sítio oficial e/ou portal da transparência | essencial (3) | existência | http | Sítio oficial e/ou portal acessível (HTTP 200). Indisponibilidade = inconclusivo |
| 1.2 | Acesso ao portal visível na capa | essencial (3) | estrutural | html_links | Link rotulado "Transparência" na capa. Só ícone sem texto = parcial |
| 1.3 | Ferramenta de pesquisa de conteúdo | essencial (3) | estrutural | html_forms | Campo `type=search` ou nomes `q`, `s`, `busca`, `pesquisa` |
| 2.1 | Competências e/ou atribuições | obrigatória (2) | semântica | texto+ia | Página institucional com título de competências e conteúdo suficiente |
| 2.4 | Endereços | obrigatória (2) | existência | regex | CEP ou logradouro com número |
| 2.5 | Telefones | obrigatória (2) | existência | regex | Telefone com DDD |
| 2.6 | Horário de atendimento | obrigatória (2) | existência | regex | "Horário de atendimento" ou faixa "8h às 17h" |
| 2.9 | Canal "Fale Conosco" | obrigatória (2) | navegação | links+formulários | Formulário com e-mail + mensagem; só link = atende com confiança menor |
| 3.1 | Receita arrecadada | essencial (3) | dados estruturados | tabelas+API | Tabela com coluna "arrecadado/realizado" ou API GeoSIAP |
| 3.5 | Relatórios de receita em diversos formatos | obrigatória (2) | dados estruturados | documentos | ≥ 2 formatos com ≥ 1 legível por máquina = atende; 1 formato = parcial |
| 4.1 | Empenho, liquidação e pagamento | essencial (3) | dados estruturados | tabelas+API | Cabeçalhos com as três fases; faltando alguma = parcial |
| 4.5 | Relatórios de despesa em diversos formatos | obrigatória (2) | dados estruturados | documentos | Como 3.5 |
| 4.6 | Despesa atualizada | obrigatória (2) | atualização | datas no conteúdo | Idade do registro mais recente: ≤ 7 dias atende, ≤ 45 parcial (configurável) |
| 4.7 | Histórico da despesa | obrigatória (2) | atualização | filtros | ≥ 3 exercícios selecionáveis = atende |
| 12.1 | RGF | essencial (3) | documentos | documentos | Arquivo com rótulo/URL RGF ou "gestão fiscal"; anos detectados |
| 15.1 | e-SIC eletrônico | essencial (3) | navegação | links+formulários | Formulário de pedido ou link para sistema e-SIC |
| 15.2 | e-SIC sem exigências indevidas | obrigatória (2) | semântica | formulário+IA | Campos obrigatórios de documento, firma, declaração, maioridade ou motivo = não atende |
| 15.4 | Prazos e recurso informados no e-SIC | obrigatória (2) | semântica | texto | "20 dias" + "recurso" |
| 16.1 | Caminho de páginas (breadcrumb) | obrigatória (2) | estrutural | breadcrumb | Trilha em ≥ 50% das páginas internas |
| 16.2 | Alto contraste | obrigatória (2) | estrutural | controles | Presente no sítio e no portal = atende; em um só = parcial |
| 16.3 | Redimensionamento de texto | obrigatória (2) | estrutural | controles | Como 16.2 (A+/A−, aumentar fonte) |
| 18.1 | Encarregado LGPD com canal de contato | recomendada (1) | semântica | texto+IA | "Encarregado" + e-mail ou telefone próximos |
| 18.3 | Dados abertos com regras de uso | recomendada (1) | dados estruturados | documentos+texto | Arquivos legíveis por máquina ou API + termos de uso/licença |
| 19.1 | PPA | essencial (3) | documentos | documentos | Arquivo PPA / plano plurianual |
| 19.3 | LDO | essencial (3) | documentos | documentos | Arquivo LDO / diretrizes orçamentárias |
| 19.5 | LOA | essencial (3) | documentos | documentos | Arquivo LOA / lei orçamentária anual |
| 20.1 | RREO | essencial (3) | documentos | documentos | Arquivo RREO / relatório resumido |

O código está em `src/rules/criterios.py`. Cada regra é uma função pura registrada com `@rule(...)`, com versão (`rule_version` = `4.6@1.0`), complexidade e técnica. A API expõe esses metadados em `GET /criteria`.

## Como adicionar um critério

1. Escrever a função em `src/rules/criterios.py`, decorada com `@rule("7.1", complexidade=..., tecnica=...)`.
2. Se o tema for novo, acrescentar o vocabulário em `src/themes.py`. O crawler passa a priorizar esses links automaticamente.
3. Escrever um teste com o portal sintético (`src/demo.py`) ou com um HTML real salvo.
4. Rodar `python -m src.pipeline reevaluate --latest`. As coletas antigas são reavaliadas a partir dos snapshots, sem acessar os portais.
