from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.db.models import Role, User

# Роли → права на контракты (ТЗ, Task 1.7) + manage_users для управления сотрудниками
ROLE_PERMISSIONS: dict[str, list[str]] = {
    Role.ADMIN.value: ["view_all", "create", "edit", "delete", "approve", "sign", "manage_users"],
    Role.HEAD.value: ["view_all", "create", "edit", "approve", "manage_users"],
    Role.SENIOR_LAWYER.value: ["view_all", "create", "edit", "approve"],
    Role.LAWYER.value: ["view_assigned", "create", "edit"],
    Role.COMPLIANCE.value: ["view_all", "approve_compliance"],
    Role.FINANCE.value: ["view_all", "approve_finance"],
    Role.EXTERNAL.value: ["view_assigned"],  # read-only
}


def require_permission(permission: str):
    async def permission_checker(user: User = Depends(get_current_user)) -> User:
        if permission not in ROLE_PERMISSIONS.get(user.role, []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied"
            )
        return user

    return permission_checker
