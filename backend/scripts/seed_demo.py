import asyncio
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import hash_password
from app.db.base import engine
from app.db.models import (
    AgentResult,
    Contract,
    ContractDeadline,
    ContractVersion,
    Notification,
    Organization,
    Role,
    SignRequest,
    User,
    WorkflowState,
)
from app.services.notifications import create_deadline_notifications
from app.services.signature import contract_hash, stub_signature

DEMO_EMAIL = "demo@legal.local"
DEMO_USERNAME = "demo_admin"
DEMO_PASSWORD = "demo12345"
DEMO_ORG = "Demo Legal Department"


async def _delete_demo_contracts(session, org_id) -> None:
    contract_ids = (
        await session.execute(
            select(Contract.id).where(
                Contract.organization_id == org_id,
                Contract.title.ilike("Demo:%"),
            )
        )
    ).scalars().all()
    if not contract_ids:
        return

    for model in (
        Notification,
        ContractDeadline,
        SignRequest,
        WorkflowState,
        AgentResult,
        ContractVersion,
    ):
        await session.execute(delete(model).where(model.contract_id.in_(contract_ids)))
    await session.execute(delete(Contract).where(Contract.id.in_(contract_ids)))


async def seed_demo() -> dict:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        org = (
            await session.execute(select(Organization).where(Organization.name == DEMO_ORG))
        ).scalar_one_or_none()
        if org is None:
            org = Organization(
                name=DEMO_ORG,
                email="legal@example.local",
                phone="+998 90 000 00 00",
                address="Tashkent",
            )
            session.add(org)
            await session.flush()

        user = (
            await session.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=DEMO_EMAIL,
                username=DEMO_USERNAME,
                hashed_password=hash_password(DEMO_PASSWORD),
                full_name="Demo Admin",
                role=Role.ADMIN.value,
                organization_id=org.id,
            )
            session.add(user)
        else:
            user.username = DEMO_USERNAME
            user.hashed_password = hash_password(DEMO_PASSWORD)
            user.full_name = "Demo Admin"
            user.role = Role.ADMIN.value
            user.organization_id = org.id
            user.is_active = True
        await session.flush()

        await _delete_demo_contracts(session, org.id)

        today = date.today()
        now = datetime.now(timezone.utc)
        draft = Contract(
            organization_id=org.id,
            title="Demo: Equipment Supply Draft",
            contract_type="purchase",
            counterparty="TechnoProm LLC",
            status="draft",
            content=(
                "Supply agreement draft. Payment deadline: "
                f"{(today + timedelta(days=10)).isoformat()}."
            ),
            amount=150000000,
            currency="UZS",
            created_by=user.id,
        )
        ready = Contract(
            organization_id=org.id,
            title="Demo: Services Ready To Sign",
            contract_type="service",
            counterparty="Service Partner LLC",
            status="ready_to_sign",
            content=(
                "Service agreement. Payment deadline: "
                f"{(today + timedelta(days=4)).isoformat()}. "
                "Report deadline: "
                f"{(today + timedelta(days=6)).isoformat()}."
            ),
            amount=32000000,
            currency="UZS",
            risk_score=35,
            created_by=user.id,
        )
        signed = Contract(
            organization_id=org.id,
            title="Demo: Office Lease Signed",
            contract_type="lease",
            counterparty="Business Center LLC",
            status="signed",
            content=(
                "Lease agreement. Delivery deadline: "
                f"{(today + timedelta(days=2)).isoformat()}."
            ),
            amount=12000000,
            currency="UZS",
            risk_score=20,
            created_by=user.id,
            signed_at=now,
            signed_by=user.id,
            signature_timestamp=now,
        )
        session.add_all([draft, ready, signed])
        await session.flush()

        signature, certificate, thumbprint = stub_signature(contract_hash(signed), signed.id)
        signed.signature = signature
        signed.signature_certificate = certificate
        signed.certificate_thumbprint = thumbprint

        for contract in (draft, ready, signed):
            session.add(
                ContractVersion(
                    contract_id=contract.id,
                    version_number=1,
                    content=contract.content,
                    changes_description="Demo seed",
                    created_by=user.id,
                )
            )

        session.add_all(
            [
                WorkflowState(
                    contract_id=ready.id,
                    current_stage="ready_to_sign",
                    approved_by=user.id,
                    approved_at=now,
                    comments="Demo approval chain",
                ),
                WorkflowState(
                    contract_id=signed.id,
                    current_stage="signed",
                    approved_by=user.id,
                    approved_at=now,
                    comments="Demo signature",
                ),
            ]
        )

        for contract, deadline_type, days in (
            (draft, "payment", 10),
            (ready, "payment", 4),
            (ready, "report", 6),
            (signed, "delivery", 2),
        ):
            session.add(
                ContractDeadline(
                    contract_id=contract.id,
                    deadline_date=today + timedelta(days=days),
                    deadline_type=deadline_type,
                )
            )

        await create_deadline_notifications(session, organization_id=org.id)
        await session.commit()
        return {
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD,
            "organization": DEMO_ORG,
            "contracts": [draft.title, ready.title, signed.title],
        }


if __name__ == "__main__":
    result = asyncio.run(seed_demo())
    print("Demo data ready:")
    for key, value in result.items():
        print(f"{key}: {value}")
