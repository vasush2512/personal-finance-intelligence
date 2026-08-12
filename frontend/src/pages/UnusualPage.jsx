import AnomaliesPanel from "../components/AnomaliesPanel.jsx";

/**
 * Flagged spending, and an honest account of how the flag is decided.
 *
 * The method is on the page deliberately. An alert you cannot interrogate
 * gets ignored the second time it is wrong, so the rule is written out where
 * the results are.
 */
export default function UnusualPage({ anomalies }) {
  return (
    <>
      <AnomaliesPanel anomalies={anomalies} />

      <div className="card">
        <h2>How this works</h2>
        <p className="prose">
          Within each category, over the trailing six months, a debit is
          flagged when it exceeds the category average by more than 2.5
          standard deviations. A category needs at least eight earlier
          transactions before anything in it can be flagged — below that the
          average means nothing.
        </p>
        <p className="prose">
          The transaction being judged is left out of its own baseline, so a
          single huge charge cannot quietly raise the bar it is measured
          against. Where a category is a fixed subscription and the spread is
          zero, a ratio test takes over so a genuinely large charge still
          fires.
        </p>
        <p className="prose">
          Each category is judged against itself. Rent being large is normal;
          food being rent-sized is not.
        </p>
        <p className="prose">
          This is recalculated on every visit rather than stored. The window
          moves, so today's outlier stops being one once similar charges
          arrive — a stored flag would go stale and nothing would recompute
          it.
        </p>
        <p className="prose muted">
          Plain statistics, not an anomaly-detection model. You need a reason
          you can read, and the method has to be explainable without
          hand-waving.
        </p>
      </div>
    </>
  );
}
