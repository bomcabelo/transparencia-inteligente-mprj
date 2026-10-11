# Etapa 8 — Integração das evidências GeoSIAP

## Instalação no Windows

1. Extraia o conteúdo deste ZIP na raiz de `C:\transparencia-inteligente-mprj`, mantendo as pastas `src`, `api`, `app`, `tests`.
2. Execute o instalador para integrar as novas rotas e a seção do painel, mantendo backups dos pontos de entrada:

```cmd
python INSTALAR_ETAPA8.py
```

O instalador é idempotente; não duplica as importações quando executado novamente. Ele gera backups com a extensão `.etapa8.bak`.

4. Execute:

```cmd
python -m pytest -q tests/test_geosiap_storage.py
python -m src.geosiap_storage --source data/geosiap_japeri_resumo_2025.json
```

5. Inicie a API e o painel em dois terminais:

```cmd
python -m uvicorn api.main:app --reload
```

```cmd
python -m streamlit run app/dashboard.py
```

6. Abra `http://127.0.0.1:8000/geosiap/evidences` para verificar o novo endpoint.

## Observações

- A importação é idempotente com base em município, entidade, exercício e hash do JSON bruto.
- O módulo persiste **somente os indicadores resumidos**, não os registros individuais nem os nomes de credores.
- O status `evidencia_parcial` é técnico; conformidade legal segue **inconclusiva**.
- Não envie ao GitHub `data/geosiap_japeri_empenhos_2025.json`, o banco `.sqlite3` ou arquivos com documentos pessoais.
- Os dados são disponibilizados numa área específica do painel, sem alterar avaliações antigas das demais prefeituras.
- Esta etapa não executa novas requisições ao portal municipal.
