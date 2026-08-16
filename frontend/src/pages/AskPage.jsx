import { useRef, useState } from "react";

import * as api from "../api.js";
import { decodeSource } from "../components/Filters.jsx";
import Card, { CardBody, CardFoot, CardHead } from "../components/ui/Card.jsx";
import Button from "../components/ui/Button.jsx";
import { IconSearch } from "../icons.jsx";
import { formatCategory, formatMoney } from "../format.js";
import { navigate } from "../router.js";

/**
 * Ask a question about your transactions.
 *
 * Not called an assistant, and not badged as AI, because there is no model
 * behind it: it recognises a fixed set of question shapes by keyword and runs
 * the same aggregations the dashboard runs. The page says so in as many words.
 * Labelling this "AI-powered" would be the easiest lie in the whole project and
 * the one most likely to be believed.
 *
 * Two things travel with every answer:
 *   - the sentence naming exactly what was counted, because answering a
 *     *different* question well is the failure mode of an interface like this;
 *   - a link to the rows behind it, so the number can be checked rather than
 *     trusted.
 */
export default function AskPage({ source, onFilterChange, onError }) {
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [result, setResult] = useState(null);
  const inputRef = useRef(null);

  async function ask(text) {
    const asked = (text ?? question).trim();
    if (!asked) return;

    setQuestion(asked);
    setAsking(true);
    try {
      setResult(await api.ask(asked, decodeSource(source)));
    } catch (error) {
      onError(error);
    } finally {
      setAsking(false);
      inputRef.current?.focus();
    }
  }

  /** Show the rows the answer was computed from. */
  function showRows() {
    const filters = result.filters || {};
    onFilterChange({
      month: filters.month || "",
      category: filters.category || "",
      direction: filters.direction || "",
      search: "",
      source: "",
    });
    navigate("/transactions");
  }

  return (
    <div className="stack">
      <Card>
        <CardHead
          title="Ask about your transactions"
          description="Matches a fixed set of question shapes and runs a real query"
          bordered
        />
        <CardBody>
          <form
            className="ask-form"
            onSubmit={(event) => {
              event.preventDefault();
              ask();
            }}
          >
            <div className="search-field">
              <IconSearch size={15} />
              <input
                ref={inputRef}
                className="input"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="How much did I spend on food in June?"
                maxLength={300}
                aria-label="Your question"
              />
            </div>
            <Button type="submit" variant="primary" loading={asking}>
              Ask
            </Button>
          </form>

          <div className="ask-examples">
            {EXAMPLES.map((example) => (
              <button
                type="button"
                className="chip chip-button"
                key={example}
                onClick={() => ask(example)}
                disabled={asking}
              >
                {example}
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      {result && (
        <Answer result={result} onShowRows={showRows} onAsk={ask} />
      )}

      <Card>
        <CardHead title="How this works, and what it is not" />
        <CardBody>
          <p className="prose">
            This is <strong>keyword matching, not a language model</strong>.
            Your question is checked against a fixed list of shapes — how much
            did I spend, what is my biggest category, who do I pay the most —
            and mapped onto the same filters the Transactions page uses. There
            is no AI here, and nothing is generated.
          </p>
          <p className="prose">
            That is why a question it cannot place comes back refused rather
            than answered. Guessing would produce a confident, well-formatted
            answer to a question you did not ask, and you would have no way to
            tell.
          </p>
        </CardBody>
        <CardFoot>
          Every answer is computed by the same functions that produce the
          dashboard, so the two can never disagree.
        </CardFoot>
      </Card>
    </div>
  );
}

/** Kept here rather than fetched: they are the parser's contract, not data. */
const EXAMPLES = [
  "How much did I spend last month?",
  "How much did I spend on food in June?",
  "What is my biggest category?",
  "Who do I pay the most?",
  "What was my largest transaction?",
  "How many transactions do I have?",
];

function Answer({ result, onShowRows, onAsk }) {
  // Understood, but there is nothing to answer from. Distinct from a question
  // that could not be placed, and distinct again from an answer of zero —
  // "₹0" reads as "you spent nothing", which is not what is being said.
  if (result.no_data) {
    return (
      <Card>
        <CardHead title={result.question} description={result.explanation} bordered />
        <CardBody>
          <p className="ask-answer">{result.reason}</p>
        </CardBody>
      </Card>
    );
  }

  if (!result.understood) {
    return (
      <Card>
        <CardHead
          title="I can't work out what that is asking"
          description={result.reason}
          bordered
        />
        <CardBody>
          <p className="note">Questions like these do work:</p>
          <div className="ask-examples">
            {(result.examples || []).map((example) => (
              <button
                type="button"
                className="chip chip-button"
                key={example}
                onClick={() => onAsk(example)}
              >
                {example}
              </button>
            ))}
          </div>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHead
        title={result.question}
        description={result.explanation}
        bordered
        actions={
          <Button size="sm" variant="secondary" onClick={onShowRows}>
            Show these rows
          </Button>
        }
      />
      <CardBody>
        <p className="ask-answer">{result.answer}</p>

        {result.rows.length > 0 && (
          <div className="table-wrap">
            <table className="cards-on-mobile">
              <tbody>
                {result.rows.map((row) => (
                  <tr key={row.label}>
                    <td data-label="Item">
                      <span className="merchant-name">
                        {maybeCategory(row.label)}
                      </span>
                    </td>
                    <td className="num right" data-label="Total">
                      {formatMoney(row.value)}
                    </td>
                    <td className="muted right" data-label="Detail">
                      {row.detail}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
      <CardFoot>
        The sentence above the answer says exactly what was counted. If it
        describes a different question from the one you asked, the number is
        answering that one.
      </CardFoot>
    </Card>
  );
}

/** Category keys arrive lowercased with underscores; merchants do not. */
function maybeCategory(label) {
  return label.includes("_") ? formatCategory(label) : label;
}
