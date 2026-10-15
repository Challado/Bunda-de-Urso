# Base de dados do Radar Brasil

Backups do banco de producao (SQLite), publicados automaticamente pelo
sincronizador da base. **A pasta guarda sempre os 5 mais recentes** — os
mais velhos sao removidos do repositorio na mesma passada.

Nome do arquivo: `radar-AAAA-MM-DD_HHMMSS.sqlite3.gz` (horario de Brasilia).

## Como restaurar

```
gunzip -k radar-AAAA-MM-DD_HHMMSS.sqlite3.gz   # vira .sqlite3
sqlite3 radar-AAAA-MM-DD_HHMMSS.sqlite3 'PRAGMA integrity_check;'
```

## Backups nesta pasta

- **2026-10-15 144017** — 18.6 MB — snapshot rb-20261015T173731602108Z

## Ultimo retrato (o backup desta rodada)

- Publicado em: 15/10/2026 14:40:34
- Snapshot: `rb-20261015T173731602108Z`
- Pontos de fiscalizacao: 50200
- Registros de fonte: 56921
- Equipamentos: 50200

---

Gerado por `/home/openclaw/bin/radar-base-sync.py` (cron do root).
O banco de verdade segue em `/var/lib/radar-brasil/radar.sqlite3`.
