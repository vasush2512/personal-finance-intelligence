import * as api from "../api.js";
import Card, { CardBody, CardFoot, CardHead } from "./ui/Card.jsx";
import { ErrorState, Skeleton } from "./ui/Feedback.jsx";
import useResource from "../useResource.js";

/**
 * Preferences that change how the app behaves and how figures are written.
 *
 * One of these is not cosmetic. Anomaly sensitivity moves the standard
 * deviation threshold the unusual-spending detector uses, so changing it
 * changes what the Unusual page shows and what the health score counts. The
 * card says so, because a setting that silently alters an analysis is worse
 * than one that does nothing.
 *
 * Each option list comes from the backend rather than being written here, so
 * the two cannot drift apart.
 */
export default function PreferencesCard({ dataVersion, onError, onSuccess, onChanged }) {
  const settings = useResource(() => api.getSettings(), [dataVersion]);
  const options = useResource(() => api.getSettingsOptions(), []);

  async function change(field, value) {
    try {
      const updated = await api.updateSettings({ [field]: value });
      settings.setData(updated);
      onSuccess(SAVED[field] || "Saved.");
      // Sensitivity changes what the detector returns, so everything that
      // reads anomalies is now out of date.
      if (field === "anomaly_sensitivity") await onChanged();
    } catch (error) {
      onError(error);
    }
  }

  if (settings.error || options.error) {
    return (
      <Card>
        <ErrorState
          title="We couldn't load your preferences"
          error={settings.error || options.error}
          onRetry={() => {
            settings.reload();
            options.reload();
          }}
        />
      </Card>
    );
  }

  if (!settings.data || !options.data) {
    return (
      <Card>
        <CardHead title="Preferences" bordered />
        <CardBody>
          <Skeleton width="40%" height={13} />
          <div style={{ height: 12 }} />
          <Skeleton width="70%" height={11} />
        </CardBody>
      </Card>
    );
  }

  const current = settings.data;
  const choices = options.data;

  return (
    <Card>
      <CardHead
        title="Preferences"
        description="How the app reads, and how closely it looks"
        bordered
      />

      <CardBody>
        <div className="pref-row">
          <div className="pref-label">
            <strong>Unusual spending sensitivity</strong>
            <span>
              How far above your normal a transaction has to sit before it is
              flagged. This changes what the Unusual page shows.
            </span>
          </div>
          <div className="segmented" role="radiogroup" aria-label="Sensitivity">
            {choices.anomaly_sensitivity.map((level) => (
              <button
                key={level}
                type="button"
                role="radio"
                aria-checked={current.anomaly_sensitivity === level}
                onClick={() => change("anomaly_sensitivity", level)}
              >
                {SENSITIVITY_LABELS[level] || level}
              </button>
            ))}
          </div>
        </div>

        <p className="note">
          {SENSITIVITY_NOTES[current.anomaly_sensitivity]}
        </p>

        <div className="pref-row">
          <div className="pref-label">
            <strong>Currency</strong>
            <span>
              Changes the symbol on every figure. It does not convert anything —
              your amounts are stored exactly as your statements recorded them.
            </span>
          </div>
          <select
            className="select"
            value={current.currency}
            onChange={(event) => change("currency", event.target.value)}
            aria-label="Currency"
          >
            {choices.currency.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </div>

        <div className="pref-row">
          <div className="pref-label">
            <strong>Date format</strong>
            <span>How dates are written across the app.</span>
          </div>
          <select
            className="select"
            value={current.date_format}
            onChange={(event) => change("date_format", event.target.value)}
            aria-label="Date format"
          >
            {choices.date_format.map((format) => (
              <option key={format} value={format}>
                {DATE_LABELS[format] || format}
              </option>
            ))}
          </select>
        </div>

        <div className="pref-row">
          <div className="pref-label">
            <strong>Dashboard opens on</strong>
            <span>Everything you have imported, or the current month only.</span>
          </div>
          <select
            className="select"
            value={current.default_period}
            onChange={(event) => change("default_period", event.target.value)}
            aria-label="Default period"
          >
            {choices.default_period.map((period) => (
              <option key={period} value={period}>
                {PERIOD_LABELS[period] || period}
              </option>
            ))}
          </select>
        </div>
      </CardBody>

      <CardFoot>
        Sensitivity changes which transactions are shown, not how they were
        recorded. Nothing here edits a transaction, and no figure is recomputed
        differently — the same statistics run against a different threshold.
      </CardFoot>
    </Card>
  );
}

const SENSITIVITY_LABELS = { low: "Low", medium: "Medium", high: "High" };

/** Said plainly, because "2.5 sigma" is not a preference anyone can weigh. */
const SENSITIVITY_NOTES = {
  low: "Only the genuinely extreme is flagged. Fewer prompts, and some unusual spending will pass unremarked.",
  medium: "The default. A transaction is flagged when it sits about 2.5 standard deviations above your normal for its category.",
  high: "More transactions are flagged. Useful if your spending is steady, noisy if it is not — this does not make the detection more accurate, only less selective.",
};

const DATE_LABELS = {
  dmy: "17 Aug 2026",
  mdy: "Aug 17, 2026",
  iso: "2026-08-17",
};

const PERIOD_LABELS = { all: "All time", month: "This month" };

const SAVED = {
  anomaly_sensitivity: "Sensitivity updated. Unusual spending has been recalculated.",
  currency: "Currency updated.",
  date_format: "Date format updated.",
  default_period: "Default period updated.",
};
