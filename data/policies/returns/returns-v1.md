# NovaMart demonstration returns policy

Policy version: demo-1.0. Effective reference: 18 October 2026.
This is synthetic policy content for the NovaMart portfolio application.

## Return windows

Standard customers have a 30-day return window from delivery. Premium customers
have a 60-day return window from delivery. The current eligibility service uses
whole elapsed days and rejects an order when elapsed days exceed its tier's window.

## Eligibility requirements

An order must have delivered status, a recorded delivery date that is not in the
future, and its return eligibility flag enabled. An already refunded order is
ineligible. Shipped orders that have not been delivered are ineligible for a
return refund. Missing order or customer information must be retrieved before a
customer-specific eligibility decision can be made.

## Amount and action boundaries

For an eligible order, the demonstrated refund amount is unit price multiplied by
quantity. The application evaluates eligibility; it does not transfer funds,
change the order status, arrange collection, or generate a return label.
Do not tell the customer a refund has been issued based only on this policy.
