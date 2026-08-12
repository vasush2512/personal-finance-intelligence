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
import { CHROME, MAGNITUDE } from "../theme.js";

/**
 * Spending per category, biggest first.
 *
 * Ranked bars rather than a donut. There are twelve categories and only
 * eight hues that stay separable for colourblind readers, so a coloured
 * slice per category would be a rainbow whose colours mean nothing. Bars put
 * identity in the axis label, where it is unambiguous, and leave colour to
 * do one job: magnitude, in a single hue.
 *
 * Clicking a bar filters the table below it.
 */
export default function CategoryChart({ categories, onSelect, selected }) {
  const data = categories.map((row) => ({
    category: row.category,
    label: formatCategory(row.category),
    total: toNumber(row.total),
    count: row.count,
  }));

  const height = Math.max(200, data.length * 30 + 24);

  return (
    <div className="card">
      <h2>Where the money goes</h2>

      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 0, right: 76, bottom: 0, left: 8 }}
        >
          <CartesianGrid stroke={CHROME.grid} horizontal={false} />
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            width={104}
            tick={{ fill: CHROME.secondary, fontSize: 12.5 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(11,11,11,0.04)" }}
            formatter={(value, _name, entry) => [
              `${formatMoney(value)} across ${entry.payload.count} transactions`,
              entry.payload.label,
            ]}
            contentStyle={{
              borderRadius: 8,
              border: `1px solid ${CHROME.grid}`,
              fontSize: 13,
            }}
          />
          <Bar
            dataKey="total"
            radius={[0, 4, 4, 0]}
            barSize={16}
            // Recharts hands the click either the row itself or a wrapper
            // with the row on .payload, depending on where you hit the bar.
            onClick={(entry) => {
              const category = entry?.category ?? entry?.payload?.category;
              if (category) onSelect(category);
            }}
            cursor="pointer"
            // Direct value labels: the relief rule for a chart whose fill
            // sits below 3:1 against the surface.
            label={{
              position: "right",
              formatter: (value) => formatMoney(value),
              fill: CHROME.secondary,
              fontSize: 12,
            }}
          >
            {data.map((row) => (
              <Cell
                key={row.category}
                fill={MAGNITUDE}
                fillOpacity={selected && selected !== row.category ? 0.35 : 1}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <p className="chart-note">
        Click a bar to filter the table. {selected ? `Showing ${formatCategory(selected)}.` : ""}
      </p>
    </div>
  );
}
