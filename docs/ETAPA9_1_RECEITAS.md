# Etapa 9.1 — Receitas públicas GeoSIAP

Esta etapa começa a integração do critério candidato **3.1 (Receitas)**. A API pública do GeoSIAP é consultada **somente com `--consultar`**. Sem a opção, o programa lê a documentação Swagger e apresenta os parâmetros exigidos.

## Instalação

Extraia o pacote na raiz do projeto `C:\transparencia-inteligente-mprj`, preservando as pastas `src/adapters`, `tests` e `docs`.

## 1. Testes

```cmd
python -m pytest -q tests/test_geosiap_receitas.py
python -m pytest -q
```

## 2. Inspeção segura do Swagger

```cmd
python -m src.adapters.geosiap_receitas
```

Este comando lê o Swagger publicado em `https://japeri.geosiap.net.br/portal-transparencia/api-docs/v1/swagger.json` e mostra os parâmetros documentados para o endpoint `/execucao/receitas/proprias/receitas_proprias`.

**Pare aqui e confira a lista de parâmetros.** Se o acesso ao Swagger falhar, salve o JSON localmente e use `--swagger-file caminho/arquivo.json`.

## 3. Consulta real (somente após conferir o Swagger)

A linha abaixo é **exemplo**, não garantia de que os parâmetros sejam suficientes. Adapte **exclusivamente** aos parâmetros documentados na saída do passo 2.

```cmd
python -m src.adapters.geosiap_receitas --consultar --param id_entidade=10 --param ano=2025
```

Se o Swagger exigir outros parâmetros, inclua `--param nome=valor`. O programa recusa parâmetros desconhecidos e obrigatórios ausentes. Condições alternativas descritas em linguagem natural pela API devem ser verificadas manualmente.

A consulta produz `data/geosiap_japeri_receitas_diagnostico.json` com metadados, quantidade de registros (quando identificável), nomes de campos e SHA-256 do retorno. **Não grava os registros individuais**.

## Limitações

- O endpoint foi identificado na especificação, mas ainda não foi validado com dados reais nesta etapa.
- Erros HTTP, ausência de resultados, falhas de rede e conteúdo inesperado **não implicam não conformidade legal**.
- Apenas a entidade 10 (Prefeitura) e o exercício escolhido são analisados no exemplo; outros fundos e órgãos não ficam automaticamente cobertos.
- A próxima etapa consistirá em interpretar os campos financeiros efetivamente retornados e integrar o diagnóstico ao banco e ao dashboard.
- Não versionar JSONs brutos de credores ou dados pessoais.
