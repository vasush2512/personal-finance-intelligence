import AnomaliesPanel from "../components/AnomaliesPanel.jsx";
import Card, { CardHead } from "../components/ui/Card.jsx";

/**
 * Flagged spending, plus the rule written out in full.
 *
 * The explanation is on the page rather than in a tooltip because an alert you
 * cannot interrogate gets ignored the second time it is wrong. Someone who can
 * read the threshold can decide for themselves whether a flag is fair.
 */
export default function UnusualPage({ anomalies }) {
  return (
    <div className="stack">
      <AnomaliesPanel anomalies={anomalies} />

      <Card>
        <CardHead title="How a transaction gets flagged" />
        <div className="card-body">
          <p className="prose">
            Within a single category, over the trailing six months, a debit is
            flagged when its amount exceeds the average of the others by more
            than <strong>2.5 standard deviations</strong>. The transaction is
            left out of its own baseline, so one very large charge cannot raise
            the bar it is being measured against.
          </p>
          <p className="prose">
            A category needs at least <strong>eight earlier transactions</strong>{" "}
            before anything in it can be flagged. Below that the average is not
            a description of your habits, it is an accident of which rows
            happened to arrive first.
          </p>
          <p className="prose">
            When every past amount in a category is identical — a fixed
            subscription, say — the standard deviation is zero and no amount
            could ever exceed the threshold. In that case the test falls back to
            1.5× the average, so a genuinely large charge still surfaces.
          </p>
          <p className="prose muted">
            Nothing here is stored. The flag depends on a moving six-month
            window, so it is recomputed on every request — a charge that looks
            extraordinary today stops being one once similar charges arrive.
          </p>
        </div>
      </Card>
    </div>
  );
}
