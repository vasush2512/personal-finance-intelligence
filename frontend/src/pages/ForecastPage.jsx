import * as api from "../api.js";
import { decodeSource } from "../components/Filters.jsx";
import MonthlyStory from "../components/MonthlyStory.jsx";
import { StatCard } from "../components/StatCard.jsx";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import {
  EmptyState,
  ErrorState,
  StatSkeleton,
  ChartSkeleton,
} from "../components/ui/Feedback.jsx";
import { IconCalendar, IconChart, IconTrendDown, IconWallet } from "../icons.jsx";
import { formatMoney, formatMonth, toNumber } from "../format.js";
import useResource from "../useResource.js";

/**
 * What a month like your recent months would cost.
 *
 * The wording on this page is deliberate throughout. Nothing here says "you
 * will spend" — the honest claim is about months that already happened, and
 * every figure is shown next to the range it came from so the width of the
 * uncertainty is visible rather than implied.
 *
 * The confidence figure is not decoration: below 50 the page says so in words,
 * because a projection built on months that look nothing like each other is
 * worth less than the crispness of a number suggests.
 */
export default function ForecastPage({ source, month, dataVersion }) {
  const forecast = useResource(
    () => api.getForecast(decodeSource(source)),
    [source, dataVersion]
  );

  if (forecast.loading && !forecast.data) {
    return (
      <div className="stack">
        <StatSkeleton count={4} />
        <ChartSkeleton height={180} />
      </div>
    );
  }

  if (forecast.error) {
    return (
      <Card>
        <ErrorState
          title="We couldn't build a projection"
          error={forecast.error}
          onRetry={forecast.reload}
        />
      </Card>
    );
  }

  const data = forecast.data || {};

  if (!data.available) {
    return (
      <div className="stack">
        <Card>
          <EmptyState
            icon={IconChart}
            title="Not enough complete months yet"
            description={
              data.reason ||
              "A projection needs at least three finished months to compare."
            }
          />
        </Card>
        <MonthlyStory source={source} month={month} dataVersion={dataVersion} />
      </div>
    );
  }

  const confidenceTone =
    data.confidence >= 65 ? "success" : data.confidence >= 40 ? "neutral" : "danger";

  return (
    <div className="stack">
      <div className="grid-4">
        <StatCard
          label={`Projected spending · ${formatMonth(data.month)}`}
          value={formatMoney(data.projected_spending)}
          note={`Between ${formatMoney(data.spending_low)} and ${formatMoney(data.spending_high)}`}
          icon={IconTrendDown}
          tone="primary"
        />
        <StatCard
          label="Projected income"
          value={formatMoney(data.projected_income)}
          note={`From the same ${data.months_used} months`}
          icon={IconWallet}
        />
        <StatCard
          label="Projected left over"
          value={formatMoney(data.projected_net)}
          note={
            toNumber(data.projected_net) < 0
              ? "A month like these spends more than it earns"
              : "Income minus spending, both projected"
          }
          icon={IconChart}
          tone={toNumber(data.projected_net) < 0 ? "danger" : "success"}
        />
        <StatCard
          label="How steady the basis is"
          value={`${data.confidence}%`}
          note={
            data.confidence >= 65
              ? "Your recent months resemble each other"
              : "Your months vary a lot — treat the figure loosely"
          }
          icon={IconCalendar}
          tone={confidenceTone}
        />
      </div>

      {data.progress && <Progress progress={data.progress} month={data.month} />}

      <Card>
        <CardHead title="Where this figure comes from" bordered />
        <CardBody>
          <p className="prose">{data.basis}</p>
          <p className="prose">
            The middle month is used rather than the average, so one unusual
            month does not move the baseline for the next six. The range above
            is not a margin of error — it is the actual smallest and largest of
            those months.
          </p>
          {toNumber(data.committed) > 0 && (
            <p className="prose">
              Of a typical month, <strong>{formatMoney(data.committed)}</strong>{" "}
              is recurring payments. That is reported alongside rather than
              added: those payments are already inside the months above.
            </p>
          )}
        </CardBody>
        <CardFoot>
          This describes months that already happened. It is not a prediction —
          a month with a wedding, a repair or a holiday in it will not resemble
          the ones this was built from, and nothing here can know that in
          advance.
        </CardFoot>
      </Card>

      <MonthlyStory source={source} month={month} dataVersion={dataVersion} />
    </div>
  );
}

/**
 * The month in progress against its projection.
 *
 * Deliberately not extrapolated to a month-end figure. "On track for ₹47,000"
 * from six days of data is a guess wearing a number's clothes, and the bar
 * below says only what has actually been spent.
 */
function Progress({ progress, month }) {
  const share = Math.min(progress.share_of_projection, 100);
  const over = progress.share_of_projection > 100;

  return (
    <Card>
      <CardHead
        title={`${formatMonth(month)} so far`}
        description={`${formatMoney(progress.spent_so_far)} spent of a projected ${formatMoney(progress.projected)}`}
        bordered
        actions={
          <span className={`badge badge-${over ? "warning" : "neutral"}`}>
            {progress.share_of_projection}% of the projection
          </span>
        }
      />
      <CardBody>
        <div className="progress-track" style={{ height: 10 }}>
          <div
            className="progress-fill"
            style={{
              width: `${share}%`,
              background: over ? "var(--warning)" : "var(--primary)",
            }}
          />
        </div>
        <p className="chart-note">
          {over
            ? `This month has already passed the projection by ${formatMoney(
                toNumber(progress.spent_so_far) - toNumber(progress.projected)
              )}.`
            : `${formatMoney(progress.remaining)} below the projection so far. This is what has been spent, not an estimate of where the month will end.`}
        </p>
      </CardBody>
    </Card>
  );
}
