import {
  Area,
  AreaChart,
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
import { useChartTheme } from "../theme.js";
import Card, { CardHead, ChartNote } from "./ui/Card.jsx";
import { EmptyState } from "./ui/Feedback.jsx";

/**
 * Spend and income per month.
 *
 * Both series share one axis on purpose. A second y-scale would let the two
 * be drawn at whatever relative height flattered the data, which is the most
 * common way a chart lies.
 *
 * `variant="area"` is the same data as a filled line, used on the Analytics
 * page where the shape over time is the question. Bars are used on the
 * dashboard, where comparing two values within a month is the question.
 */
export default function TrendChart({
  trends,
  variant = "bar",
  title = "Monthly trend",
  description = "Spending and income for every month your statements cover",
}) {
  const { series, chrome, tooltip, cursor } = useChartTheme();

  const data = trends.map((point) => ({
    month: formatMonth(point.month),
    Spent: toNumber(point.spent),
    Income: toNumber(point.income),
  }));

  const axes = (
    <>
      <CartesianGrid stroke={chrome.grid} vertical={false} />
      <XAxis
        dataKey="month"
        tick={{ fill: chrome.muted, fontSize: 11.5 }}
        axisLine={{ stroke: chrome.axis }}
        tickLine={false}
        // Drop labels rather than let "Sep 2025" collide on a narrow window.
        minTickGap={16}
      />
      <YAxis
        tick={{ fill: chrome.muted, fontSize: 11.5 }}
        axisLine={false}
        tickLine={false}
        width={72}
        tickFormatter={(value) => formatMoney(value)}
      />
      <Tooltip
        cursor={cursor}
        formatter={(value, name) => [formatMoney(value), name]}
        contentStyle={tooltip}
      />
      <Legend
        wrapperStyle={{ fontSize: 12, color: chrome.secondary, paddingTop: 8 }}
        iconType="circle"
        iconSize={8}
      />
    </>
  );

  return (
    <Card>
      <CardHead title={title} description={description} />

      <div className="card-body" style={{ paddingTop: "var(--sp-4)" }}>
        {data.length === 0 ? (
          <EmptyState
            title="Not enough data yet"
            description="Upload a statement to generate your monthly trend."
          />
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            {variant === "area" ? (
              <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  {/* A soft fill under each line so overlapping series stay
                      readable where they cross. */}
                  <linearGradient id="fill-spent" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={series.spent} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={series.spent} stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="fill-income" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={series.income} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={series.income} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                {axes}
                <Area
                  type="monotone"
                  dataKey="Spent"
                  stroke={series.spent}
                  strokeWidth={2}
                  fill="url(#fill-spent)"
                />
                <Area
                  type="monotone"
                  dataKey="Income"
                  stroke={series.income}
                  strokeWidth={2}
                  fill="url(#fill-income)"
                />
              </AreaChart>
            ) : (
              <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                {axes}
                <Bar dataKey="Spent" fill={series.spent} radius={[4, 4, 0, 0]} barSize={13} />
                <Bar dataKey="Income" fill={series.income} radius={[4, 4, 0, 0]} barSize={13} />
              </BarChart>
            )}
          </ResponsiveContainer>
        )}
      </div>

      <ChartNote>
        Transfers between your own accounts are excluded from both series.
      </ChartNote>
    </Card>
  );
}
