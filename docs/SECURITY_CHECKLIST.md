# Security Checklist

## Перед production

- `ENVIRONMENT=production`
- `SECRET_KEY` заменён на сильный секрет.
- `DATABASE_URL` указывает не на localhost.
- `CORS_ORIGINS` содержит только production frontend origin.
- `ANTHROPIC_API_KEY` хранится в secret manager.
- `ALLOW_STUB_SIGNATURES=false`
- `EIMZO_DSV_URL` настроен и доступен только backend.
- SMTP/Telegram credentials не коммитятся в git.

## Доступы

- Проверить роли `admin`, `head`, `senior_lawyer`, `lawyer`, `finance`,
  `compliance`, `external`.
- Проверить, что пользователь одной организации не видит договоры другой.
- Проверить, что `external` не может создавать, редактировать и подписывать.
- Проверить audit log для create/update/delete/sign/workflow операций.

## Файлы

- Ограничение размера загрузки: 20 MB.
- Разрешённые форматы: PDF, DOCX, TXT.
- Presigned download URLs должны иметь короткий TTL.
- MinIO/S3 bucket не должен быть публичным.

## AI

- Law Agent должен возвращать `legal_sources`.
- Ответы без найденных источников должны содержать предупреждение о проверке
  первоисточника.
- Для конфиденциальных клиентов нужно отдельное согласие на внешнюю LLM-обработку.

## Бэкапы

- Проверить `scripts/backup.ps1`.
- Проверить restore на отдельной базе.
- Не хранить backups на том же диске без внешней копии.
