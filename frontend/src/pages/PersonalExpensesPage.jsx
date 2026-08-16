import { useState } from "react";

import * as api from "../api.js";
import { StatCard } from "../components/StatCard.jsx";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import ConfirmDialog from "../components/ui/Modal.jsx";
import { EmptyState, ErrorState, StatSkeleton } from "../components/ui/Feedback.jsx";
import {
  IconCalendar,
  IconReceipt,
  IconTrash,
  IconTrendDown,
  IconWallet,
} from "../icons.jsx";
import { formatCategory, formatDate, formatMoney, toNumber } from "../format.js";
import useResource from "../useResource.js";

/**
 * Everything recorded by hand, and the fastest way to record more.
 *
 * The figures here come from the same aggregations the dashboard uses, scoped
 * to manual rows. There is no separate arithmetic anywhere — a manual entry is
 * an ordinary transaction, and this page is a view of them rather than a
 * second system.
 *
 * Rows are grouped by day rather than listed flat. Personal spending is
 * remembered by day ("what did I spend yesterday"), not by row number, and a
 * flat list of forty coffees answers a question nobody asked.
 */
export default function PersonalExpensesPage({
  categories,
  accounts,
  dataVersion,
  onAdd,
  onOpenTransaction,
  onError,
  onSuccess,
  onChanged,
}) {
  const summary = useResource(() => api.getManualSummary(), [dataVersion]);
  const page = useResource(
    () => api.getTransactions({ entry_source: "manual", limit: 100 }),
    [dataVersion]
  );
  const templates = useResource(() => api.getQuickExpenses(), [dataVersion]);

  const [usingId, setUsingId] = useState(null);
  const [confirming, setConfirming] = useState(null);

  async function useTemplate(template) {
    setUsingId(template.id);
    try {
      await api.useQuickExpense(template.id);
      onSuccess(`Recorded ${template.name} — ${formatMoney(template.amount)}.`);
      await onChanged();
    } catch (error) {
      onError(error);
    } finally {
      setUsingId(null);
    }
  }

  async function remove(row) {
    setConfirming(null);
    try {
      await api.deleteManual(row.id);
      onSuccess("Transaction deleted.");
      await onChanged();
    } catch (error) {
      onError(error);
    }
  }

  if (summary.loading && !summary.data) return <StatSkeleton count={4} />;

  if (summary.error) {
    return (
      <Card>
        <ErrorState
          title="We couldn't load your personal expenses"
          error={summary.error}
          onRetry={summary.reload}
        />
      </Card>
    );
  }

  const stats = summary.data || {};
  const rows = page.data?.items || [];
  const quick = templates.data || [];

  // Nothing recorded yet is a different statement from "you spent ₹0", and
  // the page says the first rather than showing the second.
  if (!stats.available) {
    return (
      <div className="stack">
        <Card>
          <EmptyState
            icon={IconWallet}
            title="Nothing recorded by hand yet"
            description="Track spending that never reaches a bank statement — cash, a shared bill, a UPI payment you want to log straight away. Everything you add here joins your dashboard, analytics and forecast like any other transaction."
            action={
              <Button variant="primary" onClick={onAdd}>
                Add your first expense
              </Button>
            }
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="grid-4">
        <StatCard
          label="Today"
          value={formatMoney(stats.today_total)}
          note="Recorded by hand today"
          icon={IconCalendar}
          tone="primary"
        />
        <StatCard
          label="This month"
          value={formatMoney(stats.month_total)}
          note={`${stats.month_count} transaction${stats.month_count === 1 ? "" : "s"}`}
          icon={IconTrendDown}
        />
        <StatCard
          label="Average a day"
          value={formatMoney(stats.average_daily)}
          note="Across the days you recorded something"
          icon={IconWallet}
        />
        <StatCard
          label="Largest"
          value={formatMoney(stats.largest)}
          note={`${stats.total_count} recorded in total`}
          icon={IconReceipt}
        />
      </div>

      {quick.length > 0 && (
        <Card>
          <CardHead
            title="Quick add"
            description="One tap records it, dated today"
            bordered
          />
          <CardBody>
            <div className="quick-grid">
              {quick.map((template) => (
                <button
                  type="button"
                  key={template.id}
                  className="quick-tile"
                  onClick={() => useTemplate(template)}
                  disabled={usingId !== null}
                >
                  <span className="quick-emoji" aria-hidden="true">
                    {template.emoji || "＋"}
                  </span>
                  <span className="quick-name">{template.name}</span>
                  <span className="quick-amount">
                    {formatMoney(template.amount)}
                  </span>
                  <span className="quick-category">
                    {formatCategory(template.category)}
                  </span>
                </button>
              ))}
            </div>
          </CardBody>
          <CardFoot>
            A template is not a transaction. Nothing about it appears in any
            total until you press it.
          </CardFoot>
        </Card>
      )}

      <Card>
        <CardHead
          title="Recorded by hand"
          description={`${stats.total_count} transaction${stats.total_count === 1 ? "" : "s"}`}
          bordered
          actions={
            <Button variant="primary" size="sm" onClick={onAdd}>
              + Add
            </Button>
          }
        />

        {rows.length === 0 ? (
          <CardBody>
            <p className="muted">Nothing in this period.</p>
          </CardBody>
        ) : (
          <CardBody>
            {groupByDay(rows).map(([day, entries]) => (
              <div className="day-group" key={day}>
                <div className="day-head">
                  <span>{dayLabel(day)}</span>
                  <span className="num">{formatMoney(dayTotal(entries))}</span>
                </div>

                {entries.map((row) => (
                  <div className="day-row" key={row.id}>
                    <button
                      type="button"
                      className="day-main"
                      onClick={() => onOpenTransaction(row.id)}
                    >
                      <span className="merchant-name">{row.merchant}</span>
                      <span className="day-meta">
                        {formatCategory(row.category)}
                        {row.payment_method ? ` · ${row.payment_method}` : ""}
                      </span>
                      {row.tags.length > 0 && (
                        <span className="chips">
                          {row.tags.map((tag) => (
                            <span className="chip" key={tag}>
                              #{tag}
                            </span>
                          ))}
                        </span>
                      )}
                    </button>

                    <span
                      className={`num ${row.direction === "credit" ? "amount-in" : "amount-out"}`}
                    >
                      {row.direction === "credit" ? "+" : "−"}
                      {formatMoney(row.amount)}
                    </span>

                    <Button
                      size="sm"
                      variant="ghost"
                      icon={IconTrash}
                      onClick={() => setConfirming(row)}
                      aria-label={`Delete ${row.merchant}`}
                    />
                  </div>
                ))}
              </div>
            ))}
          </CardBody>
        )}

        <CardFoot>
          These are ordinary transactions. They appear in your dashboard,
          analytics, forecast and exports alongside everything imported from a
          statement — use the source filter to see them apart.
        </CardFoot>
      </Card>

      <ConfirmDialog
        open={Boolean(confirming)}
        title="Delete this transaction?"
        confirmLabel="Delete"
        onCancel={() => setConfirming(null)}
        onConfirm={() => remove(confirming)}
      >
        <p>
          {confirming && (
            <>
              {formatMoney(confirming.amount)} at {confirming.merchant} on{" "}
              {formatDate(confirming.date)}.
            </>
          )}
        </p>
        <p style={{ marginTop: "var(--sp-3)" }}>
          You recorded this by hand, so it can be removed. Transactions imported
          from a statement cannot — those go with the file they came from.
        </p>
      </ConfirmDialog>
    </div>
  );
}

/** [[date, rows], ...] newest day first. The API already sorts by date. */
function groupByDay(rows) {
  const days = new Map();
  rows.forEach((row) => {
    if (!days.has(row.date)) days.set(row.date, []);
    days.get(row.date).push(row);
  });
  return [...days.entries()];
}

function dayTotal(entries) {
  return entries.reduce(
    (total, row) =>
      row.direction === "credit"
        ? total - toNumber(row.amount)
        : total + toNumber(row.amount),
    0
  );
}

/** "Today" and "Yesterday" are how people actually refer to recent days. */
function dayLabel(date) {
  const now = new Date();
  const iso = (offset) => {
    const day = new Date(now);
    day.setDate(day.getDate() - offset);
    return day.toISOString().slice(0, 10);
  };

  if (date === iso(0)) return "Today";
  if (date === iso(1)) return "Yesterday";
  return formatDate(date);
}
