# Store Backoffice

Sign in at `/admin65xtz/` with an active staff account and choose **Open store
dashboard**. Backoffice uses the existing Django Admin session and model pages.
The dashboard and Admin use English. Storefront and API language selection
continues to use the shared locale settings.

## Daily work

- **Dashboard** shows an inclusive date range of up to 90 days in the store
  time zone. The default covers today and the previous 29 days. Orders and new
  customer accounts use creation time. Orders requiring attention include
  processing orders, shipped orders awaiting delivery, and unpaid orders with
  expired reservations in that range.
- **Sales** uses the verification date and sums captured IRT amounts for
  verified Payments applied to Orders. Late or duplicate captures that were
  never applied are excluded. This is a gross sales figure before refunds.
- **Order summary** opens from **Printable summary** on an Order in Admin.
  Use **Print summary** or the browser's print command. Customer, shipping, line
  items, and money come from the checkout snapshot. The document is an operational
  order summary. It carries no invoice number or tax invoice status.
- **Customer history** opens from **Purchase history** on a customer record in
  Admin. The page shows that customer's orders, with links back to Admin.
- **Inventory** shows active Products with available stock at or below the
  selected threshold, including zero. The default is five units. Each row links
  to Product Admin.

## Staff roles

Superusers can assign the following permissions through Django Admin Groups.
Use the relevant view permissions for read-only access. Existing change
permissions also grant read access for the same model.

| Role | Minimum permissions for the workflow |
| --- | --- |
| Fulfillment | `orders.view_order` for orders and summaries. Use `orders.change_order` for shipping and delivery actions. |
| Customer support | `users.view_customuser` and `orders.view_order` for customer history. |
| Finance | `payments.view_payment` for verified sales and Payments. Grant `payments.view_refund` separately for the existing Refund list. |
| Inventory | `products.view_product` for low-stock inventory and Product details. |
| SMS support | `notifications.view_smsdelivery` for existing delivery history. Only active staff superusers can re-arm deliveries. |

Delegated staff cannot access privileged customer records or their Orders through
Backoffice. Product API writes require staff status plus the operation's model
permission. Grant catalogue write permissions only to roles that need those
operations. [Product API permissions](api.md#products)

## Actions and audit

Shipping and delivery use the existing Order transition services. Successful
actions appear in the Order's Django Admin history. The order state and its audit
record commit together.

For SMS, select up to 50 records awaiting manual review, choose **Re-arm selected
manual-review SMS deliveries**, and confirm. Eligible deliveries enter the
existing background retry workflow. Retry requires `SMS_ENABLED`, a usable
registered provider for the delivery, and a stored recipient. A retry after a
potential send also requires an idempotent provider. The delivery retains its
attempt history and records the confirmed action in Django Admin history.

Sales and SMS history are available when providers are disabled. Provider setup
is covered in [Deployment](deployment.md#scheduled-work-and-disabled-providers).
For runtime errors, use the request or correlation ID with the existing operator
logs. [Logging and retention](deployment.md#logs-and-retention)
