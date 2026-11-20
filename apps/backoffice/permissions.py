from dataclasses import dataclass


@dataclass(frozen=True)
class BackofficeAccess:
    orders: bool
    customers: bool
    sales: bool
    inventory: bool

    @property
    def dashboard(self):
        return self.orders or self.customers or self.sales or self.inventory


def get_access(user):
    def can_view(app, model):
        return user.has_perm(f"{app}.view_{model}") or user.has_perm(f"{app}.change_{model}")

    return BackofficeAccess(
        orders=can_view("orders", "order"),
        customers=can_view("users", "customuser"),
        sales=can_view("payments", "payment"),
        inventory=can_view("products", "product"),
    )
