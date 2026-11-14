-- Net revenue must equal gross minus refunds every day, and totals must match invoices.
select revenue_date
from {{ ref('fct_revenue_daily') }}
where abs(net_revenue_usd - (gross_revenue_usd - refunds_usd)) > 0.005
union all
select null
from (
    select
        (select sum(net_revenue_usd) from {{ ref('fct_revenue_daily') }}) as mart_total,
        (select coalesce(sum(amount_usd), 0) from {{ ref('stg_invoices') }}) as invoice_total
)
where abs(mart_total - invoice_total) > 0.01
