import { useState } from "react";

import * as api from "../api.js";
import { decodeSource } from "../components/Filters.jsx";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import Badge from "../components/ui/Badge.jsx";
import ConfirmDialog from "../components/ui/Modal.jsx";
import { StatCard } from "../components/StatCard.jsx";
import { EmptyState, ErrorState, StatSkeleton } from "../components/ui/Feedback.jsx";
import { IconRefresh, IconSparkles, IconTags } from "../icons.jsx";
import { formatCategory, formatDate, formatMoney } from "../format.js";
import useResource from "../useResource.js";

/**
 * What is labelling your transactions, how sure it is, and what you corrected.
 *
 * The figures come from /api/model/stats rather than from the dashboard
 * summary, and the difference matters: the summary reports the
 * category_source column verbatim, and that column still says 'rule' on fifty
 * thousand rows no rule ever matched. This endpoint reports where the label
 * actually came from, which is why the coverage figure here is lower — and
 * correct.
 *
 * There is no headline accuracy number anywhere on this page. See the last
 * card for why that is a deliberate omission rather than an oversight.
 */
export default function ModelPage({ source, dataVersion, onRetrained, onError }) {
  const [retraining, setRetraining] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [report, setReport] = useState(null);

  const stats = useResource(
    () => api.getModelStats(decodeSource(source)),
    [source, dataVersion]
  );
  const corrections = useResource(
    () => api.getFeedback({ limit: 10, ...decodeSource(source) }),
    [source, dataVersion]
  );

  async function retrain() {
    setConfirming(false);
    setRetraining(true);
    try {
      const result = await api.retrainModel();
      setReport(result);
      stats.reload();
      await onRetrained();
    } catch (error) {
      onError(error);
    } finally {
      setRetraining(false);
    }
  }

  if (stats.loading && !stats.data) return <StatSkeleton count={4} />;

  if (stats.error) {
    return (
      <Card>
        <ErrorState
          title="We couldn't read the model status"
          error={stats.error}
          onRetry={stats.reload}
        />
      </Card>
    );
  }

  const data = stats.data;
  const total = data.total_transactions || 1;
  const labelled = data.by_source
    .filter((entry) => entry.source !== "none")
    .reduce((sum, entry) => sum + entry.count, 0);
  const coverage = Math.round((labelled / total) * 100);
  const userCount =
    data.by_source.find((entry) => entry.source === "user")?.count || 0;

  return (
    <div className="stack">
      <Card>
        <CardHead
          title="Model status"
          description="The classifier runs on every import, after the keyword rules"
          actions={
            <Badge tone={data.model_trained ? "success" : "warning"} dot>
              {retraining ? "Training" : data.model_trained ? "Trained" : "Not trained"}
            </Badge>
          }
          bordered
        />

        <CardBody>
          <p className="prose">
            Training fits a classifier on every row a rule or you have labelled.
            It is what makes your corrections count: fix a few rows, retrain,
            and the model stops repeating that mistake on merchants it has never
            seen.
          </p>

          <div className="pair-actions" style={{ borderTop: "none", paddingTop: 0 }}>
            <Button
              variant="primary"
              icon={IconRefresh}
              loading={retraining}
              disabled={!data.can_train}
              onClick={() => setConfirming(true)}
            >
              {retraining ? "Training…" : "Retrain model"}
            </Button>
          </div>

          {!data.can_train && (
            <p className="note">
              Training needs at least {data.min_training_rows} rule- or
              user-labelled rows and refuses below that, rather than reporting a
              number built on nothing. You have{" "}
              {data.trainable_rows.toLocaleString("en-IN")}.
            </p>
          )}

          {report && (
            <div className="grid-3" style={{ marginTop: "var(--sp-5)" }}>
              <StatCard
                label="Agreement with the rules"
                value={`${(report.holdout_accuracy * 100).toFixed(1)}%`}
                note="Not accuracy — see the last card"
                icon={IconSparkles}
                tone="primary"
              />
              <StatCard
                label="Rows trained on"
                value={report.labelled_rows.toLocaleString("en-IN")}
                note="Rule- and user-labelled rows"
              />
              <StatCard
                label="Categories predicted"
                value={report.classes.length}
                note={report.classes.map(formatCategory).slice(0, 3).join(", ") + "…"}
              />
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHead
          title="Who labelled your transactions"
          description={`${coverage}% of ${total.toLocaleString("en-IN")} rows carry a category something actually recognised.`}
          bordered
        />
        <CardBody>
          <div className="grid-4">
            {data.by_source.map((entry) => (
              <LabellerCard key={entry.source} entry={entry} />
            ))}
          </div>

          {data.stale_rule_rows > 0 && (
            <p className="note">
              <strong>{data.stale_rule_rows.toLocaleString("en-IN")} rows</strong>{" "}
              are stored with the label <code>rule</code> but were never matched
              by one — they date from before the app distinguished "no rule
              matched" from "a rule matched". They are counted above as{" "}
              <em>nothing matched</em>, which is what they are. Nothing has been
              changed in your database to achieve that.
            </p>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHead
          title="How sure the classifier was"
          description={`Only rows the classifier labelled. Below ${Math.round(data.confidence_threshold * 100)}% it declines to answer.`}
          bordered
        />
        <CardBody>
          {data.confidence_buckets.every((bucket) => bucket.count === 0) ? (
            <EmptyState
              icon={IconSparkles}
              title="The classifier has not labelled anything yet"
              description="Either every row matched a keyword rule, or the model has not run on this data."
            />
          ) : (
            <div className="factors">
              {data.confidence_buckets.map((bucket) => (
                <div key={bucket.label}>
                  <div className="factor-head">
                    <span>
                      {bucket.label}{" "}
                      <span className="muted">
                        ({Math.round(bucket.low * 100)}–{Math.round(bucket.high * 100)}%)
                      </span>
                    </span>
                    <strong>{bucket.count.toLocaleString("en-IN")}</strong>
                  </div>
                  <div className="bar-track">
                    <div
                      className="bar-fill"
                      style={{
                        width: `${bucketShare(bucket, data.confidence_buckets)}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          <p className="note">
            <strong>{data.abstentions.toLocaleString("en-IN")}</strong> rows were
            looked at and left alone, because no answer cleared{" "}
            {Math.round(data.confidence_threshold * 100)}%. That is the model
            working as intended — an abstention is not an error, and counting it
            as one is how a coverage figure starts flattering itself.
          </p>
        </CardBody>
      </Card>

      <CorrectionsCard corrections={corrections} confusions={data.corrections} />

      <Card>
        <CardHead title="Why there is no accuracy figure on this page" />
        <CardBody>
          <p className="prose">
            The one number a page like this usually leads with would measure{" "}
            <strong>agreement with the keyword rules, not correctness</strong>.
            The training labels came from those rules, so the model is scored on
            how well it reproduces them. That is what weak supervision buys you:
            coverage, not ground truth.
          </p>
          <p className="prose">
            It only becomes a measure of correctness once enough rows carry a
            label a person chose. You have{" "}
            <strong>{userCount.toLocaleString("en-IN")}</strong> so far. Every
            correction you make moves it closer to meaning something — which is
            the real reason the corrections above are worth making.
          </p>
        </CardBody>
        <CardFoot>
          Rule coverage on sample data flatters itself too: the file that wrote
          the keyword rules also invented the sample's merchants. On a real
          statement expect roughly 60–75%.
        </CardFoot>
      </Card>

      <ConfirmDialog
        open={confirming}
        title="Retrain the model?"
        confirmLabel="Retrain now"
        onCancel={() => setConfirming(false)}
        onConfirm={retrain}
      >
        <p>
          The classifier will be refitted on every rule- and user-labelled row
          currently in your data, then saved over the existing model.
        </p>
        <p style={{ marginTop: "var(--sp-3)" }}>
          Existing categories are not changed by this. The new model applies to
          rows imported from now on.
        </p>
      </ConfirmDialog>
    </div>
  );
}

function bucketShare(bucket, all) {
  const largest = Math.max(...all.map((entry) => entry.count));
  return largest ? (bucket.count / largest) * 100 : 0;
}

const EXPLANATIONS = {
  rule: "Matched a keyword rule — Swiggy, rent, Blinkit.",
  model: "No rule matched, so the classifier decided and was sure enough to commit.",
  user: "You corrected it. Never overwritten, and used as training data.",
  none: "Nothing recognised it. Left as 'other' — these are the rows worth correcting.",
};

const TONES = {
  rule: "neutral",
  model: "primary",
  user: "success",
  // Amber, not red: an unlabelled row is a gap to fill, not a failure.
  none: "warning",
};

function LabellerCard({ entry }) {
  return (
    <div className="card stat">
      <div className="stat-top">
        <span className="stat-label">{entry.label}</span>
        <Badge tone={TONES[entry.source]}>{entry.share}%</Badge>
      </div>
      <div className="stat-value">{entry.count.toLocaleString("en-IN")}</div>
      <div className="stat-note">{EXPLANATIONS[entry.source]}</div>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${entry.share}%` }} />
      </div>
    </div>
  );
}

/**
 * What you corrected, and what it says about the labeller you overruled.
 *
 * The confusion list is the useful half: which wrong answer the classifier
 * keeps giving is far more actionable than a single score, because it names
 * the merchants worth writing a rule for.
 */
function CorrectionsCard({ corrections, confusions }) {
  const recent = corrections.data || [];

  return (
    <Card>
      <CardHead
        title="Your corrections"
        description={
          confusions.total > 0
            ? `${confusions.total.toLocaleString("en-IN")} recorded. Each one is training data for the next retrain.`
            : "Change a category anywhere in the app and it is recorded here."
        }
        bordered
      />
      <CardBody>
        {recent.length === 0 ? (
          <EmptyState
            icon={IconTags}
            title="No corrections yet"
            description="Open any transaction and change its category. The change is stored, used the next time the model is trained, and never overwritten."
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="cards-on-mobile">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Merchant</th>
                    <th className="right">Amount</th>
                    <th>Changed</th>
                    <th>Had been set by</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((row) => (
                    <tr key={row.id}>
                      <td className="num" data-label="Date">{formatDate(row.date)}</td>
                      <td data-label="Merchant">
                        <span className="merchant-name">{row.merchant}</span>
                      </td>
                      <td className="num right" data-label="Amount">
                        {formatMoney(row.amount)}
                      </td>
                      <td data-label="Changed">
                        <span className="muted">
                          {formatCategory(row.from_category)}
                        </span>{" "}
                        → <strong>{formatCategory(row.to_category)}</strong>
                      </td>
                      <td data-label="Had been set by">
                        {EXPLANATIONS[row.from_source] ? row.from_source : "—"}
                        {row.confidence_before != null && (
                          <span className="muted">
                            {" "}
                            at {Math.round(row.confidence_before * 100)}%
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {confusions.confusions.length > 0 && (
              <>
                <h4 className="section-title">
                  What the classifier keeps getting wrong
                </h4>
                <div className="chips">
                  {confusions.confusions.map((pair) => (
                    <span
                      className="chip"
                      key={`${pair.from_category}-${pair.to_category}`}
                    >
                      {formatCategory(pair.from_category)} →{" "}
                      {formatCategory(pair.to_category)} · {pair.count}×
                    </span>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </CardBody>
      <CardFoot>
        A correction to a row the classifier was confident about is a worse sign
        than one it was unsure about, which is why the confidence it had is kept
        next to each change.
      </CardFoot>
    </Card>
  );
}
