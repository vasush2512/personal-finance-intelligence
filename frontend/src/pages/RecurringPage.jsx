import * as api from "../api.js";
import { decodeSource } from "../components/Filters.jsx";
import { StatCard } from "../components/StatCard.jsx";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import {
  EmptyState,
  ErrorState,
  StatSkeleton,
  TableSkeleton,
} from "../components/ui/Feedback.jsx";
import { IconCalendar, IconRepeat, IconWallet } from "../icons.jsx";
import {
  formatCategory,
  formatDate,
  formatMoney,
  formatMoneyExact,
  toNumber,
} from "../format.js";
import useResource from "../useResource.js";

/**
 * Merchants being paid on a regular rhythm.
 *
 * What makes something recurring here is the regularity of the gaps, not how
 * often a merchant appears. Three trips to the same restaurant in a month are
 * frequent and not recurring; four payments 30 days apart are recurring even
 * though there are fewer of them. That distinction is the whole detector.
 *
 * Confidence is shown on every row, and a next date is shown only above 60 —
 * an expected date attached to a weak signal reads as a commitment the data
 * cannot back.
 */
export default function RecurringPage({ source, dataVersion }) {
  const recurring = useResource(
    () => api.getRecurring(decodeSource(source)),
    [source, dataVersion]
  );

  if (recurring.loading && !recurring.data) {
    return (
      <div className="stack">
        <StatSkeleton count={3} />
        <TableSkeleton rows={5} />
      </div>
    );
  }

  if (recurring.error) {
    return (
      <Card>
        <ErrorState
          title="We couldn't look for recurring payments"
          error={recurring.error}
          onRetry={recurring.reload}
        />
      </Card>
    );
  }

  const {
    payments = [],
    monthly_total: monthlyTotal = "0.00",
    // The window is the backend's to decide; this is only a fallback so the
    // sentences below never read "the last NaN months".
    lookback_days: lookbackDays = 730,
  } = recurring.data || {};

  if (payments.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={IconRepeat}
          title="No recurring payments detected"
          description={
            `Nothing in the last ${Math.round(lookbackDays / 30)} months repeats on a ` +
            "regular enough schedule to call it recurring. A subscription needs at " +
            "least three payments at consistent intervals before it can be told apart " +
            "from simply shopping somewhere often."
          }
        />
      </Card>
    );
  }

  const upcoming = payments
    .filter((payment) => payment.next_expected)
    .sort((a, b) => a.next_expected.localeCompare(b.next_expected));

  const predicted = upcoming.reduce(
    (total, payment) => total + toNumber(payment.average_amount),
    0
  );

  return (
    <div className="stack">
      <div className="grid-4">
        <StatCard
          label="Monthly commitment"
          value={formatMoney(monthlyTotal)}
          note="Every rhythm converted to its monthly equivalent"
          icon={IconWallet}
          tone="primary"
        />
        <StatCard
          label="Recurring payments"
          value={payments.length.toLocaleString("en-IN")}
          note={`Found across the last ${Math.round(lookbackDays / 30)} months`}
          icon={IconRepeat}
        />
        <StatCard
          label="Next expected"
          value={upcoming.length ? formatDate(upcoming[0].next_expected) : "—"}
          note={
            upcoming.length
              ? `${upcoming[0].merchant} · ${formatMoney(upcoming[0].average_amount)}`
              : "No date is confident enough to show"
          }
          icon={IconCalendar}
        />
        <StatCard
          label="Due in the next cycle"
          value={upcoming.length ? formatMoney(predicted) : "—"}
          note={
            upcoming.length
              ? `${upcoming.length} payment${upcoming.length === 1 ? "" : "s"} with a confident date`
              : "Needs more history"
          }
          icon={IconCalendar}
        />
      </div>

      <Card>
        <CardHead
          title="Detected rhythms"
          description="Highest confidence first"
          bordered
          actions={
            <Button
              variant="secondary"
              onClick={recurring.reload}
              loading={recurring.loading}
            >
              Re-check
            </Button>
          }
        />

        <div className="table-wrap">
          <table className="cards-on-mobile">
            <thead>
              <tr>
                <th>Merchant</th>
                <th>Category</th>
                <th className="right">Typical amount</th>
                <th>Frequency</th>
                <th className="right">Seen</th>
                <th>Last paid</th>
                <th>Next expected</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((payment) => (
                <tr key={`${payment.merchant}-${payment.typical_gap_days}`}>
                  <td data-label="Merchant">
                    <span className="merchant-name">{payment.merchant}</span>
                  </td>
                  <td data-label="Category">
                    {payment.category ? formatCategory(payment.category) : "—"}
                  </td>
                  <td className="num right" data-label="Typical amount">
                    {formatMoneyExact(payment.average_amount)}
                    {/* Said plainly rather than hidden: an average is a poor
                        description of a bill that moves every month. */}
                    {payment.amount_varies && (
                      <span className="muted"> · varies</span>
                    )}
                  </td>
                  <td data-label="Frequency">
                    {payment.frequency}
                    <span className="muted"> · ~{payment.typical_gap_days}d</span>
                  </td>
                  <td className="num right" data-label="Seen">
                    {payment.occurrences}×
                  </td>
                  <td className="num" data-label="Last paid">
                    {formatDate(payment.last_date)}
                  </td>
                  <td className="num" data-label="Next expected">
                    {payment.next_expected ? (
                      formatDate(payment.next_expected)
                    ) : (
                      <span className="muted" title="Intervals are too irregular for a date to mean anything">
                        —
                      </span>
                    )}
                  </td>
                  <td data-label="Confidence">
                    <ConfidenceBar value={payment.confidence} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <CardFoot>
          Confidence combines how regular the intervals are, how steady the
          amount is, and how many payments there are to go on. It is a measure
          of how clear the pattern is — not a promise that the next payment will
          happen. An expected date is only shown at 60% and above.
        </CardFoot>
      </Card>

      <Card>
        <CardHead title="How this is worked out" />
        <CardBody>
          <p className="prose">
            Every debit in the last {Math.round(lookbackDays / 30)} months is
            grouped by merchant. Groups with at least three payments have the
            gaps between them measured; if those gaps are consistent, the group
            is named for the rhythm closest to it — weekly, monthly, quarterly
            and so on.
          </p>
          <p className="prose">
            The monthly commitment above converts each rhythm to what it costs
            per month, so a ₹1,200 yearly renewal counts as ₹100 and not ₹1,200.
            Income is excluded: a salary arriving every month is regular, but it
            is not something you are paying.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}

/** A bar and its number. The bar is for scanning, the number for reading. */
function ConfidenceBar({ value }) {
  const tone = value >= 75 ? "success" : value >= 60 ? "primary" : "muted";

  return (
    <span className="confidence">
      <span className="confidence-track">
        <span
          className={`confidence-fill confidence-${tone}`}
          style={{ width: `${Math.max(value, 3)}%` }}
        />
      </span>
      <span className="num confidence-value">{value}%</span>
    </span>
  );
}
