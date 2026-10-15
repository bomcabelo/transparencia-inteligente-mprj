# Etapa 6 — Triagem de evidências (Windows CMD)

Arquivos novos: `src/evidence.py` e `tests/test_evidence.py`.
Não substitua `src/evaluator.py` nem `src/database.py`.

```cmd
cd /d C:\transparencia-inteligente-mprj
.venv\Scripts\activate.bat
python -m pytest -q
python -m src.evidence --source data/descoberta.json --output data/evidencias.json --update-db
```

O módulo examina apenas as páginas coletadas na Etapa 5. Ele identifica LINKS e TÍTULOS candidatos para os quesitos 3.1 e 4.1, e assuntos relacionados a licitações e contratos. Todas as detecções permanecem candidatas, sem score jurídico. A base SQLite recebe uma tabela `evidence_candidates`. Reexecutar o importador evita duplicações pelo identificador da evidência.

Atenção: como cada coleta usa poucos links/páginas, a ausência de candidato significa somente **não encontrado na amostra**. A próxima etapa será aprofundar validação de conteúdo e apresentar esta tabela pela API.
