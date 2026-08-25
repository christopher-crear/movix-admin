-- MOVIX 021 · Administración exclusiva de flotas, mensualidad por vehículo
-- y notificaciones administrativas descartables.
-- Ejecutar después de 020_movix_routes_ranks_fleet.sql.

begin;

-- Restricciones estructurales para registros nuevos. NOT VALID conserva los
-- datos históricos hasta que el administrador los depure.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'fleet_vehicle_ec_plate') then
    alter table public.fleet_vehicles add constraint fleet_vehicle_ec_plate
      check (plate ~ '^[A-Z]{3}-[0-9]{3,4}$') not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'fleet_driver_ec_phone') then
    alter table public.fleet_drivers add constraint fleet_driver_ec_phone
      check (phone is null or phone ~ '^09[0-9]{8}$') not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'fleet_driver_ec_license') then
    alter table public.fleet_drivers add constraint fleet_driver_ec_license
      check (license_number ~ '^[0-9]{10}$') not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'fleet_driver_ec_identification') then
    alter table public.fleet_drivers add constraint fleet_driver_ec_identification
      check (identification_number ~ '^[0-9]{10}$') not valid;
  end if;
end $$;

-- Los propietarios solo consultan lo que el administrador agrupó.
drop policy if exists "owners manage vehicles" on public.fleet_vehicles;
drop policy if exists "owners read vehicles" on public.fleet_vehicles;
create policy "owners read vehicles" on public.fleet_vehicles
for select to authenticated
using ((select auth.uid()) = owner_id);

drop policy if exists "owners manage fleet drivers" on public.fleet_drivers;
drop policy if exists "owners read fleet drivers" on public.fleet_drivers;
create policy "owners read fleet drivers" on public.fleet_drivers
for select to authenticated
using ((select auth.uid()) = owner_id);

revoke insert, update, delete on public.fleet_vehicles, public.fleet_drivers from anon, authenticated;
grant select on public.fleet_vehicles, public.fleet_drivers to authenticated;

-- La mensualidad se controla por cada vehículo registrado.
alter table public.driver_monthly_payments
  add column if not exists vehicle_id uuid references public.fleet_vehicles(id) on delete restrict;

alter table public.driver_monthly_payments
  drop constraint if exists driver_monthly_payments_driver_period_unique;

create unique index if not exists driver_monthly_payments_vehicle_period_unique
  on public.driver_monthly_payments(driver_id, vehicle_id, period)
  where vehicle_id is not null;
create unique index if not exists driver_monthly_payments_legacy_period_unique
  on public.driver_monthly_payments(driver_id, period)
  where vehicle_id is null;
create index if not exists driver_monthly_payments_vehicle_idx
  on public.driver_monthly_payments(vehicle_id, period desc);

drop policy if exists "drivers create own monthly payments" on public.driver_monthly_payments;
create policy "drivers create own monthly payments" on public.driver_monthly_payments
for insert to authenticated with check (
  driver_id = (select auth.uid())
  and vehicle_id is not null
  and exists (
    select 1 from public.fleet_vehicles fv
    where fv.id = vehicle_id and fv.owner_id = (select auth.uid()) and fv.is_active
  )
);

-- Alertas del administrador. No se exponen al cliente; Django las gestiona
-- con su conexión administrativa y las elimina al abrirlas.
create table if not exists public.admin_notifications (
  id uuid primary key default gen_random_uuid(),
  type text not null default 'general',
  title text not null,
  message text not null,
  target_url text,
  entity_type text,
  entity_id uuid,
  created_at timestamptz not null default now()
);
create index if not exists admin_notifications_created_idx
  on public.admin_notifications(created_at desc);
alter table public.admin_notifications enable row level security;
revoke all on public.admin_notifications from anon, authenticated;

create schema if not exists private;

create or replace function private.movix_notify_new_payment()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.admin_notifications(type, title, message, target_url, entity_type, entity_id)
  values (
    'payment', 'Nuevo pago por verificar',
    'Se registró una mensualidad de vehículo que requiere revisión.',
    '/mensualidades/?status=pending', 'driver_monthly_payment', new.id
  );
  return new;
end;
$$;
revoke all on function private.movix_notify_new_payment() from public, anon, authenticated;
drop trigger if exists movix_admin_new_payment on public.driver_monthly_payments;
create trigger movix_admin_new_payment
after insert on public.driver_monthly_payments
for each row execute function private.movix_notify_new_payment();

create or replace function private.movix_notify_profile_verification()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if coalesce(new.verification_status, 'pending') = 'pending' then
    insert into public.admin_notifications(type, title, message, target_url, entity_type, entity_id)
    values (
      'profile', 'Nuevo perfil por verificar',
      'Un perfil nuevo requiere revisión de datos y documentos.',
      '/verificaciones/?status=pending', 'profile', new.id
    );
  end if;
  return new;
end;
$$;
revoke all on function private.movix_notify_profile_verification() from public, anon, authenticated;
drop trigger if exists movix_admin_new_profile on public.profiles;
create trigger movix_admin_new_profile
after insert on public.profiles
for each row execute function private.movix_notify_profile_verification();

-- Las vistas respetan las políticas de las tablas subyacentes (Postgres 15+).
alter view public.profile_ranks set (security_invoker = true);

commit;
notify pgrst, 'reload schema';
