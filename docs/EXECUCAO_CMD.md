# Etapa 3 — Persistência e dashboard (CMD Windows)

Executar na raiz do projeto (ambiente virtual ativado):

```cmd
cd /d C:\transparencia-inteligente-mprj
git pull origin main
python -m pytest -q
python -m src.crawler
python -m src.database --source data/coletas.json
```

Em **um CMD**, inicie:

```cmd
python -m uvicorn api.main:app --reload
```

Em **outro CMD**, com o ambiente virtual ativado:

```cmd
python -m streamlit run app/dashboard.py
```

API Swagger: http://127.0.0.1:8000/docs
Dashboard: http://localhost:8501

Os arquivos de coleta JSON e banco SQLite são locais e estão ignorados pelo Git.

**Limites desta etapa:**
- O histórico usa a data/hora efetiva da coleta e preserva todos os registros distintos.
- Reimportar o mesmo JSON não duplica a avaliação.
- Evidência de HTTP 200 é indício técnico de acesso, **não conformidade jurídica**.
- Critério 1.2 ainda requer validação visual; não há pontuação calculada.
- Não existem tarefas agendadas nem coleta JavaScript/PDF nesta versão.
