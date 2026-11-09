from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AuditLog


def log_action(db: AsyncSession, admin_id: int, action: str, target_type: str, target_id: str, details: dict) -> None:
    """Adds an AuditLog row to the session without committing — callers add
    this alongside their actual change and commit both together, so the
    audit entry and the change it describes are atomic (plan section 16:
    "every write creates an audit_log row")."""
    db.add(AuditLog(admin_id=admin_id, action=action, target_type=target_type, target_id=target_id, details=details))
