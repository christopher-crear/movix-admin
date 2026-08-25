-- MOVIX 022 · Flotas compuestas por perfiles reales de transportista.
-- Copia versionada de sql/022_movix_profile_fleets_and_permits.sql.

begin;

alter table public.profiles
  add column if not exists permit_photo_url text,
  add column if not exists is_fleet_owner boolean not null default false,
  add column if not exists fleet_owner_id uuid references public.profiles(id) on delete set null;

create index if not exists profiles_fleet_owner_idx
  on public.profiles(fleet_owner_id, is_active)
  where fleet_owner_id is not null;
create index if not exists profiles_fleet_company_idx
  on public.profiles(company_name)
  where is_fleet_owner = true;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'profiles_fleet_not_self') then
    alter table public.profiles add constraint profiles_fleet_not_self
      check (fleet_owner_id is null or fleet_owner_id <> id) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'profiles_fleet_owner_not_member') then
    alter table public.profiles add constraint profiles_fleet_owner_not_member
      check (not is_fleet_owner or fleet_owner_id is null) not valid;
  end if;
end $$;

update public.profiles owner_profile
set is_fleet_owner = true
where exists (select 1 from public.fleet_drivers fd where fd.owner_id = owner_profile.id)
or exists (
  select 1 from public.fleet_vehicles fv
  where fv.owner_id = owner_profile.id
  group by fv.owner_id having count(*) > 1
);

update public.profiles member_profile
set fleet_owner_id = fd.owner_id,
    is_fleet_owner = false,
    vehicle_plate = coalesce(nullif(member_profile.vehicle_plate, ''), fv.plate),
    vehicle_type = coalesce(nullif(member_profile.vehicle_type, ''), fv.vehicle_type),
    vehicle_year = coalesce(member_profile.vehicle_year, fv.year),
    load_capacity = coalesce(member_profile.load_capacity, fv.load_capacity),
    permit_number = coalesce(nullif(member_profile.permit_number, ''), fv.permit_number),
    updated_at = now()
from public.fleet_drivers fd
left join public.fleet_vehicles fv on fv.id = fd.vehicle_id
where member_profile.id <> fd.owner_id
  and coalesce(member_profile.identification_number, member_profile.cedula) = fd.identification_number;

create schema if not exists private;
create or replace function private.movix_protect_fleet_assignment()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  if (select auth.uid()) is not null and (
    new.fleet_owner_id is distinct from old.fleet_owner_id
    or new.is_fleet_owner is distinct from old.is_fleet_owner
  ) then
    raise exception 'La agrupación de flota solo puede modificarla el administrador.';
  end if;
  return new;
end;
$$;
revoke all on function private.movix_protect_fleet_assignment() from public, anon, authenticated;
drop trigger if exists movix_protect_fleet_assignment on public.profiles;
create trigger movix_protect_fleet_assignment
before update of fleet_owner_id, is_fleet_owner on public.profiles
for each row execute function private.movix_protect_fleet_assignment();

drop policy if exists "drivers create own monthly payments" on public.driver_monthly_payments;
create policy "drivers create own monthly payments" on public.driver_monthly_payments
for insert to authenticated with check (driver_id = (select auth.uid()) and vehicle_id is null);

commit;
notify pgrst, 'reload schema';
