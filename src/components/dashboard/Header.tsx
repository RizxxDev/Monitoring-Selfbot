'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Bot, LogOut, Radio, Database, RotateCcw, ShieldCheck } from 'lucide-react';
import { isSupabaseConfigured } from '@/lib/supabase';
import { simulationStore } from '@/lib/simulation-store';
import { useToast } from './Toast';

export function Header() {
  const router = useRouter();
  const { showToast } = useToast();
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
      showToast({ type: 'info', title: 'Berhasil Logout', message: 'Sesi dashboard telah ditutup.' });
      router.push('/login');
      router.refresh();
    } catch {
      setLoggingOut(false);
    }
  };

  const handleResetDemo = () => {
    simulationStore.resetToDefault();
    showToast({
      type: 'info',
      title: 'Data Demo Direset',
      message: 'Status akun dan saldo telah dikembalikan ke kondisi awal simulasi.',
    });
  };

  return (
    <header className="border-b border-white/5 bg-[#121318]/80 backdrop-blur-md sticky top-0 z-30 px-4 lg:px-8 py-3.5">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-discord-blurple to-indigo-600 flex items-center justify-center shadow-lg shadow-discord-blurple/20 border border-white/10">
            <Bot className="w-6 h-6 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-white text-base lg:text-lg tracking-tight">
                Growcord Farm
              </span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-discord-blurple/20 text-discord-blurple border border-discord-blurple/30 tracking-wider">
                V1.0
              </span>
            </div>
            <p className="text-xs text-gray-400 hidden sm:block">
              Multi-Account Remote Control & Live Telemetry
            </p>
          </div>
        </div>

        {/* Right Actions & Status */}
        <div className="flex items-center gap-2.5 sm:gap-4">
          {/* Connection Status Badge */}
          {isSupabaseConfigured ? (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
              <Database className="w-3.5 h-3.5" />
              <span className="hidden sm:inline font-medium">Supabase Cloud</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-discord-blurple/10 border border-discord-blurple/20 text-discord-blurple text-xs">
              <Radio className="w-3.5 h-3.5" />
              <span className="font-medium">Demo Simulator</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            </div>
          )}

          {/* Reset Demo button (only if not configured) */}
          {!isSupabaseConfigured && (
            <button
              onClick={handleResetDemo}
              title="Reset data simulasi ke awal"
              className="p-2 text-gray-400 hover:text-white bg-[#1e1f24] hover:bg-[#2b2d31] border border-white/5 rounded-lg transition text-xs flex items-center gap-1.5"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span className="hidden md:inline">Reset Demo</span>
            </button>
          )}

          {/* Logout Button */}
          <button
            onClick={handleLogout}
            disabled={loggingOut}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-300 hover:text-red-200 text-xs transition duration-150"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span className="font-medium hidden sm:inline">Kunci / Logout</span>
          </button>
        </div>
      </div>
    </header>
  );
}
