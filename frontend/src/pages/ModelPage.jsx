import { useState } from "react";

import * as api from "../api.js";

/**
 * Who labelled your transactions, and retraining.
 *
 * The honest caveat about the accuracy figure is on the page rather than
 * buried in a README, because this is the screen where someone reads that
 * number and decides what it means.
 */
export default function ModelPage({ summary, onRetrained, onError }) {
  const [retraining, setRetraining] = useState(false);
  const [report, setReport] = useState(null);

  const labellers = summary.by_category_source;
  const total = labellers.reduce((sum, entry) => sum + entry.count, 0) || 1;

  const explanations = {
    rule: "Matched a keyword rule — Swiggy, rent, Blinkit.",
    model: "No rule matched, so the classifier decided. Confident enough to commit.",
    user: "You corrected it. Never overwritten, and used as training data.",
  };

  async function retrain() {
    setRetraining(true);
    try {
      const result = await api.retrainModel();
      setReport(result);
      await onRetrained();
    } catch (error) {
      onError(error);
    } finally {
      setRetraining(false);
    }
  }

  return (
    <>
      <div className="card">
        <h2>Who labelled your transactions</h2>

        <div className="cards">
          {labellers.map((entry) => (
            <div key={entry.source}>
              <div className="stat-label">{entry.source}</div>
              <div className="stat-value">
                {entry.count.toLocaleString("en-IN")}
              </div>
              <div className="stat-note">
                {Math.round((entry.count / total) * 100)}% —{" "}
                {explanations[entry.source]}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h2>Retrain</h2>

        <p className="prose">
          Training fits a classifier on every row a rule or you have labelled.
          It is what makes your corrections count: fix a few rows, retrain,
          and the model stops repeating that mistake on merchants it has
          never seen.
        </p>

        <button className="primary" onClick={retrain} disabled={retraining}>
          {retraining ? "Training…" : "Retrain the model"}
        </button>

        {report && (
          <div className="report">
            <div className="report-row">
              <span>Held-out accuracy</span>
              <strong>{(report.holdout_accuracy * 100).toFixed(1)}%</strong>
            </div>
            <div className="report-row">
              <span>Labelled rows trained on</span>
              <strong>{report.labelled_rows.toLocaleString("en-IN")}</strong>
            </div>
            <div className="report-row">
              <span>Categories it can predict</span>
              <strong>{report.classes.length}</strong>
            </div>
          </div>
        )}

        <p className="chart-note">
          Training needs at least 50 labelled rows, and refuses below that
          rather than reporting a number built on nothing.
        </p>
      </div>

      <div className="card">
        <h2>What the accuracy figure actually measures</h2>

        <p className="prose">
          It measures <strong>agreement with the keyword rules, not
          correctness</strong>. The training labels came from those rules, so
          the model is being scored on how well it reproduces them. That is
          what weak supervision buys you: coverage, not ground truth.
        </p>
        <p className="prose">
          The number only becomes a measure of correctness once enough rows in
          the <em>user</em> column above exist to evaluate against. Every
          correction you make moves it closer to meaning something.
        </p>
        <p className="prose muted">
          The same applies to rule coverage on the sample data. The file that
          wrote the keyword rules also invented the sample's merchants, so of
          course they match. On a real statement expect roughly 60–75%.
        </p>
      </div>
    </>
  );
}
