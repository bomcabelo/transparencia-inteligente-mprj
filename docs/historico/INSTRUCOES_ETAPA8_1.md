# Etapa 8.1 — Evidências vinculadas ao município selecionado

1. Extraia o pacote na raiz `C:\transparencia-inteligente-mprj`, preservando a pasta `app` e a pasta `tests`.
2. No CMD, execute `python ATUALIZAR_ETAPA8_1.py`. O script modifica somente a chamada do módulo GeoSIAP no dashboard e gera `app/dashboard.py.etapa8_1.bak`.
3. Execute `python -m pytest -q tests/test_geosiap_filtro.py tests/test_geosiap.py tests/test_geosiap_storage.py`.
4. Execute `python -m pytest -q` para verificar os demais testes.
5. Reinicie FastAPI e Streamlit, caso estejam abertos.
6. Teste selecionando **Cachoeiras de Macacu** (nenhuma evidência GeoSIAP de Japeri deve aparecer) e **Japeri** (evidência 4.1 deve aparecer).
7. Após a validação, publique código e documentação, sem os arquivos de dados brutos: `git add app/dashboard.py app/geosiap_section.py app/geosiap_filtro.py api/geosiap_routes.py src/geosiap_storage.py tests/test_geosiap_storage.py tests/test_geosiap_filtro.py ATUALIZAR_ETAPA8_1.py INSTRUCOES_ETAPA8_1.md`; `git commit -m "Vincula evidências GeoSIAP ao município selecionado"`; `git push origin main`.

O painel preserva a classificação técnica e não atribui conformidade legal automática. A data de processamento não equivale à data de publicação dos dados.
