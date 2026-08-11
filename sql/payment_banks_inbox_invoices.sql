-- MOVIX · Bancos, facturas y buzón del transportista
-- Ejecutar en Supabase > SQL Editor después de sql/supabase_panel.sql.
-- Es idempotente: puede ejecutarse nuevamente sin borrar información.

create extension if not exists pgcrypto;

-- Cuentas que el administrador habilita desde el panel.
create table if not exists public.payment_bank_accounts (
  id uuid primary key default gen_random_uuid(),
  code text not null unique
    check (code in ('banco_loja','banco_pichincha','coopego','jep')),
  account_holder text not null,
  account_number text not null,
  account_type text not null default 'savings'
    check (account_type in ('savings','checking')),
  identification_number text,
  instructions text,
  logo_url text,
  qr_url text,
  is_active boolean not null default false,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists payment_bank_accounts_visible_idx
  on public.payment_bank_accounts (is_active, sort_order, code);

-- Se crean los cuatro bancos admitidos, pero permanecen ocultos hasta que el
-- administrador reemplace los valores pendientes y active cada cuenta.
insert into public.payment_bank_accounts
  (code, account_holder, account_number, account_type, is_active, sort_order)
values
  ('banco_loja', 'Configurar desde el panel', 'Pendiente', 'savings', false, 10),
  ('banco_pichincha', 'Configurar desde el panel', 'Pendiente', 'savings', false, 20),
  ('coopego', 'Configurar desde el panel', 'Pendiente', 'savings', false, 30),
  ('jep', 'Configurar desde el panel', 'Pendiente', 'savings', false, 40)
on conflict (code) do nothing;

-- Factura PDF emitida a partir de una mensualidad aprobada.
create table if not exists public.driver_invoices (
  id uuid primary key default gen_random_uuid(),
  invoice_number text not null unique,
  payment_id uuid not null unique
    references public.driver_monthly_payments(id) on delete cascade,
  driver_id uuid not null
    references public.profiles(id) on delete cascade,
  customer_name text not null,
  customer_email text,
  customer_identification text,
  period date not null,
  amount numeric(10,2) not null check (amount > 0),
  bank text not null,
  payment_method text not null,
  pdf_url text,
  status text not null default 'issued'
    check (status in ('issued','cancelled')),
  issued_at timestamptz not null default now(),
  emailed_at timestamptz,
  created_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists driver_invoices_driver_idx
  on public.driver_invoices (driver_id, issued_at desc);
create index if not exists driver_invoices_period_idx
  on public.driver_invoices (period desc, status);

-- Mensajes persistentes visibles en el portal y en la app móvil.
create table if not exists public.driver_inbox_messages (
  id uuid primary key default gen_random_uuid(),
  driver_id uuid not null
    references public.profiles(id) on delete cascade,
  message_type text not null default 'general'
    check (message_type in ('invoice','meeting','payment','account','general')),
  title text not null,
  body text not null,
  invoice_id uuid references public.driver_invoices(id) on delete set null,
  details jsonb not null default '{}'::jsonb,
  is_read boolean not null default false,
  read_at timestamptz,
  emailed_at timestamptz,
  created_by text,
  created_at timestamptz not null default now()
);

create index if not exists driver_inbox_messages_driver_idx
  on public.driver_inbox_messages (driver_id, is_read, created_at desc);
create index if not exists driver_inbox_messages_type_idx
  on public.driver_inbox_messages (message_type, created_at desc);

create or replace function public.movix_set_updated_at()
returns trigger language plpgsql set search_path = public as $$
begin
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists payment_bank_accounts_updated_at_trigger
  on public.payment_bank_accounts;
create trigger payment_bank_accounts_updated_at_trigger
before update on public.payment_bank_accounts
for each row execute function public.movix_set_updated_at();

drop trigger if exists driver_invoices_updated_at_trigger
  on public.driver_invoices;
create trigger driver_invoices_updated_at_trigger
before update on public.driver_invoices
for each row execute function public.movix_set_updated_at();

-- RLS: la conexión PostgreSQL protegida de Django administra los datos. La
-- Data API solo entrega a cada cuenta autenticada lo que le corresponde.
alter table public.payment_bank_accounts enable row level security;
alter table public.driver_invoices enable row level security;
alter table public.driver_inbox_messages enable row level security;

revoke all on public.payment_bank_accounts from anon, authenticated;
revoke all on public.driver_invoices from anon, authenticated;
revoke all on public.driver_inbox_messages from anon, authenticated;

grant select on public.payment_bank_accounts to authenticated;
grant select on public.driver_invoices to authenticated;
grant select on public.driver_inbox_messages to authenticated;
grant update (is_read, read_at) on public.driver_inbox_messages to authenticated;

drop policy if exists "authenticated read active payment banks"
  on public.payment_bank_accounts;
create policy "authenticated read active payment banks"
on public.payment_bank_accounts for select to authenticated
using (is_active = true);

drop policy if exists "drivers read own invoices" on public.driver_invoices;
create policy "drivers read own invoices"
on public.driver_invoices for select to authenticated
using (auth.uid() = driver_id);

drop policy if exists "drivers read own inbox" on public.driver_inbox_messages;
create policy "drivers read own inbox"
on public.driver_inbox_messages for select to authenticated
using (auth.uid() = driver_id);

drop policy if exists "drivers mark own inbox read" on public.driver_inbox_messages;
create policy "drivers mark own inbox read"
on public.driver_inbox_messages for update to authenticated
using (auth.uid() = driver_id)
with check (auth.uid() = driver_id);

notify pgrst, 'reload schema';

select
  'Bancos, facturas y buzón MOVIX instalados correctamente' as resultado,
  (select count(*) from public.payment_bank_accounts) as bancos_registrados;
