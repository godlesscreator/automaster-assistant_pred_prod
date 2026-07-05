"""initial_schema

Создание таблиц leads и web_sessions.

Revision ID: 06b9ab3974a1
Revises:
Create Date: 2026-06-30 18:17:40.142431

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06b9ab3974a1'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Таблица leads — заявки клиентов
    op.create_table(
        'leads',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(50), server_default='', nullable=True),
        sa.Column('timestamp', sa.String(50), server_default='', nullable=True),
        sa.Column('name', sa.String(255), server_default='', nullable=True),
        sa.Column('phone', sa.String(50), server_default='', nullable=True),
        sa.Column('car', sa.String(255), server_default='', nullable=True),
        sa.Column('service', sa.String(255), server_default='', nullable=True),
        sa.Column('desired_datetime', sa.String(50), server_default='', nullable=True),
        sa.Column('comment', sa.Text(), server_default='', nullable=True),
        sa.Column('user_id', sa.String(255), server_default='', nullable=True),
        sa.Column('status', sa.String(50), server_default='new', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_leads_source'), 'leads', ['source'], unique=False)
    op.create_index(op.f('ix_leads_name'), 'leads', ['name'], unique=False)
    op.create_index(op.f('ix_leads_phone'), 'leads', ['phone'], unique=False)
    op.create_index(op.f('ix_leads_user_id'), 'leads', ['user_id'], unique=False)
    op.create_index(op.f('ix_leads_status'), 'leads', ['status'], unique=False)

    # Таблица web_sessions — сессии веб-чата
    op.create_table(
        'web_sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), server_default='', nullable=True),
        sa.Column('phone', sa.String(50), server_default='', nullable=True),
        sa.Column('car', sa.String(255), server_default='', nullable=True),
        sa.Column('service', sa.String(255), server_default='', nullable=True),
        sa.Column('desired_datetime', sa.String(50), server_default='', nullable=True),
        sa.Column('comment', sa.Text(), server_default='', nullable=True),
        sa.Column('awaiting', sa.String(50), nullable=True),
        sa.Column('messages', sa.Text(), server_default='[]', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_web_sessions_session_id'),
        'web_sessions',
        ['session_id'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_web_sessions_session_id'), table_name='web_sessions')
    op.drop_table('web_sessions')
    op.drop_index(op.f('ix_leads_status'), table_name='leads')
    op.drop_index(op.f('ix_leads_user_id'), table_name='leads')
    op.drop_index(op.f('ix_leads_phone'), table_name='leads')
    op.drop_index(op.f('ix_leads_name'), table_name='leads')
    op.drop_index(op.f('ix_leads_source'), table_name='leads')
    op.drop_table('leads')
