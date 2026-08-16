import * as api from "../api.js";
import { decodeSource } from "../components/Filters.jsx";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import { ErrorState, TableSkeleton } from "../components/ui/Feedback.jsx";
import { IconFile } from "../icons.jsx";
import {
  formatCategory,
  formatDate,
  formatMoney,
  formatMonth,
  toNumber,
} from "../format.js";
import useResource from "../useResource.js";

/**
 * A printable report (§30).
 *
 * PDF is produced by the browser's own print-to-PDF rather than a server-side
 * library, and that is a deliberate trade rather than a shortcut. Generating
 * PDFs on the backend means a new dependency — reportlab or weasyprint — which
 * the house rules say to ask about first; it also means re-implementing this
 * layout a second time in a second language, where it would drift out of step
 * with the page it is supposed to mirror.
 *
 * Printing what is already on screen means one layout, no dependency, and a
 * report that cannot disagree with the app. The print stylesheet drops the
 * navigation and the buttons, so the output is the report and nothing else.
 *
 * Every figure comes from the same endpoints the dashboard uses. Nothing here
 * is recomputed for the report.
 */
export default function ReportPage({ source, month, session, dataVersion }) {
  const query = { month, ...decodeSource(source) };

  const summary = useResource(() => api.getSummary(query), [month, source, dataVersion]);
  const trends = useResource(() => api.getTrends(decodeSource(source)), [source, dataVersion]);
  const anomalies = useResource(() => api.getAnomalies(decodeSource(source)), [source, dataVersion]);
  const recurring = useResource(() => api.getRecurring(decodeSource(source)), [source, dataVersion]);
  const insights = useResource(() => api.getInsights(query), [month, source, dataVersion]);
  const health = useResource(() => api.getFinancialHealth(decodeSource(source)), [source, dataVersion]);
  const quality = useResource(
    () => api.getDataQuality(decodeSource(source)),
    [source, dataVersion]
  );

  const parts = [summary, trends, anomalies, recurring, insights, health, quality];

  if (parts.some((part) => part.loading && !part.data)) {
    return <TableSkeleton rows={8} />;
  }

  const failed = parts.find((part) => part.error);
  if (failed) {
    return (
      <Card>
        <ErrorState
          title="We couldn't build the report"
          error={failed.error}
          onRetry={() => parts.forEach((part) => part.reload())}
        />
      </Card>
    );
  }

  const s = summary.data;
  const scope = month ? formatMonth(month) : "All time";
  const spent = toNumber(s.total_spent);

  return (
    <div className="stack report">
      <Card className="no-print">
        <CardHead
          title="Financial report"
          description={`${scope} · every figure below comes from your own transactions`}
          actions={
            <Button variant="primary" icon={IconFile} onClick={() => window.print()}>
              Print / Save as PDF
            </Button>
          }
        />
        <CardBody>
          <p className="note">
            Choose <strong>Save as PDF</strong> as the destination in the print
            dialog. The navigation, buttons and this note are left out of the
            printed page.
          </p>
        </CardBody>
      </Card>

      <div className="print-header">
        <h1>Financial report</h1>
        <p>
          {scope}
          {session?.email ? ` · ${session.email}` : ""}
        </p>
      </div>

      <Card>
        <CardHead title="Summary" bordered />
        <CardBody>
          <dl className="detail-grid">
            <dt>Total income</dt>
            <dd>{formatMoney(s.total_income)}</dd>
            <dt>Total spending</dt>
            <dd>{formatMoney(s.total_spent)}</dd>
            <dt>Savings</dt>
            <dd>{formatMoney(s.net)}</dd>
            <dt>Savings rate</dt>
            <dd>
              {toNumber(s.total_income) > 0
                ? `${((toNumber(s.net) / toNumber(s.total_income)) * 100).toFixed(1)}%`
                : "—"}
            </dd>
            <dt>Transactions</dt>
            <dd>{s.transaction_count.toLocaleString("en-IN")}</dd>
            <dt>Financial health</dt>
            <dd>
              {health.data?.available
                ? `${health.data.score}/100 · ${health.data.band}`
                : "Not enough history"}
            </dd>
          </dl>
        </CardBody>
        <CardFoot>
          Spending excludes transfers between your own accounts. Refunds are
          counted in their own category, not as income.
        </CardFoot>
      </Card>

      <Section title="Spending by category">
        <Table
          head={["Category", "Transactions", "Total", "Share"]}
          rows={s.by_category.map((row) => [
            formatCategory(row.category),
            row.count.toLocaleString("en-IN"),
            formatMoney(row.total),
            spent ? `${((toNumber(row.total) / spent) * 100).toFixed(1)}%` : "—",
          ])}
        />
      </Section>

      <Section title="Month by month">
        <Table
          head={["Month", "Spent", "Income", "Net"]}
          rows={trends.data.map((point) => [
            formatMonth(point.month),
            formatMoney(point.spent),
            formatMoney(point.income),
            formatMoney(toNumber(point.income) - toNumber(point.spent)),
          ])}
        />
      </Section>

      <Section title="Largest merchants">
        <Table
          head={["Merchant", "Transactions", "Total"]}
          rows={s.top_merchants.map((row) => [
            row.merchant,
            row.count.toLocaleString("en-IN"),
            formatMoney(row.total),
          ])}
        />
      </Section>

      <Section
        title="Unusual transactions"
        empty="Nothing was flagged as unusual."
      >
        <Table
          head={["Date", "Description", "Category", "Amount"]}
          rows={anomalies.data.map((row) => [
            formatDate(row.date),
            row.description.slice(0, 60),
            formatCategory(row.category),
            formatMoney(row.amount),
          ])}
        />
      </Section>

      <Section
        title="Recurring payments"
        empty="No recurring payments were detected."
      >
        <Table
          head={["Merchant", "Frequency", "Typical amount", "Confidence"]}
          rows={(recurring.data?.payments || []).map((row) => [
            row.merchant,
            row.frequency,
            formatMoney(row.average_amount),
            `${row.confidence}%`,
          ])}
        />
      </Section>

      <Section title="Observations" empty="Not enough data for observations.">
        <ul className="report-list">
          {insights.data.map((item) => (
            <li key={item.key}>
              <strong>{item.headline}</strong>
              <br />
              {item.detail}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Data quality">
        <Table
          head={["Check", "Found"]}
          rows={quality.data.issues.map((issue) => [
            issue.title,
            issue.count ? issue.count.toLocaleString("en-IN") : "Clear",
          ])}
        />
      </Section>

      <p className="report-foot">
        Generated from {s.transaction_count.toLocaleString("en-IN")} transactions.
        Every figure is calculated from your own uploaded statements. Nothing in
        this report is estimated, predicted, or advice.
      </p>
    </div>
  );
}

function Section({ title, children, empty }) {
  const isEmpty =
    empty &&
    (!children?.props?.rows?.length &&
      !children?.props?.children?.length);

  return (
    <Card>
      <CardHead title={title} bordered />
      {isEmpty ? (
        <CardBody>
          <p className="muted">{empty}</p>
        </CardBody>
      ) : (
        <div className="table-wrap">{children}</div>
      )}
    </Card>
  );
}

function Table({ head, rows }) {
  return (
    <table className="cards-on-mobile">
      <thead>
        <tr>
          {head.map((cell, index) => (
            <th key={cell} className={index === 0 ? "" : "right"}>
              {cell}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>
            {row.map((cell, cellIndex) => (
              <td
                key={cellIndex}
                data-label={head[cellIndex]}
                className={cellIndex === 0 ? "" : "num right"}
              >
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
