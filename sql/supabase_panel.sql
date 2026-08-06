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

-- La carga administrativa usa service_role, que omite RLS. Los documentos
-- privados solo se entregan desde Django mediante enlaces firmados temporales.

select 'MOVIX Admin SQL instalado correctamente' as resultado;

notify pgrst, 'reload schema';
