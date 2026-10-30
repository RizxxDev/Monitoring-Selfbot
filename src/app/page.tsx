'use client';

import React, { useState, useEffect } from 'react';
import { Header } from '@/components/dashboard/Header';
import { MetricsSummary } from '@/components/dashboard/MetricsSummary';
import { AccountCard } from '@/components/dashboard/AccountCard';
import { AccountDrawer } from '@/components/dashboard/AccountDrawer';
import { AddAccountModal } from '@/components/dashboard/AddAccountModal';
import { ToastProvider } from '@/components/dashboard/Toast';
import { Account } from '@/lib/types';
import { simulationStore } from '@/lib/simulation-store';
import { AlertCircle, Bot, RefreshCw } from 'lucide-react';

export default function DashboardPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [filterStatus, setFilterStatus] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDrawerAccount, setSelectedDrawerAccount] = useState<Account | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);

  useEffect(() => {
    // Initialize simulation store
    simulationStore.init();
    setAccounts(simulationStore.getAccounts());

    // Subscribe to store updates (every 1-second tick or remote action)
    const unsubscribe = simulationStore.subscribe(() => {
      setAccounts([...simulationStore.getAccounts()]);
    });

    return () => unsubscribe();
  }, []);

  // Filter accounts
  const filteredAccounts = accounts.filter((acc) => {
    const matchesFilter = filterStatus === 'ALL' || acc.status === filterStatus;
    const matchesSearch =
      acc.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
      acc.channel_id.includes(searchQuery) ||
      acc.farmable_item.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  const handleOpenDrawer = (acc: Account) => {
    setSelectedDrawerAccount(acc);
    setIsDrawerOpen(true);
  };

  return (
    <ToastProvider>
      <div className="min-h-screen bg-[#0e0f14] text-[#e0e2e8] flex flex-col selection:bg-discord-blurple selection:text-white">
        {/* Navigation Bar */}
        <Header />

        {/* Main Content Area */}
        <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-8">
          {/* Top Metrics Summary & Controls */}
          <MetricsSummary
            accounts={accounts}
            filterStatus={filterStatus}
            setFilterStatus={setFilterStatus}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            onOpenAddModal={() => setIsAddModalOpen(true)}
          />

          {/* Account Cards Grid */}
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold uppercase tracking-wider text-gray-400 flex items-center gap-2">
                <span>Daftar Akun Farm</span>
                <span className="text-xs bg-white/5 px-2 py-0.5 rounded-full text-gray-300">
                  {filteredAccounts.length}
                </span>
              </h2>
            </div>

            {filteredAccounts.length === 0 ? (
              <div className="bg-[#15161b] border border-white/5 rounded-2xl p-12 text-center flex flex-col items-center justify-center space-y-3">
                <div className="p-4 rounded-2xl bg-[#1e2026] text-gray-400">
                  <Bot className="w-8 h-8" />
                </div>
                <h3 className="font-bold text-white text-base">Tidak Ada Akun Ditemukan</h3>
                <p className="text-xs text-gray-400 max-w-sm">
                  Tidak ada akun bot yang cocok dengan kriteria filter atau pencarian Anda.
                </p>
                <button
                  onClick={() => {
                    setFilterStatus('ALL');
                    setSearchQuery('');
                  }}
                  className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-white transition mt-2 flex items-center gap-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Reset Filter</span>
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {filteredAccounts.map((account) => (
                  <AccountCard
                    key={account.id}
                    account={account}
                    onOpenDrawer={handleOpenDrawer}
                  />
                ))}
              </div>
            )}
          </section>
        </main>

        {/* Slide-over Drawer for Quick Inspection */}
        <AccountDrawer
          account={selectedDrawerAccount}
          isOpen={isDrawerOpen}
          onClose={() => {
            setIsDrawerOpen(false);
            setSelectedDrawerAccount(null);
          }}
        />

        {/* Modal Tambah Akun Baru */}
        <AddAccountModal
          isOpen={isAddModalOpen}
          onClose={() => setIsAddModalOpen(false)}
        />
      </div>
    </ToastProvider>
  );
}
