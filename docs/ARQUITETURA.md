# Arquitetura proposta — evolução incremental

## Fluxo previsto

1. **Cadastro de entidades:** município, tipo, domínio oficial, URL do portal e metadados de descoberta.
2. **Coleta:** HTTP/HTML com limites de requisição e, se indispensável, browser automatizado; PDFs e tabelas entram por extratores específicos.
3. **Normalização:** armazenar URL, título, texto, data de coleta, hash do conteúdo e documentos associados.
4. **Avaliação:** regras determinísticas para requisitos objetivos; análise semântica seletiva, com evidências, somente quando necessária.
5. **Persistência:** SQLite na POC; tabelas de entidades, critérios, execuções, avaliações e evidências. PostgreSQL numa evolução.
6. **API:** FastAPI publica entidades, resultados e histórico.
7. **Interface:** Streamlit obtém dados da API, sem acessar diretamente o banco.

## Critérios e explicabilidade

Cada critério deve ter código de origem, descrição, tipo de entidade aplicável, peso, estratégia de validação, versão da regra e evidência mínima. Não confundir existência de palavra-chave com atendimento do requisito. Registrar URLs, recortes de texto, horários, hashes e eventuais erros.

Estados previstos: atende, parcial, não_atende, não_aplicavel e inconclusivo. Um erro HTTP ou bloqueio de scraping gera inconclusivo, nunca não_atende automaticamente.

## Pontuação proposta (a validar com o checklist)

Score = 100 × soma(peso × nota) / soma(pesos considerados), considerando apenas critérios aplicáveis e conclusivos.
Notas propostas: atende=1; parcial=0,5; não_atende=0. Mostrar também percentual de cobertura, critérios inconclusivos e data. Não comparar entidades com coberturas muito diferentes sem ressalvas.

## Expansão para milhares de portais

Separar coleta, extração, avaliação e API. Introduzir filas, agendador, workers isolados, políticas de rate-limit por domínio, reprocessamento idempotente e armazenamento de objetos. Priorizar regras baratas; reservar IA para ambiguidade semântica. Monitorar custos e falsos positivos por revisão humana amostral.

## Limitações atuais

Somente esqueleto inicial implementado. Não há crawler, critérios cadastrados, pontuação, persistência ou diagnóstico real dos municípios. Os indicadores permanecerão vazios até que avaliações reais sejam executadas.

## Próximas etapas

Importar checklist recebido; mapear tipos de entidade e critérios; confirmar domínios oficiais; testar coleta; implementar regras e persistência; obter resultados rastreáveis; validar manualmente uma amostra.
