import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatCategory, formatMoney, toNumber } from "../format.js";
import { useChartTheme } from "../theme.js";
import Card, { CardHead, ChartNote } from "./ui/Card.jsx";
import { EmptyState } from "./ui/Feedback.jsx";

/**
 * Spending per category, biggest first.
 *
 * Ranked bars rather than a donut. There are twelve categories and only about
 * eight hues that stay separable for colourblind readers, so a coloured slice
 * per category would be a rainbow whose colours mean nothing. Bars put
 * identity in the axis label, where it is unambiguous, and leave colour one
 * job: magnitude, in a single hue.
 *
 * Clicking a bar filters the transactions table, so the chart is a control as
 * well as a picture. A selected category dims the others rather than hiding
 * them — you need the comparison to know whether your selection is the big one.
 */
export default function CategoryChart({ categories, onSelect, selected }) {
  const { magnitude, chrome, tooltip, cursor } = useChartTheme();

  const data = categories.map((row) => ({
    category: row.category,
    label: formatCategory(row.category),
    total: toNumber(row.total),
    count: row.count,
  }));

  const height = Math.max(220, data.length * 32 + 24);

  return (
    <Card>
      <CardHead
        title="Where the money goes"
        description="Spending by category, largest first"
      />

      <div className="card-body" style={{ paddingTop: "var(--sp-4)" }}>
        {data.length === 0 ? (
          <EmptyState
            title="Nothing to break down yet"
            description="Once transactions are imported, your category split appears here."
          />
        ) : (
          <ResponsiveContainer width="100%" height={height}>
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 0, right: 84, bottom: 0, left: 8 }}
            >
              <CartesianGrid stroke={chrome.grid} horizontal={false} />
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="label"
                width={112}
                tick={{ fill: chrome.secondary, fontSize: 12 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                cursor={cursor}
                formatter={(value, _name, entry) => [
                  `${formatMoney(value)} across ${entry.payload.count} transactions`,
                  entry.payload.label,
                ]}
                contentStyle={tooltip}
              />
              <Bar
                dataKey="total"
                radius={[0, 4, 4, 0]}
                barSize={16}
                // Recharts hands the click either the row itself or a wrapper
                // with the row on .payload, depending on where you hit the bar.
                onClick={(entry) => {
                  const category = entry?.category ?? entry?.payload?.category;
                  if (category && onSelect) onSelect(category);
                }}
                cursor={onSelect ? "pointer" : "default"}
                // Direct value labels: the relief rule for a chart whose fill
                // sits below 3:1 against the surface.
                label={{
                  position: "right",
                  formatter: (value) => formatMoney(value),
                  fill: chrome.secondary,
                  fontSize: 11.5,
                }}
              >
                {data.map((row) => (
                  <Cell
                    key={row.category}
                    fill={magnitude}
                    fillOpacity={selected && selected !== row.category ? 0.3 : 1}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {onSelect && (
        <ChartNote>
          Click a bar to filter the transactions table.
          {selected ? ` Currently showing ${formatCategory(selected)}.` : ""}
        </ChartNote>
      )}
    </Card>
  );
}
