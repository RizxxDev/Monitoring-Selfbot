'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ShieldAlert, KeyRound, Lock, Eye, EyeOff, AlertTriangle, Bot } from 'lucide-react';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectPath = searchParams.get('redirect') || '/';

  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remainingAttempts, setRemainingAttempts] = useState<number | null>(null);
  const [lockedCountdown, setLockedCountdown] = useState<number | null>(null);

  // Countdown timer for lockout
  useEffect(() => {
    if (lockedCountdown === null || lockedCountdown <= 0) return;
    const interval = setInterval(() => {
      setLockedCountdown((prev) => {
        if (prev === null || prev <= 1) return null;
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [lockedCountdown]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim() || lockedCountdown !== null) return;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || 'Password salah.');
        if (data.isLocked && data.retryAfterSec) {
          setLockedCountdown(data.retryAfterSec);
        } else if (typeof data.remainingAttempts === 'number') {
          setRemainingAttempts(data.remainingAttempts);
        }
      } else {
        // Success
        router.push(redirectPath);
        router.refresh();
      }
    } catch {
      setError('Gagal menghubungi server. Pastikan server aktif.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md relative z-10">
      {/* Brand Card */}
      <div className="bg-[#18191c] border border-white/10 rounded-2xl shadow-2xl p-8 backdrop-blur-xl">
        {/* Logo & Header */}
        <div className="flex flex-col items-center text-center mb-8">
          <div className="w-16 h-16 bg-gradient-to-tr from-discord-blurple to-indigo-600 rounded-2xl flex items-center justify-center shadow-lg shadow-discord-blurple/25 mb-4 border border-white/10">
            <Bot className="w-9 h-9 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            Growcord Farm{' '}
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-discord-blurple/20 text-discord-blurple border border-discord-blurple/30">
              MONITOR
            </span>
          </h1>
          <p className="text-gray-400 text-sm mt-1">Multi-Account Remote Control & Analytics</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <div className="flex justify-between items-center mb-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-gray-300 flex items-center gap-1.5">
                <KeyRound className="w-3.5 h-3.5 text-discord-blurple" />
                Master Password
              </label>
              <span className="text-[11px] text-gray-500">Default: admin123</span>
            </div>

            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-500">
                <Lock className="w-4 h-4" />
              </div>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Masukkan master password..."
                disabled={lockedCountdown !== null}
                className="w-full bg-[#111214] border border-white/10 rounded-xl py-3 pl-10 pr-11 text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-discord-blurple/50 focus:border-discord-blurple transition text-sm disabled:opacity-50"
                autoFocus
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-gray-400 hover:text-white transition"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Error & Lockout Notification */}
          {error && (
            <div className="p-3.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-start gap-2.5 animate-fadeIn">
              <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">{error}</p>
                {lockedCountdown !== null && (
                  <p className="mt-1 font-mono text-[11px] text-red-300">
                    Tunggu {lockedCountdown} detik sebelum mencoba kembali.
                  </p>
                )}
              </div>
            </div>
          )}

          {remainingAttempts !== null && remainingAttempts > 0 && remainingAttempts < 5 && !error && (
            <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              <span>Sisa kesempatan login: {remainingAttempts} kali</span>
            </div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading || !password.trim() || lockedCountdown !== null}
            className="w-full bg-gradient-to-r from-discord-blurple to-indigo-600 hover:from-discord-blurple/90 hover:to-indigo-500 text-white font-medium py-3 rounded-xl shadow-lg shadow-discord-blurple/25 transition duration-200 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin"></div>
            ) : (
              <>
                <Lock className="w-4 h-4" />
                <span>Buka Akses Dashboard</span>
              </>
            )}
          </button>
        </form>

        {/* Security Notice Footer */}
        <div className="mt-6 pt-5 border-t border-white/5 flex items-center justify-between text-[11px] text-gray-500">
          <span className="flex items-center gap-1.5">
            <ShieldAlert className="w-3.5 h-3.5 text-emerald-400" />
            Sesi HTTP-Only 24 Jam
          </span>
          <span>Brute-force Protected</span>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-[#0d0e12] flex items-center justify-center p-4 selection:bg-discord-blurple selection:text-white">
      {/* Background ambient lighting */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-discord-blurple/15 rounded-full blur-3xl"></div>
        <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl"></div>
      </div>

      <Suspense
        fallback={
          <div className="w-full max-w-md p-8 bg-[#18191c] rounded-2xl border border-white/10 text-center text-gray-400 text-sm">
            Memuat gerbang keamanan...
          </div>
        }
      >
        <LoginForm />
      </Suspense>
    </div>
  );
}
