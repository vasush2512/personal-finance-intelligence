import { CategoryChart, TrendChart } from "../components/LazyCharts.jsx";
import AnomaliesPanel from "../components/AnomaliesPanel.jsx";
import SummaryCards from "../components/StatCard.jsx";
import Card, { CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import Badge, { SourceBadge } from "../components/ui/Badge.jsx";
import { EmptyState } from "../components/ui/Feedback.jsx";
import {
  IconActivity,
  IconAlert,
  IconArrowRight,
  categoryEmoji,
} from "../icons.jsx";
import {
  formatCategory,
  formatDate,
  formatMoney,
  formatMoneyExact,
  formatMonth,
  shortenDescription,
  toNumber,
} from "../format.js";
import { navigate } from "../router.js";

const RECENT_COUNT = 6;

/**
 * The overview: four numbers, two charts, and the most recent rows.
 *
 * Ordered by how quickly a glance pays off — totals first, then the shape over
 * time, then the breakdown, then individual rows. Anything that needs reading
 * rather than glancing lives on its own page.
 */
export default function DashboardPage({
  summary,
  trends,
  transactions,
  anomalies,
  health,
  scopeLabel,
  onSelectCategory,
  onOpenTransaction,
}) {
  return (
    <div className="stack">
      <SummaryCards
        summary={summary}
        scopeLabel={scopeLabel}
        anomalyCount={anomalies.length}
        health={health}
      />

      <div className="grid-wide-left">
        <TrendChart trends={trends} />
        <HealthCard health={health} />
      </div>

      <div className="grid-wide-left">
        <CategoryChart
          categories={summary.by_category}
          onSelect={onSelectCategory}
        />
        <div className="stack">
          <NeedsAttention
            anomalies={anomalies}
            summary={summary}
            onOpenTransaction={onOpenTransaction}
          />
          <TopDrivers trends={trends} summary={summary} />
        </div>
      </div>

      <RecentTransactions
        items={transactions.slice(0, RECENT_COUNT)}
        onOpen={onOpenTransaction}
      />

      {anomalies.length > 0 && <AnomaliesPanel anomalies={anomalies} limit={4} />}
    </div>
  );
}

/**
 * The health score, with the components that produced it.
 *
 * The breakdown is not optional decoration: a single number nobody can
 * interrogate gets ignored the first time it disagrees with how someone feels
 * about their own finances.
 */
function HealthCard({ health }) {
  if (!health) return null;

  if (!health.available) {
    return (
      <Card>
        <CardHead title="Financial health" bordered />
        <div className="card-body">
          <EmptyState
            icon={IconActivity}
            title="Not enough history yet"
            description={health.reason}
          />
        </div>
      </Card>
    );
  }

  const tone =
    health.score >= 65 ? "success" : health.score >= 50 ? "warning" : "danger";

  return (
    <Card>
      <CardHead
        title="Financial health"
        description="Scored from your own months of history"
        actions={<Badge tone={tone}>{health.band}</Badge>}
        bordered
      />
      <div className="card-body">
        <div className="score-row">
          <div
            className={`score-ring ${tone === "success" ? "ok" : "warn"}`}
            role="img"
            aria-label={`Financial health ${health.score} out of 100`}
          >
            <strong>{health.score}</strong>
            <span>/100</span>
          </div>
          <p className="prose">
            A summary of what already happened — savings, discipline and
            consistency across {health.components.length} measures. It is not a
            forecast and not a credit rating.
          </p>
        </div>

        <div className="factors">
          {health.components.map((component) => (
            <div className="factor" key={component.key}>
              <div className="factor-head">
                <span>{component.label}</span>
                <strong>{component.value}%</strong>
              </div>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{ width: `${component.value}%` }}
                />
              </div>
              <p className="note">{component.detail}</p>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

/**
 * What changed, and which categories drove it.
 *
 * Compares the most recent month against the average of the months before it,
 * which is the honest comparison when statements cover uneven periods — last
 * month alone could itself have been the unusual one.
 */
function TopDrivers({ trends, summary }) {
  if (trends.length < 2) {
    return (
      <Card>
        <CardHead title="Top spending drivers" bordered />
        <div className="card-body">
          <p className="note">
            Needs at least two months of statements to compare periods.
          </p>
        </div>
      </Card>
    );
  }

  const latest = trends[trends.length - 1];
  const earlier = trends.slice(0, -1);
  const average =
    earlier.reduce((sum, point) => sum + toNumber(point.spent), 0) /
    earlier.length;
  const change = toNumber(latest.spent) - average;
  const percent = average ? (change / average) * 100 : 0;

  // Category-level attribution needs per-month category totals, which
  // /api/summary does not break down — so this shows the categories carrying
  // the most spend rather than inventing a per-category delta.
  const top = summary.by_category.slice(0, 3);

  return (
    <Card>
      <CardHead
        title="Top spending drivers"
        description={`${formatMonth(latest.month)} vs the ${earlier.length}-month average`}
        bordered
      />
      <div className="card-body">
        <p
          className="stat-value"
          style={{
            fontSize: 21,
            color: change > 0 ? "var(--danger)" : "var(--success)",
          }}
        >
          {change > 0 ? "+" : "−"}
          {formatMoney(Math.abs(change))}
          <span className="note" style={{ marginLeft: 8, fontWeight: 400 }}>
            {percent > 0 ? "+" : ""}
            {percent.toFixed(1)}%
          </span>
        </p>

        <div className="factors" style={{ marginTop: "var(--sp-4)" }}>
          {top.map((row) => (
            <div className="factor" key={row.category}>
              <div className="factor-head">
                <span>{formatCategory(row.category)}</span>
                <strong>{formatMoney(row.total)}</strong>
              </div>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{
                    width: `${
                      summary.by_category[0]
                        ? (toNumber(row.total) /
                            toNumber(summary.by_category[0].total)) *
                          100
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

/** Rows worth a second look, each opening its own analysis. */
function NeedsAttention({ anomalies, summary, onOpenTransaction }) {
  const uncategorized =
    summary.by_category_source?.find((entry) => entry.source === "none")?.count || 0;

  const items = [];

  anomalies.slice(0, 3).forEach((anomaly) => {
    items.push({
      key: `anomaly-${anomaly.id}`,
      tone: "warning",
      title: `${formatMoney(anomaly.amount)} on ${formatCategory(anomaly.category)}`,
      detail: anomaly.reason,
      onClick: () => onOpenTransaction?.(anomaly.id),
    });
  });

  if (uncategorized > 0) {
    items.push({
      key: "uncategorized",
      tone: "neutral",
      title: `${uncategorized.toLocaleString("en-IN")} rows uncategorized`,
      detail: "No rule matched and the model was not confident enough to label them.",
      onClick: () => navigate("/transactions"),
    });
  }

  return (
    <Card>
      <CardHead
        title="Needs your attention"
        description={items.length ? undefined : "Nothing outstanding"}
        bordered
      />
      {items.length === 0 ? (
        <div className="card-body">
          <p className="note">
            No unusual transactions and nothing waiting to be categorized.
          </p>
        </div>
      ) : (
        items.map((item) => (
          <button
            key={item.key}
            className="list-row"
            onClick={item.onClick}
            style={{ width: "100%", background: "none", border: "none", cursor: "pointer", textAlign: "left", font: "inherit" }}
          >
            <span
              className="state-icon"
              style={{
                width: 28,
                height: 28,
                flexShrink: 0,
                background:
                  item.tone === "warning" ? "var(--warning-soft)" : "var(--surface-hover)",
                color: item.tone === "warning" ? "var(--warning)" : "var(--text-muted)",
              }}
            >
              <IconAlert size={14} />
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 550, fontSize: 13 }}>{item.title}</div>
              <div className="tile-meta">{item.detail}</div>
            </div>
          </button>
        ))
      )}
    </Card>
  );
}

/**
 * The latest rows, as a list rather than a table.
 *
 * Six rows beside a chart do not need column headers, and the description is
 * the content — so it gets the width, and the amount is the only thing pinned
 * to the right where the eye can compare down the column.
 */
function RecentTransactions({ items, onOpen }) {
  return (
    <Card>
      <CardHead
        title="Recent transactions"
        description="Newest first"
        bordered
        actions={
          <Button size="sm" variant="ghost" onClick={() => navigate("/transactions")}>
            View all
            <IconArrowRight size={14} />
          </Button>
        }
      />

      {items.length === 0 ? (
        <div className="card-body">
          <p className="note">Nothing imported yet.</p>
        </div>
      ) : (
        items.map((transaction) => {
          const credit = transaction.direction === "credit";

          return (
            <div
              className="list-row clickable"
              key={transaction.id}
              role="button"
              tabIndex={0}
              onClick={() => onOpen?.(transaction.id)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen?.(transaction.id); } }}
            >
              <span
                className="tile-icon"
                style={{ background: "var(--surface-hover)", fontSize: 15 }}
                aria-hidden="true"
              >
                {categoryEmoji(transaction.category)}
              </span>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    fontWeight: 550,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={transaction.description}
                >
                  {shortenDescription(transaction.description, 34)}
                </div>
                <div
                  className="tile-meta"
                  style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}
                >
                  {formatCategory(transaction.category)} ·{" "}
                  {formatDate(transaction.date)}
                  <SourceBadge
                    source={transaction.category_source}
                    confidence={transaction.confidence}
                  />
                </div>
              </div>

              <span
                className={`num ${credit ? "amount-in" : "amount-out"}`}
                style={{ whiteSpace: "nowrap" }}
              >
                {credit ? "+" : "−"}
                {formatMoneyExact(transaction.amount)}
              </span>
            </div>
          );
        })
      )}
    </Card>
  );
}
