import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatMoney, formatMonth, toNumber } from "../format.js";
import { CHROME, SERIES } from "../theme.js";

/**
 * Spend and income per month.
 *
 * Both series share one axis on purpose. A second y-scale would let the two
 * bars be drawn at whatever relative height flattered the data, which is the
 * most common way a chart lies.
 */
export default function TrendChart({ trends }) {
  const data = trends.map((point) => ({
    month: formatMonth(point.month),
    Spent: toNumber(point.spent),
    Income: toNumber(point.income),
  }));

  return (
    <div className="card">
      <h2>Monthly trend</h2>

      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid stroke={CHROME.grid} vertical={false} />
          <XAxis
            dataKey="month"
            tick={{ fill: CHROME.muted, fontSize: 12 }}
            axisLine={{ stroke: CHROME.axis }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: CHROME.muted, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={64}
            tickFormatter={(value) => formatMoney(value)}
          />
          <Tooltip
            cursor={{ fill: "rgba(11,11,11,0.04)" }}
            formatter={(value, name) => [formatMoney(value), name]}
            contentStyle={{
              borderRadius: 8,
              border: `1px solid ${CHROME.grid}`,
              fontSize: 13,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: CHROME.secondary }} />
          {/* 2px gap between adjacent bars, rounded data-ends on the baseline */}
          <Bar dataKey="Spent" fill={SERIES.spent} radius={[4, 4, 0, 0]} barSize={14} />
          <Bar dataKey="Income" fill={SERIES.income} radius={[4, 4, 0, 0]} barSize={14} />
        </BarChart>
      </ResponsiveContainer>

      <p className="chart-note">Transfers between your own accounts are excluded.</p>
    </div>
  );
}
