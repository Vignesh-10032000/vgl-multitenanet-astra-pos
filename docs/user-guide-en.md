# VGL POS user guide (English)

All images use synthetic training data. Your screen may show fewer actions because permissions are role-based.

## Sign in and start work

![VGL POS sign-in screen](images/login-en.png)

Enter the company code, username and password supplied by your administrator. Choose the assigned branch and terminal when prompted. Never share passwords or MFA codes. Open a shift and enter the physical opening cash by denomination before billing.

## Dashboard and checkout

![Operations dashboard](images/dashboard-en.png)

The dashboard shows sales and operational summaries for your permitted branch. Investigate warnings rather than changing old documents.

![Point-of-sale billing screen](images/pos-en.png)

Scan a barcode or search a product, confirm quantity, select the customer when needed, and use Quote to verify the server-calculated total. Add cash/card/UPI/loyalty tenders; only cash can fund change. Complete once and wait for the receipt. If connectivity fails, continue in offline mode and keep the queue until synchronization succeeds—do not re-enter bills.

Hold a bill when the customer pauses. Recall it later; stock and price are revalidated. Returns must reference the original sale. Cancellations, excessive discounts, receipt reprints and shift variances require manager approval and a reason.

## Reports and GST compliance

![Durable report jobs](images/reports-en.png)

Choose a report, period and output format. Large exports become durable jobs; refresh until Completed, then download. Failed jobs retain an error for an authorized operator to retry.

![E-invoice compliance queue](images/compliance-en.png)

Accountants should review pending/dead-letter e-invoices, reconciliation issues and e-way bills daily. Retry only after correcting the shown problem. IRN cancellation is time-limited and audited. Validate GSTR-1 JSON/XLSX in the government Offline Utility and import Tally XML into a trial company before filing or production import.

## Close shift

Count cash without looking at expected cash, enter denomination totals, resolve held bills, and submit. A variance above the company threshold requires manager approval and a reason. Print or retain the Z-report according to store policy.
