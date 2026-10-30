'use client';

import React, { useState } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { MetricHistory } from '@/lib/types';
import { TrendingUp, Clock, Calendar } from 'lucide-react';

interface GemsChartProps {
  data: MetricHistory[];
  accountLabel: string;
}

export function GemsTimeSeriesChart({ data, accountLabel }: GemsChartProps) {
  const [timeframe, setTimeframe] = useState<'24h' | '7d'>('24h');

  // Filter or format points
  const points = data.map((d) => ({
    time: new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    gems: d.gems_balance,
    stock: d.stock_remaining,
    ping: d.gateway_ping_ms,
  }));

  // Calculate stats
  const firstGems = points[0]?.gems || 0;
  const lastGems = points[points.length - 1]?.gems || 0;
  const netGain = lastGems - firstGems;
  const gemsPerHour = points.length > 1 ? Math.round(netGain / Math.max(1, points.length - 1)) : 0;

  return (
    <div className="bg-[#15161b] border border-white/5 rounded-2xl p-5 shadow-xl">
      {/* Chart Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-bold text-white text-base">Grafik Pertumbuhan Saldo Gems</h3>
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
              <TrendingUp className="w-3 h-3" />
              +{netGain.toLocaleString()} 💎
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            Laju estimasi: <span className="font-semibold text-discord-blurple">~{gemsPerHour.toLocaleString()} gems / jam</span>
          </p>
        </div>

        {/* Timeframe toggle */}
        <div className="flex items-center bg-[#101115] border border-white/5 rounded-xl p-1 gap-1 text-xs self-start">
          <button
            onClick={() => setTimeframe('24h')}
            className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 ${
              timeframe === '24h'
                ? 'bg-discord-blurple text-white shadow-md'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <Clock className="w-3 h-3" />
            <span>24 Jam</span>
          </button>
          <button
            onClick={() => setTimeframe('7d')}
            className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 ${
              timeframe === '7d'
                ? 'bg-discord-blurple text-white shadow-md'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <Calendar className="w-3 h-3" />
            <span>7 Hari</span>
          </button>
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="gemsGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#5865F2" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#5865F2" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#252730" vertical={false} />
            <XAxis
              dataKey="time"
              stroke="#6b7280"
              fontSize={11}
              tickLine={false}
              axisLine={{ stroke: '#252730' }}
            />
            <YAxis
              stroke="#6b7280"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (active && payload && payload.length) {
                  return (
                    <div className="bg-[#181920] border border-white/10 rounded-xl p-3 shadow-2xl text-xs space-y-1">
                      <p className="text-gray-400 font-mono text-[11px]">{label}</p>
                      <p className="font-bold text-white flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-discord-blurple"></span>
                        <span>Saldo: {Number(payload[0].value).toLocaleString()} 💎</span>
                      </p>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Area
              type="monotone"
              dataKey="gems"
              stroke="#5865F2"
              strokeWidth={2.5}
              fillOpacity={1}
              fill="url(#gemsGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
