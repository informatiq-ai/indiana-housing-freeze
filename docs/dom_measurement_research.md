# Days-on-market measurement and relisting research

## Finding

There is no defensible national date when agents "began" resetting days on
market (DOM). MLS rules are local, and relisting practices predate consistent
public listing-history data. The earliest strong evidence located for this
project shows the practice was established by **2005**:

- Tucker, Zhang, and Zhu cite a July 2005 *Boston Globe* report about agents
  cancelling and relisting homes to obtain a fresh appearance.
- Massachusetts changed its MLS policy in **2006** to prevent sellers from
  resetting displayed DOM by relisting. The resulting natural experiment is
  direct evidence that DOM manipulation existed before the rule change.
- The published study finds that revealing cumulative marketing time affected
  sale prices and reports that only 62.8% of its small homeowner-survey sample
  understood that relisting could reset displayed DOM.

The appropriate conclusion is therefore **"documented by 2005 and already
important enough to trigger an MLS policy response in 2006,"** not that gaming
began in 2005 or during the pandemic.

## Why the current Redfin DOM series needs qualification

Redfin defines median DOM as the median number of days a home was listed before
going under contract, among homes that went under contract in the period;
listings older than one year are excluded. Redfin separately identifies a
delisting only when a home does not return or sell within 31 days and defines a
relisting as a return between 31 and 365 days. Its public relisting-history data
begin in 2016 because earlier listing histories are incomplete.

This means the county-month `median_dom` field is not documented as a
property-level cumulative DOM measure. It can differ from true total marketing
time when a property receives a new listing identifier, is marketed outside the
MLS, or leaves the market long enough to satisfy a local reset rule. The bias is
not guaranteed to be constant over time or geography.

For Central Indiana, MIBOR's published Market Insights reports explicitly use
**Cumulative Days on Market**, defined as the median days between listing and
purchase-contract dates. MIBOR reported this series at least from January 2020
in its August 2023 report. That is the preferred Indianapolis measure if a
machine-readable historical series can be licensed or reconstructed. The
public MIBOR rules reviewed here require timely status updates and adopted the
Clear Cooperation language in November 2019, but they do not provide enough
public detail to establish the historical DOM/CDOM reset interval.

NAR adopted the Clear Cooperation Policy in November 2019, with local
implementation required by May 1, 2020. It requires public-marketed listings to
enter the MLS within one business day. It improves inventory visibility but is
not a cumulative-DOM rule and should not be treated as the start or end of DOM
resetting.

## Analytical treatment

1. Keep Redfin `median_dom` as a secondary listing-market outcome, labeled
   "reported DOM" rather than true marketing duration.
2. Do not claim that its measurement error necessarily biases estimates
   downward; direction depends on relisting and sample-composition patterns.
3. Obtain MIBOR CDOM or property-level listing histories for the primary
   Indianapolis duration analysis.
4. If property histories become available, construct both current-listing DOM
   and property-level cumulative DOM, then report their difference by county,
   month, price tier, and pre/post-2022 period.
5. Use Redfin's delisting/relisting series (available from 2016) as a diagnostic
   control or sensitivity measure, not as proof of agent intent.

## Sources

- Tucker, Zhang, and Zhu, [“Days on Market and Home Sales,” *RAND Journal of
  Economics* (2013)](https://onlinelibrary.wiley.com/doi/10.1111/1756-2171.12022)
- Redfin, [Housing Market Tracker methodology and metric
  definitions](https://www.redfin.com/news/data-center/methodology/)
- MIBOR, [August 2023 Market Insights report](https://www.mibor.com/wp-content/uploads/2025/05/MIBOR_Market_Insights_Report_2023_08.pdf)
- National Association of REALTORS®, [Summary of 2020 MLS changes and Clear
  Cooperation](https://www.nar.realtor/about-nar/policies/summary-of-2020-mls-changes)
- MIBOR, [BLC Rules and Regulations](https://www.mibor.com/wp-content/uploads/2025/08/BLC-Rules-and-Regulations-8.26.25.pdf)
