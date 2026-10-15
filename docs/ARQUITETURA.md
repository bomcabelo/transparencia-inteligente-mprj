# Arquitetura

A arquitetura vigente está em [DOCUMENTACAO_TECNICA.md §2](DOCUMENTACAO_TECNICA.md#2-arquitetura). O modelo de dados está no §12 e a estratégia de escala no §8.

Resumo do fluxo:

1. **Cadastro** (`config/municipios.json`): entidade, tipo, site e portal (opcional, descoberto na capa).
2. **Coleta** (`src/fetch.py`, `src/collector.py`): crawler focado, educado e com circuit breaker. O HTML é guardado como snapshot endereçado por SHA-256.
3. **Fornecedor** (`src/fingerprint.py`, `src/adapters/`): identificação da tecnologia e sondas de API (GeoSIAP).
4. **Avaliação** (`src/engine.py`, `src/rules/`): uma regra por critério, com evidências e confiança. IA opcional para critérios semânticos.
5. **Pontuação** (`src/scoring.py`): score ponderado com intervalo e cobertura.
6. **Persistência** (`src/repository.py`): histórico imutável, diff e reprocessamento sem rede.
7. **API** (`api/main.py`) → **Dashboard** (`app/dashboard.py`).
