import { formatMoney } from "../format.js";
import {
  IconActivity,
  IconAlert,
  IconPercent,
  IconReceipt,
  IconTrendDown,
  IconTrendUp,
  IconWallet,
} from "../icons.jsx";

/**
 * One headline number.
 *
 * The icon tint carries meaning and nothing else: money in is green, money out
 * is neutral (spending is not an error), and the balance takes the colour of
 * its own sign, because that sign is the entire point of the card.
 */
export function StatCard({ label, value, note, icon: Icon, tone = "neutral" }) {
  const tints = {
    neutral: { bg: "var(--surface-hover)", fg: "var(--text-secondary)" },
    primary: { bg: "var(--primary-soft)", fg: "var(--primary)" },
    success: { bg: "var(--success-soft)", fg: "var(--success)" },
    danger: { bg: "var(--danger-soft)", fg: "var(--danger)" },
  };
  const tint = tints[tone] || tints.neutral;

  return (
    <div className="card stat">
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        {Icon && (
          <span
            className="stat-icon"
            style={{ background: tint.bg, color: tint.fg }}
          >
            <Icon size={15} />
          </span>
        )}
      </div>
      <div
        className={`stat-value ${
          tone === "success" ? "positive" : tone === "danger" ? "negative" : ""
        }`}
      >
        {value}
      </div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

/**
 * The four numbers that open the dashboard.
 *
 * Balance is derived by the backend (`net`), not recomputed here — two places
 * doing the same arithmetic is two places to disagree.
 */
export default function SummaryCards({
  summary,
  scopeLabel,
  anomalyCount = 0,
  health,
}) {
  const net = Number(summary.net);
  const income = Number(summary.total_income);

  // Meaningless without income on record — an em dash rather than a confident
  // 100% when nothing came in.
  const savingsRate = income > 0 ? (net / income) * 100 : null;

  return (
    <div className="grid-4">
      <StatCard
        label="Total Income"
        value={formatMoney(summary.total_income)}
        note={scopeLabel}
        icon={IconTrendUp}
        tone="success"
      />
      <StatCard
        label="Total Spending"
        value={formatMoney(summary.total_spent)}
        note={`${scopeLabel} · transfers excluded`}
        icon={IconTrendDown}
        tone="neutral"
      />
      <StatCard
        label="Savings"
        value={formatMoney(summary.net)}
        note="Income minus spending"
        icon={IconWallet}
        tone={net < 0 ? "danger" : "success"}
      />
      <StatCard
        label="Savings Rate"
        value={savingsRate === null ? "—" : `${savingsRate.toFixed(1)}%`}
        note={savingsRate === null ? "Needs recorded income" : "Share of income kept"}
        icon={IconPercent}
        tone={savingsRate !== null && savingsRate < 0 ? "danger" : "success"}
      />
      <StatCard
        label="Unusual"
        value={anomalyCount.toLocaleString("en-IN")}
        note={
          anomalyCount === 0
            ? "Nothing flagged this period"
            : "Transactions worth reviewing"
        }
        icon={IconAlert}
        tone={anomalyCount > 0 ? "danger" : "neutral"}
      />
      <StatCard
        label="Transactions"
        value={summary.transaction_count.toLocaleString("en-IN")}
        note={scopeLabel}
        icon={IconReceipt}
        tone="primary"
      />
      {health && (
        <StatCard
          label="Financial Health"
          value={health.available ? `${health.score}/100` : "—"}
          note={health.available ? health.band : "Not enough history"}
          icon={IconActivity}
          tone={
            !health.available
              ? "neutral"
              : health.score >= 65
                ? "success"
                : health.score >= 50
                  ? "neutral"
                  : "danger"
          }
        />
      )}
    </div>
  );
}
