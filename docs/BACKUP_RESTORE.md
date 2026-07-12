# Backup And Restore

## Что нужно сохранять

- PostgreSQL: пользователи, организации, договоры, workflow, audit log, legal RAG.
- MinIO: исходные файлы договоров.
- `.env` и production secrets: хранить отдельно в secret manager.

Elasticsearch можно не бэкапить: индексы пересобираются из PostgreSQL.

## Локальный backup

```powershell
cd backend
.\scripts\backup.ps1
```

Скрипт создаёт папку `backend/backups/<timestamp>` с `postgres.dump`,
копией MinIO data и `manifest.json`.

## Restore

```powershell
cd backend
.\scripts\restore.ps1 -BackupPath .\backups\<timestamp> -RestoreMinio
python -m scripts.reindex_search
python -m scripts.reindex_laws
```

Проверка дампа без затрагивания рабочей базы:

```powershell
.\scripts\test_restore.ps1 -BackupPath .\backups\<timestamp>
```

## Production рекомендации

- PostgreSQL: ежедневный full backup + WAL/PITR, хранение минимум 30 дней.
- MinIO/S3: versioning + lifecycle policy + отдельный bucket/region для backup.
- Периодически тестировать restore на отдельном окружении.
- Шифровать backups и ограничивать доступ по принципу least privilege.
- Запускать backup ежедневно системным scheduler и копировать результат в
  отдельный S3 bucket/регион. Локальная папка `backups` не считается внешней копией.
