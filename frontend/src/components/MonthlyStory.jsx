import * as api from "../api.js";
import { decodeSource } from "./Filters.jsx";
import Card, { CardBody, CardFoot, CardHead } from "./ui/Card.jsx";
import { EmptyState, Skeleton } from "./ui/Feedback.jsx";
import { IconFile } from "../icons.jsx";
import useResource from "../useResource.js";

/**
 * A month written out, rather than shown as boxes.
 *
 * The dashboard already has the same figures in cards. This exists because a
 * sentence carries the relationship between two of them in a way four separate
 * cards do not — "that is more than came in, so the difference came out of what
 * you already had" lands differently from a red minus sign.
 *
 * Every sentence is a template filled from a figure computed on the backend.
 * Nothing is generated in the language-model sense, and there is no advice in
 * it — the footer says so plainly, because a page of confident prose about
 * someone's money invites exactly that assumption.
 */
export default function MonthlyStory({ source, month, dataVersion }) {
  const story = useResource(
    () => api.getStory({ month, ...decodeSource(source) }),
    [month, source, dataVersion]
  );

  if (story.error) return null;

  if (story.loading && !story.data) {
    return (
      <Card>
        <CardHead title="Your month in words" bordered />
        <CardBody>
          <Skeleton width="35%" height={13} />
          <div style={{ height: 12 }} />
          <Skeleton width="92%" height={11} />
          <div style={{ height: 8 }} />
          <Skeleton width="78%" height={11} />
        </CardBody>
      </Card>
    );
  }

  const data = story.data || {};

  if (!data.available) {
    return (
      <Card>
        <CardHead title="Your month in words" bordered />
        <CardBody>
          <EmptyState
            icon={IconFile}
            title="Nothing to write about yet"
            description={data.reason || "Upload a statement to see a month described."}
          />
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHead
        title={`${data.title} in words`}
        description="The same figures as the dashboard, written as sentences"
        bordered
      />
      <CardBody>
        {data.paragraphs.map((paragraph, index) => (
          // Index as key is safe here: the list is regenerated whole on every
          // fetch and never reordered or edited in place.
          <p className="prose" key={index}>
            {paragraph}
          </p>
        ))}
      </CardBody>
      <CardFoot>
        Written from figures already computed on this data — no estimates, no
        predictions, and no advice about what to do next.
      </CardFoot>
    </Card>
  );
}
