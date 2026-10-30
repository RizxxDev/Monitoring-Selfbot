'use client';

import React from 'react';
import { BUFF_CONFIG } from '@/lib/constants';

interface BuffIndicatorProps {
  type: keyof typeof BUFF_CONFIG;
  secondsRemaining: number;
}

function formatCountdown(sec: number): string {
  if (sec <= 0) return 'EXPIRED';
  const hrs = Math.floor(sec / 3600);
  const mins = Math.floor((sec % 3600) / 60);
  const secs = sec % 60;

  if (hrs > 0) {
    return `${hrs}j ${mins}m`;
  }
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export function BuffIndicator({ type, secondsRemaining }: BuffIndicatorProps) {
  const config = BUFF_CONFIG[type];
  const maxSec = config.maxSeconds;
  const pct = Math.min(100, Math.max(0, (secondsRemaining / maxSec) * 100));

  const isExpired = secondsRemaining <= 0;
  const isCritical = secondsRemaining > 0 && secondsRemaining <= 300; // <= 5 minutes

  // Determine styling
  let badgeColor = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
  let barColor = 'bg-emerald-500';

  if (type === 'arroz') {
    badgeColor = 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    barColor = 'bg-amber-500';
  } else if (type === 'benedict') {
    badgeColor = 'bg-sky-500/10 text-sky-400 border-sky-500/20';
    barColor = 'bg-sky-500';
  }

  if (isCritical) {
    badgeColor = 'bg-red-500/15 text-red-300 border-red-500/30 animate-pulse';
    barColor = 'bg-red-500';
  } else if (isExpired) {
    badgeColor = 'bg-gray-800 text-gray-500 border-gray-700';
    barColor = 'bg-gray-700';
  }

  return (
    <div className="flex flex-col gap-1.5 p-2 rounded-xl bg-[#111216] border border-white/5">
      <div className="flex items-center justify-between gap-1 text-[11px]">
        <span className="flex items-center gap-1 font-medium text-gray-300 truncate">
          <span>{config.icon}</span>
          <span>{config.shortName}</span>
        </span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border ${badgeColor}`}>
          {formatCountdown(secondsRemaining)}
        </span>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-[#1b1d22] h-1.5 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-1000 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
