# Static architecture rules fixture only. Never import or execute.
class BaseEntity:
    pass


class AuditedEntity(BaseEntity):
    pass


class AccountEntity(AuditedEntity):
    pass


class PremiumAccountEntity(AccountEntity):
    pass


def dispatch_order(
    account_id,
    region,
    currency,
    priority,
    discount_code,
    warehouse_id,
    channel,
):
    return (account_id, region, currency, priority, discount_code, warehouse_id, channel)
