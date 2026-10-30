-- ================================================================
-- 01_init_schema.sql
-- Discord Autofarm Multi-Account Monitoring & Control Schema
-- ================================================================

-- 1. Tabel: accounts
CREATE TABLE IF NOT EXISTS public.accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label VARCHAR(100) NOT NULL,
    encrypted_token TEXT NOT NULL,
    channel_id VARCHAR(32) NOT NULL,
    farmable_item VARCHAR(64) NOT NULL DEFAULT 'pot o'' gems',
    gem_floor INTEGER NOT NULL DEFAULT 2000,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, PAUSED, ERROR, OFFLINE
    avatar_url TEXT,
    last_heartbeat TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Index untuk mempercepat query status dan heartbeat
CREATE INDEX IF NOT EXISTS idx_accounts_status ON public.accounts(status);
CREATE INDEX IF NOT EXISTS idx_accounts_last_heartbeat ON public.accounts(last_heartbeat);

-- 2. Tabel: bot_commands
CREATE TABLE IF NOT EXISTS public.bot_commands (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    command VARCHAR(50) NOT NULL, -- START, PAUSE, FORCE_REBUFF, FORCE_RESTOCK
    payload JSONB DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING, EXECUTED, FAILED
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    executed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_bot_commands_account_id ON public.bot_commands(account_id);
CREATE INDEX IF NOT EXISTS idx_bot_commands_status ON public.bot_commands(status);
CREATE INDEX IF NOT EXISTS idx_bot_commands_created_at ON public.bot_commands(created_at DESC);

-- 3. Tabel: metrics_history
CREATE TABLE IF NOT EXISTS public.metrics_history (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    gems_balance INTEGER NOT NULL DEFAULT 0,
    stock_remaining INTEGER NOT NULL DEFAULT 0,
    is_farming BOOLEAN NOT NULL DEFAULT true,
    buff_clover_sec INTEGER NOT NULL DEFAULT 0,
    buff_arroz_sec INTEGER NOT NULL DEFAULT 0,
    buff_benedict_sec INTEGER NOT NULL DEFAULT 0,
    gateway_ping_ms INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_metrics_account_time ON public.metrics_history(account_id, timestamp DESC);

-- 4. Tabel: event_logs
CREATE TABLE IF NOT EXISTS public.event_logs (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    event_type VARCHAR(50) NOT NULL, -- ANTI_AFK_SOLVED, BUFF_APPLIED, SHOP_PURCHASE, ERROR, etc.
    severity VARCHAR(20) NOT NULL DEFAULT 'INFO', -- INFO, WARNING, CRITICAL
    message TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_event_logs_account_time ON public.event_logs(account_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_event_logs_severity ON public.event_logs(severity);
CREATE INDEX IF NOT EXISTS idx_event_logs_event_type ON public.event_logs(event_type);

-- Trigger untuk update automatic kolom updated_at pada tabel accounts
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_accounts_updated_at ON public.accounts;
CREATE TRIGGER set_accounts_updated_at
BEFORE UPDATE ON public.accounts
FOR EACH ROW
EXECUTE FUNCTION public.handle_updated_at();

-- Enable Row Level Security (RLS)
ALTER TABLE public.accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bot_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.metrics_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_logs ENABLE ROW LEVEL SECURITY;

-- Policy dasar: Service Role & Anon key bisa membaca / menulis jika digunakan dalam dashboard terproteksi
CREATE POLICY "Allow public read access to accounts" ON public.accounts FOR SELECT USING (true);
CREATE POLICY "Allow public insert to accounts" ON public.accounts FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow public update to accounts" ON public.accounts FOR UPDATE USING (true);
CREATE POLICY "Allow public delete to accounts" ON public.accounts FOR DELETE USING (true);

CREATE POLICY "Allow public access to bot_commands" ON public.bot_commands FOR ALL USING (true);
CREATE POLICY "Allow public access to metrics_history" ON public.metrics_history FOR ALL USING (true);
CREATE POLICY "Allow public access to event_logs" ON public.event_logs FOR ALL USING (true);

-- Enable Supabase Realtime publication untuk tables yang dimonitor
DO $$
BEGIN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.accounts;
    ALTER PUBLICATION supabase_realtime ADD TABLE public.bot_commands;
    ALTER PUBLICATION supabase_realtime ADD TABLE public.event_logs;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
