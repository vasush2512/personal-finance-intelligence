/**
 * The panel every piece of content sits in.
 *
 * Split into head / body / foot so a chart, a table and a form can share one
 * frame without each re-inventing its padding and its divider.
 */

export default function Card({ children, className = "", ...rest }) {
  return (
    <section className={`card ${className}`} {...rest}>
      {children}
    </section>
  );
}

/**
 * `bordered` draws the rule under the heading. Use it when the body is a table
 * or a list that starts flush; leave it off when the body is prose.
 */
export function CardHead({ title, description, actions, bordered = false, id }) {
  return (
    <header className={`card-head ${bordered ? "bordered" : ""}`}>
      <div>
        <h2 id={id}>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="topbar-actions">{actions}</div>}
    </header>
  );
}

export function CardBody({ children, className = "" }) {
  return <div className={`card-body ${className}`}>{children}</div>;
}

export function CardFoot({ children }) {
  return <footer className="card-foot">{children}</footer>;
}

/** The small print under a chart — what is counted, what is excluded. */
export function ChartNote({ children }) {
  return <p className="chart-note">{children}</p>;
}
