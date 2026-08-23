from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.db.models import Role, User

# Роли → права (ТЗ, раздел 7).
#
#   view_all / view_assigned — видимость документов
#   view_all_projects        — доступ ко всем проектам организации, включая
#                              те, где назначены участники (ТЗ, раздел 7)
#   create / edit / delete   — работа с документами
#   comment                  — комментарии к документу и пунктам; есть даже у
#                              наблюдателя, который не может менять статусы
#   confirm_clause           — подтверждение пунктов в Модуле 1
#   run_review               — запуск модулей проверки
#   export                   — выгрузка DOCX/PDF
#   approve                  — подтверждение документа; ТЗ (раздел 2) прямо
#                              называет автором этого статуса юриста
#   archive                  — перевод в архив; по ТЗ это тоже действие юриста
#   finalize                 — перевод в «Финальный»; ТЗ (раздел 7) отдаёт его
#                              строкой «Старший юрист / руководитель», то есть
#                              обоим, а не одному руководителю
#   verify_template          — отметка «верифицирован» на шаблоне
#   manage_templates         — создание и правка шаблонов
#   manage_catalog           — правовая база и каталог типов документов
#   manage_users             — управление сотрудниками
ROLE_PERMISSIONS: dict[str, list[str]] = {
    Role.ADMIN.value: [
        "view_all",
        "view_all_projects",
        "create",
        "edit",
        "delete",
        "comment",
        "confirm_clause",
        "run_review",
        "export",
        "approve",
        "archive",
        "finalize",
        "sign",
        "verify_template",
        "manage_templates",
        "manage_catalog",
        "manage_users",
    ],
    Role.HEAD.value: [
        "view_all",
        "view_all_projects",
        "create",
        "edit",
        "comment",
        "confirm_clause",
        "run_review",
        "export",
        "approve",
        "archive",
        "finalize",
        "verify_template",
        "manage_templates",
        "manage_users",
    ],
    Role.SENIOR_LAWYER.value: [
        "view_all",
        "view_all_projects",
        "create",
        "edit",
        "comment",
        "confirm_clause",
        "run_review",
        "export",
        "approve",
        "archive",
        "finalize",
        "verify_template",
        "manage_templates",
    ],
    Role.LAWYER.value: [
        "view_assigned",
        "create",
        "edit",
        "comment",
        "confirm_clause",
        "run_review",
        "export",
        "approve",
        "archive",
        "manage_templates",
    ],
    Role.COMPLIANCE.value: ["view_all", "comment", "approve_compliance"],
    Role.FINANCE.value: ["view_all", "comment", "approve_finance"],
    # Наблюдатель по ТЗ: просмотр и комментирование без права менять статусы.
    Role.OBSERVER.value: ["view_all", "comment"],
    Role.EXTERNAL.value: ["view_assigned"],  # read-only
}


def has_permission(user: User, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(user.role, [])


def require_permission(permission: str):
    async def permission_checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав для этого действия"
            )
        return user

    return permission_checker
