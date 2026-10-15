# Etapa 9.2 — Receitas próprias no painel MPRJ

Esta atualização integra ao SQLite e ao painel o **resumo técnico** de 169 registros de receitas próprias de Japeri/RJ, sem publicar os registros originais. Não atribui pontuação nem comprova conformidade legal.

1. Extrair o ZIP na raiz `C:\transparencia-inteligente-mprj` preservando as pastas `src`, `app` e `tests`.
2. Com `.venv` ativo, executar `python INSTALAR_ETAPA9_2.py`. O instalador cria backups de `src/geosiap_storage.py` e `app/geosiap_section.py`, e é seguro executar novamente.
3. Executar `python -m pytest -q`.
4. Executar `python -m src.geosiap_receitas_integracao --source data/geosiap_japeri_receitas_2025.json`.
5. Reiniciar FastAPI (`python -m uvicorn api.main:app --reload`) e Streamlit (`python -m streamlit run app/dashboard.py`).
6. Selecionar Japeri; no seletor de evidência GeoSIAP escolher o critério 3.1 para visualizar receitas. Conferir que o critério 4.1 continua exibindo despesas e que os demais municípios não exibem dados de Japeri.

Para não versionar dados brutos, antes do commit executar `git diff --cached --name-only`. Incluir apenas código, testes e documentação. Não incluir `data/*.json`, `data/*.sqlite3` ou `*.bak`.

Sugestão de mensagem de commit: `Integra evidências de receitas próprias ao painel GeoSIAP`.
