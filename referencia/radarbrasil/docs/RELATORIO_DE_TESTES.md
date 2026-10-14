# Testes locais da entrega

- Ambiente de desenvolvimento: Python 3.13, pytest 9, SQLAlchemy 2, SQLite; sem DNS para as fontes governamentais.
- Suíte original: 11 testes de integração testados em dois grupos de 6 e 5, com sucesso.
- Suíte de reforço: 15 testes `tests/test_enhancements.py`, com sucesso.
- Total: **26 testes locais aprovados** em execuções separadas. Incluem importação e segregação de velocidades, consulta `.pse` via subprocesso GET/POST, TXT, JSON, XML, NDJSON, DIF e EDIFACT, links XLSX da PRF, status, proteção HTTPS, retry 429/304, cache, fonte Inmetro, operações pontuais, fusão conservadora, tráfego, consultas detalhadas e cursor.
- **Não houve execução de coleta real ponta a ponta ANTT/DNIT/PRF/Inmetro no ambiente de construção**, nem homologação real PostgreSQL/MySQL/MariaDB/Firebird. O script `scripts/validar_fontes_reais.py` fornece smoke de download sem modificar a base para essa fase.

Comandos:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_integration.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_enhancements.py
python scripts/validar_fontes_reais.py --source ANTT_RADARES --out /tmp/antt-validacao.json
```
