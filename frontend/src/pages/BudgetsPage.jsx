import { useState } from "react";

import * as api from "../api.js";
import { StatCard } from "../components/StatCard.jsx";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import { EmptyState, ErrorState, StatSkeleton } from "../components/ui/Feedback.jsx";
import { IconAlert, IconCalendar, IconTrash, IconWallet } from "../icons.jsx";
import { formatMoney, formatMonth } from "../format.js";
import useResource from "../useResource.js";

/**
 * Monthly limits, and how much of each has gone.
 *
 * The spending figures come from the same summary the dashboard reads, so the
 * two cannot disagree about what went on food this month.
 *
 * What this page deliberately does not do:
 *
 *   - **Suggest amounts.** A budget is a decision about how somebody wants to
 *     live. Proposing ₹8,000 for food from a spending average is a description
 *     of the past dressed up as advice about the future.
 *   - **Judge.** Over budget is reported as over budget. No scolding, no
 *     "you should", no score.
 *   - **Roll anything over.** A month is a month; carrying an underspend
 *     forward silently would make the number on screen unexplainable.
 */
export default function BudgetsPage({
  choices,
  month,
  dataVersion,
  onError,
  onSuccess,
  onChanged,
}) {
  const progress = useResource(
    () => api.getBudgetProgress({ month }),
    [month, dataVersion]
  );

  const [category, setCategory] = useState("food");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.setBudget({ category, amount: amount.trim() });
      onSuccess("Budget saved.");
      setAmount("");
      progress.reload();
      await onChanged();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  }

  async function remove(item) {
    try {
      await api.deleteBudget(item.id);
      onSuccess(`Budget for ${item.label} removed. No transaction changed.`);
      progress.reload();
      await onChanged();
    } catch (error) {
      onError(error);
    }
  }

  if (progress.loading && !progress.data) return <StatSkeleton count={4} />;

  if (progress.error) {
    return (
      <Card>
        <ErrorState
          title="We couldn't load your budgets"
          error={progress.error}
          onRetry={progress.reload}
        />
      </Card>
    );
  }

  const data = progress.data || {};
  const spendable = (choices || []).filter(
    (entry) => !entry.archived && entry.kind !== "income" && entry.category !== "transfer"
  );

  const form = (
    <Card>
      <CardHead
        title="Set a limit"
        description="One monthly limit per category"
        bordered
      />
      <CardBody>
        <form className="rule-form" onSubmit={save}>
          <div className="field">
            <label htmlFor="budget-category">Category</label>
            <select
              id="budget-category"
              className="select"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              {spendable.map((entry) => (
                <option key={entry.category} value={entry.category}>
                  {entry.emoji ? `${entry.emoji} ` : ""}
                  {entry.label}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="budget-amount">Limit for the month</label>
            <div className="amount-input">
              <span aria-hidden="true">₹</span>
              <input
                id="budget-amount"
                className="input"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                placeholder="8000"
                inputMode="decimal"
                required
              />
            </div>
          </div>

          <Button
            type="submit"
            variant="primary"
            loading={busy}
            disabled={!amount.trim()}
          >
            Save budget
          </Button>
        </form>
      </CardBody>
      <CardFoot>
        Setting a limit for a category you already have one for replaces it.
        Nothing here suggests an amount — the number is entirely yours.
      </CardFoot>
    </Card>
  );

  // No budget set is a different statement from every budget sitting at zero.
  if (!data.available) {
    return (
      <div className="stack">
        <Card>
          <EmptyState
            icon={IconWallet}
            title="No budgets set yet"
            description="Pick a category and a monthly limit. Your spending is already being counted — a budget just holds it next to a number you chose."
          />
        </Card>
        {form}
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="grid-4">
        <StatCard
          label="Budgeted"
          value={formatMoney(data.total_limit)}
          note={`Across ${data.budgets.length} categor${data.budgets.length === 1 ? "y" : "ies"}`}
          icon={IconWallet}
          tone="primary"
        />
        <StatCard
          label="Spent"
          value={formatMoney(data.total_spent)}
          note={formatMonth(data.month)}
          icon={IconCalendar}
        />
        <StatCard
          label="Left"
          value={formatMoney(data.total_remaining)}
          note={
            data.days_left > 0
              ? `${data.days_left} day${data.days_left === 1 ? "" : "s"} to go`
              : "Month finished"
          }
          icon={IconWallet}
          tone="success"
        />
        <StatCard
          label="Over limit"
          value={data.over_count}
          note={
            data.over_count === 0
              ? "Nothing has passed its limit"
              : "Listed first below"
          }
          icon={IconAlert}
          tone={data.over_count > 0 ? "danger" : "neutral"}
        />
      </div>

      <Card>
        <CardHead
          title="This month"
          description="Closest to its limit first"
          bordered
        />
        <CardBody>
          <div className="budget-list">
            {data.budgets.map((item) => (
              <div className="budget-row" key={item.id}>
                <div className="budget-head">
                  <span className="budget-label">{item.label}</span>
                  <span className="budget-figures num">
                    {formatMoney(item.spent)}{" "}
                    <span className="muted">/ {formatMoney(item.limit)}</span>
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={IconTrash}
                    onClick={() => remove(item)}
                    aria-label={`Remove budget for ${item.label}`}
                  />
                </div>

                <div className="budget-track">
                  <div
                    className={`budget-fill budget-${item.state}`}
                    // Capped at 100 so an overspend does not paint outside the
                    // track; the number beside it carries the real figure.
                    style={{ width: `${Math.min(item.share, 100)}%` }}
                  />
                </div>

                <div className="budget-foot">
                  <span className={item.state === "over" ? "over" : "muted"}>
                    {item.state === "over"
                      ? `${formatMoney(item.over_by)} over`
                      : `${formatMoney(item.remaining)} left`}
                  </span>
                  <span className="muted num">{item.share}%</span>
                </div>
              </div>
            ))}
          </div>
        </CardBody>
        <CardFoot>
          Spending comes from the same figures as your dashboard — a budget
          holds one of them next to a limit you set. Budgets do not carry over:
          each month starts again.
        </CardFoot>
      </Card>

      {form}
    </div>
  );
}
