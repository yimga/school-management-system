"""Canonical boundary between SaaS billing and tenant school-fee payments."""

PLATFORM_SUBSCRIPTION_OWNER = "runmycampus"
TENANT_FEE_MERCHANT_OF_RECORD = "tenant"
TENANT_GATEWAY_CREDENTIAL_OWNER = "tenant"
TENANT_FUNDS_SETTLEMENT_OWNER = "tenant"
PLATFORM_COLLECTS_TENANT_FUNDS = False
PLATFORM_SPLITS_TENANT_FUNDS = False
LOCAL_FIRST_REQUIRES_PSP = False


def tenant_payment_boundary() -> dict[str, str | bool]:
    return {
        "platform_subscription_owner": PLATFORM_SUBSCRIPTION_OWNER,
        "tenant_fee_merchant_of_record": TENANT_FEE_MERCHANT_OF_RECORD,
        "tenant_gateway_credential_owner": TENANT_GATEWAY_CREDENTIAL_OWNER,
        "tenant_funds_settlement_owner": TENANT_FUNDS_SETTLEMENT_OWNER,
        "platform_collects_tenant_funds": PLATFORM_COLLECTS_TENANT_FUNDS,
        "platform_splits_tenant_funds": PLATFORM_SPLITS_TENANT_FUNDS,
        "local_first_requires_psp": LOCAL_FIRST_REQUIRES_PSP,
    }
