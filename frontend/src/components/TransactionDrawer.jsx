import { useEffect, useRef, useState } from "react";

import * as api from "../api.js";
import {
  categoryEmoji,
  IconAlert,
  IconCheckCircle,
  IconX,
} from "../icons.jsx";
import {
  formatCategory,
  formatDate,
  formatMoney,
  formatMoneyExact,
} from "../format.js";
import Badge, { SourceBadge } from "./ui/Badge.jsx";
import Button from "./ui/Button.jsx";
import { ErrorState, Skeleton } from "./ui/Feedback.jsx";

/**
 * One transaction, opened from the table.
 *
 * A drawer rather than a modal: the list stays visible behind it, so working
 * through several flagged rows does not mean losing your place each time.
 *
 * The analysis is fetched when the drawer opens, not with the list — it costs
 * a query over six months of the category, and fifty rows nobody opened would
 * pay that fifty times.
 */
export default function TransactionDrawer({
  transactionId,
  categories,
  onClose,
  onChangeCategory,
  savingId,
}) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const closeRef = useRef(null);
  const previouslyFocused = useRef(null);

  useEffect(() => {
    if (!transactionId) return undefined;

    let cancelled = false;
    setLoading(true);
    setError(null);
    setDetail(null);

    api
      .getTransaction(transactionId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((failure) => {
        if (!cancelled) setError(failure);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [transactionId]);

  // Escape closes, focus moves in on open and back to the row on close.
  useEffect(() => {
    if (!transactionId) return undefined;

    previouslyFocused.current = document.activeElement;
    closeRef.current?.focus();

    function onKeyDown(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused.current?.focus?.();
    };
  }, [transactionId, onClose]);

  if (!transactionId) return null;

  return (
    <div className="drawer-scrim" onClick={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Transaction detail"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer-head">
          <h2>Transaction</h2>
          <Button
            ref={closeRef}
            variant="ghost"
            size="sm"
            icon={IconX}
            onClick={onClose}
            aria-label="Close transaction detail"
          />
        </header>

        <div className="drawer-body">
          {loading && <DetailSkeleton />}
          {error && <ErrorState error={error} />}
          {detail && (
            <Detail
              detail={detail}
              categories={categories}
              onChangeCategory={onChangeCategory}
              saving={savingId === detail.id}
            />
          )}
        </div>
      </aside>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div style={{ display: "grid", gap: "var(--sp-4)" }}>
      <Skeleton height={28} width="55%" />
      <Skeleton height={40} width="40%" />
      <Skeleton height={90} />
      <Skeleton height={160} />
    </div>
  );
}

function Detail({ detail, categories, onChangeCategory, saving }) {
  const credit = detail.direction === "credit";
  const analysis = detail.anomaly;

  return (
    <>
      <div className="drawer-hero">
        <span className="tile-icon" style={{ background: "var(--surface-hover)" }}>
          {categoryEmoji(detail.category)}
        </span>
        <div style={{ minWidth: 0 }}>
          <h3 className="drawer-merchant">{detail.merchant}</h3>
          <p className="note">{formatDate(detail.date)}</p>
        </div>
      </div>

      <p className={`drawer-amount ${credit ? "amount-in" : ""}`}>
        {credit ? "+" : "−"}
        {formatMoneyExact(detail.amount)}
      </p>

      {detail.is_anomaly && (
        <Badge tone="warning" dot>
          Unusual — requires review
        </Badge>
      )}

      <dl className="detail-grid">
        <Row label="Category">
          <span style={{ display: "inline-flex", gap: "var(--sp-2)", alignItems: "center" }}>
            {formatCategory(detail.category)}
            <SourceBadge
              source={detail.category_source}
              confidence={detail.confidence}
            />
          </span>
        </Row>
        <Row label="Payment method">{detail.payment_method || "Not stated"}</Row>
        <Row label="Type">{credit ? "Money in" : "Money out"}</Row>
        {detail.sheet_name && <Row label="Worksheet">{detail.sheet_name}</Row>}
      </dl>

      {/* The bank's own words, kept verbatim. The merchant above is derived
          from this, and anyone checking the derivation needs the source. */}
      <section className="drawer-section">
        <h4>Original description</h4>
        <p className="mono-block">{detail.description}</p>
        <h4 style={{ marginTop: "var(--sp-3)" }}>Normalized</h4>
        <p className="mono-block">{detail.normalized_description || "—"}</p>
      </section>

      {analysis && <Analysis analysis={analysis} detail={detail} />}

      <section className="drawer-section">
        <h4>Change category</h4>
        <p className="note" style={{ marginBottom: "var(--sp-2)" }}>
          Your correction is permanent — neither the rules nor the model will
          overwrite it, and it becomes training data on the next retrain.
        </p>
        <div style={{ display: "flex", gap: "var(--sp-2)", alignItems: "center" }}>
          <label className="visually-hidden" htmlFor="drawer-category">
            Category
          </label>
          <select
            id="drawer-category"
            className="select"
            value={detail.category}
            disabled={saving}
            onChange={(event) => onChangeCategory(detail.id, event.target.value)}
          >
            {categories.map((entry) => (
              <option key={entry.category} value={entry.category}>
                {formatCategory(entry.category)}
              </option>
            ))}
          </select>
          {saving && <span className="btn-spinner" />}
        </div>
      </section>
    </>
  );
}

/**
 * Why this was, or was not, flagged.
 *
 * Every number here is arithmetic on the user's own transactions, which is why
 * the working is shown rather than a verdict. Nothing on this panel calls the
 * transaction fraudulent — unusual and wrong are different claims, and only one
 * of them is supported by a standard deviation.
 */
function Analysis({ analysis, detail }) {
  if (!analysis.available) {
    return (
      <section className="drawer-section">
        <h4>Spending analysis</h4>
        <p className="note">{analysis.reason}</p>
      </section>
    );
  }

  const amount = Number(detail.amount);
  const baseline = Number(analysis.baseline);
  const widest = Math.max(amount, baseline) || 1;

  return (
    <section className="drawer-section">
      <h4>
        {detail.is_anomaly ? "Why this was flagged" : "How this compares"}
      </h4>

      <div className="score-row">
        <div
          className={`score-ring ${detail.is_anomaly ? "warn" : "ok"}`}
          role="img"
          aria-label={`Anomaly score ${analysis.score} out of 100`}
        >
          <strong>{analysis.score}</strong>
          <span>/100</span>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span
            className="state-icon"
            style={{
              width: 26,
              height: 26,
              float: "left",
              marginRight: "var(--sp-2)",
              background: detail.is_anomaly ? "var(--warning-soft)" : "var(--success-soft)",
              color: detail.is_anomaly ? "var(--warning)" : "var(--success)",
            }}
          >
            {detail.is_anomaly ? <IconAlert size={13} /> : <IconCheckCircle size={13} />}
          </span>
          <p className="prose">{analysis.explanation}</p>
        </div>
      </div>

      {/* The comparison the sentence describes, drawn to scale. */}
      <div className="compare">
        <div className="compare-row">
          <span>This transaction</span>
          <div className="compare-track">
            <div
              className="compare-fill current"
              style={{ width: `${(amount / widest) * 100}%` }}
            />
          </div>
          <strong>{formatMoney(amount)}</strong>
        </div>
        <div className="compare-row">
          <span>Your usual {formatCategory(detail.category).toLowerCase()}</span>
          <div className="compare-track">
            <div
              className="compare-fill usual"
              style={{ width: `${(baseline / widest) * 100}%` }}
            />
          </div>
          <strong>{formatMoney(baseline)}</strong>
        </div>
      </div>

      <h4 style={{ marginTop: "var(--sp-4)" }}>Score breakdown</h4>
      <div className="factors">
        {analysis.factors.map((factor) => (
          <div className="factor" key={factor.key}>
            <div className="factor-head">
              <span>{factor.label}</span>
              <strong>{factor.value}%</strong>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${factor.value}%` }} />
            </div>
            <p className="note">{factor.detail}</p>
          </div>
        ))}
      </div>

      <p className="note" style={{ marginTop: "var(--sp-3)" }}>
        Compared against {analysis.peer_count} transactions in this category over
        the last {analysis.lookback_days} days. This is a statistical comparison,
        not a fraud check.
      </p>
    </section>
  );
}

function Row({ label, children }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}
