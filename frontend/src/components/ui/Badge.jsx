/**
 * A small label that carries state.
 *
 * Two uses in this app: the category on a transaction row, and who assigned
 * it. The second one matters more than it looks — "rule", "model" and "user"
 * are the difference between a category you can trust and one you should
 * check, so they are visually distinct rather than three grey pills.
 */
export default function Badge({ tone = "neutral", dot = false, children }) {
  return (
    <span className={`badge badge-${tone}`}>
      {dot && <span className="dot" />}
      {children}
    </span>
  );
}

/**
 * Who decided this row's category.
 *
 * A model label carries its confidence, because "model" alone invites equal
 * trust in a 56% guess and a 99% one.
 */
export function SourceBadge({ source, confidence }) {
  const tones = { rule: "neutral", model: "primary", user: "success" };
  const percent =
    source === "model" && confidence != null
      ? ` ${Math.round(confidence * 100)}%`
      : "";

  return (
    <Badge tone={tones[source] || "neutral"}>
      {source}
      {percent}
    </Badge>
  );
}
