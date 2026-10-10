"""Index de recherche par prefixe du nom normalise (PostgreSQL).

La recherche de candidats utilise LIKE 'PREFIXE%'. Avec une collation autre
que C, PostgreSQL n'utilise un index B-tree pour ce motif qu'avec la classe
d'operateurs varchar_pattern_ops. Sous SQLite, l'index existant suffit.

Revision : 0002
Revision precedente : 0001
Date de creation : 2026-10-11
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_personnes_nom_normalise_motif "
            "ON personnes (nom_normalise varchar_pattern_ops)"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_personnes_nom_normalise_motif")
