# Transparência Inteligente — MPRJ

Prova de conceito para monitorar conformidade de portais públicos municipais a partir de um checklist de transparência.

> **Status:** estrutura inicial do projeto. Nenhum município foi avaliado nesta versão. Não interprete ausência de resultado como não conformidade.

## Objetivo

Coletar páginas e documentos públicos, aplicar critérios verificáveis, guardar evidências e histórico, disponibilizar resultados via API e exibi-los em um dashboard.

## Tecnologias

- Python 3.11+
- FastAPI / Uvicorn para API REST
- Streamlit / Requests para dashboard
- SQLite para persistência (prevista para próxima etapa)
- BeautifulSoup e Playwright para coleta (previstos para próxima etapa)

## Início rápido

```bash
git clone https://github.com/bomcabelo/transparencia-inteligente-mprj.git
cd transparencia-inteligente-mprj
python -m venv .venv
```

Ativar ambiente virtual no Windows (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS: `source .venv/bin/activate`.

Executar API em um terminal:

```bash
uvicorn api.main:app --reload
```

Documentação interativa: http://127.0.0.1:8000/docs

Executar dashboard em outro terminal:

```bash
streamlit run app/dashboard.py
```

O dashboard consulta a API em `http://127.0.0.1:8000` por padrão. Defina `MPRJ_API_URL` para outra URL, se necessário.

## Escopo do desafio

Municípios-alvo: Duque de Caxias, Japeri, Itaboraí, Cachoeiras de Macacu e Rio de Janeiro; expansão opcional para Niterói e Maricá.

Entregáveis previstos: código, documentação técnica, API funcional e dashboard consumidor da API.

## Estrutura

- `api/main.py`: endpoints iniciais
- `app/dashboard.py`: dashboard inicial conectado à API
- `src/`: coleta, critérios, persistência e pontuação (a implementar)
- `config/`: critérios extraídos da planilha do desafio (a implementar)
- `tests/`: testes automatizados (a implementar)
- `docs/`: arquitetura e metodologia (a implementar)

## Metodologia pretendida

Status possíveis: `atende`, `parcial`, `nao_atende`, `nao_aplicavel` e `inconclusivo`.
Atribuir status exige evidência e regra documentada. Falha de acesso não é prova de desconformidade. A pontuação futura será apresentada com cobertura da avaliação e histórico.

## Ética e segurança

Respeitar limites dos sites, termos de acesso e dados pessoais. Não contornar autenticação/CAPTCHA nem publicar credenciais, informações privadas ou inferências sem evidência.

## Licença e autoria

Projeto desenvolvido por Anderson da Silva Rodrigues para o desafio técnico do GATE/MPRJ. Repositório privado durante o desenvolvimento.
