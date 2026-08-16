import * as api from "../api.js";
import { decodeSource } from "./Filters.jsx";
import Card, { CardBody, CardFoot, CardHead } from "./ui/Card.jsx";
import { EmptyState, Skeleton } from "./ui/Feedback.jsx";
import { IconBulb } from "../icons.jsx";
import useResource from "../useResource.js";

/**
 * Plain-English observations about the figures already on the page.
 *
 * Deliberately not called insights-from-AI, because nothing here is generated:
 * each line is a sentence template filled from one arithmetic result, and each
 * one carries the comparison it came from in its second line. If a figure
 * cannot be computed honestly — a month-on-month change with only one month of
 * data — the observation is simply absent rather than hedged.
 *
 * A failure here is silent by design. This panel sits under charts that are
 * already correct and complete; an error banner across it would suggest the
 * page above it is broken too.
 */
export default function InsightsPanel({ month, source, dataVersion }) {
  const insights = useResource(
    () => api.getInsights({ month, ...decodeSource(source) }),
    [month, source, dataVersion]
  );

  if (insights.error) return null;

  return (
    <Card>
      <CardHead
        title="What stands out"
        description="Calculated from the figures on this page — no estimates, no predictions"
        bordered
      />

      <CardBody>
        {insights.loading && !insights.data ? (
          <div className="insight-list">
            {[0, 1, 2].map((index) => (
              <div className="insight" key={index}>
                <Skeleton width="14px" height={14} radius="50%" />
                <div style={{ flex: 1 }}>
                  <Skeleton width="55%" height={13} />
                  <div style={{ height: 8 }} />
                  <Skeleton width="80%" height={10} />
                </div>
              </div>
            ))}
          </div>
        ) : (insights.data || []).length === 0 ? (
          <EmptyState
            icon={IconBulb}
            title="Nothing worth calling out yet"
            description="Observations need at least a couple of months of data to compare against."
          />
        ) : (
          <div className="insight-list">
            {insights.data.map((insight) => (
              <div className={`insight insight-${insight.tone}`} key={insight.key}>
                <span className="insight-dot" aria-hidden="true" />
                <div>
                  <strong>{insight.headline}</strong>
                  <p>{insight.detail}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardBody>

      <CardFoot>
        Each line above is one calculation over your own transactions, with the
        numbers behind it shown. None of it is a forecast, and none of it is
        advice.
      </CardFoot>
    </Card>
  );
}
