-- MOVIX Admin · Extensiones necesarias para el panel Django
-- Ejecutar UNA VEZ en Supabase > SQL Editor antes de iniciar el proyecto.
-- Es idempotente: puede volver a ejecutarse sin duplicar columnas o tablas.

create extension if not exists pgcrypto;

-- Campos que el diseño administrativo necesita y que no existían en profiles.
alter table public.profiles add column if not exists is_active boolean not null default true;
alter table public.profiles add column if not exists blocked_at timestamptz;
alter table public.profiles add column if not exists blocked_reason text;
alter table public.profiles add column if not exists identification_photo_url text;
alter table public.profiles add column if not exists verification_status text not null default 'pending';
alter table public.profiles add column if not exists verification_rejection_reason text;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'profiles_verification_status_check') then
    alter table public.profiles add constraint profiles_verification_status_check
      check (verification_status in ('pending', 'approved', 'rejected'));
  end if;
end $$;

-- Conserva las verificaciones que ya existían en la aplicación móvil. Cuando se
-- agregó verification_status, PostgreSQL asignó "pending" a todos los registros
-- antiguos; por eso se sincronizan explícitamente los booleanos existentes.
update public.profiles
set verification_status = 'approved'
where coalesce(profile_verified, false) = true or coalesce(verified, false) = true;

update public.profiles
set verification_status = 'pending'
where verification_status is null or verification_status not in ('pending', 'approved', 'rejected');

update public.profiles
set profile_verified = true, verified = true
where verification_status = 'approved';

-- Las versiones anteriores de la app móvil usaban avatar_url; el panel usa
-- profile_photo_url. Se mantienen ambos campos compatibles.
update public.profiles
set profile_photo_url = avatar_url
where nullif(profile_photo_url, '') is null and nullif(avatar_url, '') is not null;

update public.profiles
set avatar_url = profile_photo_url
where nullif(avatar_url, '') is null and nullif(profile_photo_url, '') is not null;

create or replace function public.movix_sync_profile_fields()
returns trigger language plpgsql set search_path = public as $$
begin
  if coalesce(new.profile_verified, false) or coalesce(new.verified, false) then
    new.verification_status := 'approved';
  elsif new.verification_status = 'approved' then
    new.profile_verified := true;
    new.verified := true;
  end if;

  if tg_op = 'INSERT' then
    new.profile_photo_url := coalesce(nullif(new.profile_photo_url, ''), new.avatar_url);
    new.avatar_url := coalesce(nullif(new.avatar_url, ''), new.profile_photo_url);
  elsif new.profile_photo_url is distinct from old.profile_photo_url then
    new.avatar_url := new.profile_photo_url;
  elsif new.avatar_url is distinct from old.avatar_url then
    new.profile_photo_url := new.avatar_url;
  end if;
  return new;
end $$;

drop trigger if exists movix_sync_profile_fields_trigger on public.profiles;
create trigger movix_sync_profile_fields_trigger
before insert or update on public.profiles
for each row execute function public.movix_sync_profile_fields();

create index if not exists profiles_role_idx on public.profiles (role);
create index if not exists profiles_role_lower_idx on public.profiles (lower(role));
create index if not exists profiles_active_idx on public.profiles (is_active);
create index if not exists profiles_verification_status_idx on public.profiles (verification_status);
create index if not exists profiles_created_at_idx on public.profiles (created_at desc);

-- Campañas creadas desde el panel; las notificaciones individuales siguen
-- guardándose en la tabla public.notifications ya existente.
create table if not exists public.admin_notification_campaigns (
  id uuid primary key default gen_random_uuid(),
  audience text not null check (audience in ('all', 'clients', 'drivers', 'specific')),
  recipient_id uuid references public.profiles(id) on delete set null,
  title text not null,
  message text not null,
  total_recipients integer not null default 0,
  push_sent integer not null default 0,
  status text not null default 'stored' check (status in ('stored', 'delivered', 'failed')),
  error_message text,
  created_by text not null,
  created_at timestamptz not null default now()
);
create index if not exists admin_notification_campaigns_created_idx on public.admin_notification_campaigns (created_at desc);

-- Tokens FCM registrados por la app móvil.
create table if not exists public.device_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  token text not null unique,
  platform text not null default 'unknown' check (platform in ('android', 'ios', 'web', 'unknown')),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists device_tokens_user_idx on public.device_tokens (user_id) where is_active;

-- Banners leídos por la app móvil.
create table if not exists public.advertisements (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  description text,
  image_url text not null,
  target_url text,
  audience text not null default 'all' check (audience in ('all', 'clients', 'drivers')),
  is_active boolean not null default true,
  starts_at timestamptz,
  ends_at timestamptz,
  created_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists advertisements_active_idx on public.advertisements (is_active, created_at desc);

-- Registro de cada acción sensible del administrador.
create table if not exists public.admin_audit_logs (
  id uuid primary key default gen_random_uuid(),
  admin_username text not null,
  action text not null,
  entity_type text not null,
  entity_id text,
  description text not null,
  metadata jsonb not null default '{}'::jsonb,
  ip_address inet,
  created_at timestamptz not null default now()
);
create index if not exists admin_audit_logs_created_idx on public.admin_audit_logs (created_at desc);

create table if not exists public.admin_settings (
  key text primary key,
  value jsonb not null default '{}'::jsonb,
  updated_by text,
  updated_at timestamptz not null default now()
);

-- Seguridad Data API. El backend Django usa la conexión PostgreSQL protegida.
alter table public.admin_notification_campaigns enable row level security;
alter table public.device_tokens enable row level security;
alter table public.advertisements enable row level security;
alter table public.admin_audit_logs enable row level security;
alter table public.admin_settings enable row level security;

revoke all on public.admin_notification_campaigns from anon, authenticated;
revoke all on public.admin_audit_logs from anon, authenticated;
revoke all on public.admin_settings from anon, authenticated;

grant select on public.advertisements to anon, authenticated;
drop policy if exists "read active advertisements" on public.advertisements;
create policy "read active advertisements" on public.advertisements
for select to anon, authenticated
using (
  is_active = true
  and (starts_at is null or starts_at <= now())
  and (ends_at is null or ends_at >= now())
);

grant select, insert, update, delete on public.device_tokens to authenticated;
drop policy if exists "users manage own device tokens" on public.device_tokens;
create policy "users manage own device tokens" on public.device_tokens
for all to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

-- Buckets: banners públicos y documentos privados.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('movix-public', 'movix-public', true, 10485760, array['image/jpeg','image/png','image/webp'])
on conflict (id) do update set public = excluded.public, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('movix-documents', 'movix-documents', false, 10485760, array['image/jpeg','image/png','image/webp','application/pdf'])
on conflict (id) do update set public = excluded.public, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "public reads movix banners" on storage.objects;
create policy "public reads movix banners" on storage.objects
for select to anon, authenticated
using (bucket_id = 'movix-public');

-- Mensualidades declaradas por los transportistas. El comprobante se guarda
-- en movix-documents y esta tabla conserva únicamente su referencia segura.
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
create index if not exists driver_monthly_payments_period_status_idx on public.driver_monthly_payments (period desc, status);
create index if not exists driver_monthly_payments_driver_idx on public.driver_monthly_payments (driver_id, created_at desc);

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

-- Cuentas bancarias administrables, facturas y buzón del transportista.
create table if not exists public.payment_bank_accounts (
  id uuid primary key default gen_random_uuid(),
  code text not null unique check (code in ('banco_loja','banco_pichincha','coopego','jep')),
  account_holder text not null,
  account_number text not null,
  account_type text not null default 'savings' check (account_type in ('savings','checking')),
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
insert into public.payment_bank_accounts
  (code, account_holder, account_number, account_type, is_active, sort_order)
values
  ('banco_loja', 'Configurar desde el panel', 'Pendiente', 'savings', false, 10),
  ('banco_pichincha', 'Configurar desde el panel', 'Pendiente', 'savings', false, 20),
  ('coopego', 'Configurar desde el panel', 'Pendiente', 'savings', false, 30),
  ('jep', 'Configurar desde el panel', 'Pendiente', 'savings', false, 40)
on conflict (code) do nothing;

create table if not exists public.driver_invoices (
  id uuid primary key default gen_random_uuid(),
  invoice_number text not null unique,
  payment_id uuid not null unique references public.driver_monthly_payments(id) on delete cascade,
  driver_id uuid not null references public.profiles(id) on delete cascade,
  customer_name text not null,
  customer_email text,
  customer_identification text,
  period date not null,
  amount numeric(10,2) not null check (amount > 0),
  bank text not null,
  payment_method text not null,
  pdf_url text,
  status text not null default 'issued' check (status in ('issued','cancelled')),
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

create table if not exists public.driver_inbox_messages (
  id uuid primary key default gen_random_uuid(),
  driver_id uuid not null references public.profiles(id) on delete cascade,
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

drop trigger if exists payment_bank_accounts_updated_at_trigger on public.payment_bank_accounts;
create trigger payment_bank_accounts_updated_at_trigger
before update on public.payment_bank_accounts
for each row execute function public.movix_set_updated_at();
drop trigger if exists driver_invoices_updated_at_trigger on public.driver_invoices;
create trigger driver_invoices_updated_at_trigger
before update on public.driver_invoices
for each row execute function public.movix_set_updated_at();

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
drop policy if exists "authenticated read active payment banks" on public.payment_bank_accounts;
create policy "authenticated read active payment banks" on public.payment_bank_accounts
for select to authenticated using (is_active = true);
drop policy if exists "drivers read own invoices" on public.driver_invoices;
create policy "drivers read own invoices" on public.driver_invoices
for select to authenticated using (auth.uid() = driver_id);
drop policy if exists "drivers read own inbox" on public.driver_inbox_messages;
create policy "drivers read own inbox" on public.driver_inbox_messages
for select to authenticated using (auth.uid() = driver_id);
drop policy if exists "drivers mark own inbox read" on public.driver_inbox_messages;
create policy "drivers mark own inbox read" on public.driver_inbox_messages
for update to authenticated using (auth.uid() = driver_id) with check (auth.uid() = driver_id);

-- La carga administrativa usa service_role, que omite RLS. Los documentos
-- privados solo se entregan desde Django mediante enlaces firmados temporales.

select 'MOVIX Admin SQL instalado correctamente' as resultado;

notify pgrst, 'reload schema';
