"""Canonical Business Model (SPEC §6.3) and tenant database migrations (SPEC §11.2).

Phase 0 ships only the tenant schema baseline. CBM v1.0 entity tables are added in Phase 2.
"""

from dcs_cbm.migrate import CBM_VERSION, TENANT_SCHEMAS, upgrade_tenant

__all__ = ["CBM_VERSION", "TENANT_SCHEMAS", "upgrade_tenant"]
