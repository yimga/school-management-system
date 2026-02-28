# Billing and Stripe (Plan X)

## Trial state

- **School.billing_type** = `FREE_TRIAL` for trial tenants.
- **School.trial_end_date**: when the trial ends; middleware or billing job can set `is_frozen` / `frozen_reason=BILLING` when past this date.
- **Super billing dashboard**: `/super/billing/` lists trial schools, trial end date, and usage; link to Usage and Edit school.

## Stripe integration (scaffold)

- **Webhook URL**: `POST /api/v1/billing/stripe-webhook/` (or similar). Configure in Stripe Dashboard to receive `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`.
- **Subscription mapping**: Store `StripeCustomerId` / `StripeSubscriptionId` on School (or TenantBillingProfile) when linking; on webhook, find school by customer_id and update plan, trial_end_date, or set is_frozen.
- **Settings**: Use `STRIPE_WEBHOOK_SECRET` in env; validate signature in webhook view. Map Stripe price/plan IDs to `siteconfig.Plan` or feature flags.
- Implementation: add optional `stripe_customer_id` / `stripe_subscription_id` fields and a webhook view behind a feature flag or integration registry (ServiceIntegration type STRIPE).
