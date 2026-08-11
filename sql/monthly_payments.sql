-- MOVIX · Mensualidades de transportistas
-- Puedes ejecutar solamente este archivo si supabase_panel.sql ya fue aplicado.
create extension if not exists pgcrypto;

create table if not exists public.driver_monthly_payments (
  id uuid primary key default gen_random_uuid(),
  driver_id uuid not null references public.profiles(id) on delete cascade,
  period date not null,
  amount numeric(10,2),
  bank text not null check (bank in ('banco_loja','banco_pichincha','coopego','jep','physical')),
  payment_method text not null default 'transfer' check (payment_method in ('transfer','deposit','cash')),
  receipt_url text,
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  admin_notes text,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint driver_monthly_payments_period_first_day check (period = date_trunc('month', period)::date),
  constraint driver_monthly_payments_driver_period_unique unique (driver_id, period),
  constraint driver_monthly_payments_receipt_required check (payment_method = 'cash' or nullif(receipt_url, '') is not null)
);

create index if not exists driver_monthly_payments_period_status_idx
  on public.driver_monthly_payments (period desc, status);
create index if not exists driver_monthly_payments_driver_idx
  on public.driver_monthly_payments (driver_id, created_at desc);

create or replace function public.movix_set_updated_at()
returns trigger language plpgsql set search_path = public as $$
begin
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists driver_monthly_payments_updated_at_trigger on public.driver_monthly_payments;
create trigger driver_monthly_payments_updated_at_trigger
before update on public.driver_monthly_payments
for each row execute function public.movix_set_updated_at();

alter table public.driver_monthly_payments enable row level security;
grant select, insert on public.driver_monthly_payments to authenticated;
revoke update, delete on public.driver_monthly_payments from anon, authenticated;

drop policy if exists "drivers read own monthly payments" on public.driver_monthly_payments;
create policy "drivers read own monthly payments" on public.driver_monthly_payments
for select to authenticated using (auth.uid() = driver_id);

drop policy if exists "drivers create own monthly payments" on public.driver_monthly_payments;
create policy "drivers create own monthly payments" on public.driver_monthly_payments
for insert to authenticated with check (
  auth.uid() = driver_id
  and status = 'pending'
  and reviewed_by is null
  and reviewed_at is null
);

notify pgrst, 'reload schema';
select 'Mensualidades MOVIX instaladas correctamente' as resultado;
