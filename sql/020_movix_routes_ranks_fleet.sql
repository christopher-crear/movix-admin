-- MOVIX Web + App · encomiendas multipunto, rangos, flota y ganancias
-- Ejecutar una sola vez en Supabase SQL Editor. Es idempotente.

create extension if not exists pgcrypto;

alter table public.profiles add column if not exists permit_number text;
alter table public.profiles add column if not exists permit_details text;
alter table public.profiles add column if not exists company_name text;

create table if not exists public.fleet_vehicles (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles(id) on delete cascade,
  plate text not null,
  vehicle_type text not null check (vehicle_type in ('camioneta','camion_pequeno','camion_mediano')),
  year integer check (year is null or year between 1950 and 2100),
  load_capacity numeric(12,2) check (load_capacity is null or load_capacity >= 0),
  alias text,
  permit_number text,
  photo_url text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(owner_id, plate)
);

create table if not exists public.fleet_drivers (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles(id) on delete cascade,
  vehicle_id uuid references public.fleet_vehicles(id) on delete set null,
  first_name text not null,
  last_name text not null,
  identification_number text not null,
  license_number text not null,
  phone text,
  email text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(owner_id, identification_number)
);

alter table public.rides add column if not exists fleet_vehicle_id uuid references public.fleet_vehicles(id) on delete set null;
alter table public.rides add column if not exists fleet_driver_id uuid references public.fleet_drivers(id) on delete set null;

create table if not exists public.ride_stops (
  id uuid primary key default gen_random_uuid(),
  ride_id uuid not null references public.rides(id) on delete cascade,
  stop_type text not null check (stop_type in ('pickup','delivery')),
  sequence integer not null check (sequence > 0),
  address text not null,
  latitude double precision,
  longitude double precision,
  contact_name text,
  contact_phone text,
  notes text,
  status text not null default 'pending' check (status in ('pending','heading','arrived','completed','skipped')),
  arrived_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  unique(ride_id, stop_type, sequence)
);

create index if not exists ride_stops_route_idx on public.ride_stops(ride_id, sequence);
create index if not exists fleet_vehicles_owner_idx on public.fleet_vehicles(owner_id, is_active);
create index if not exists fleet_drivers_owner_idx on public.fleet_drivers(owner_id, is_active);
create index if not exists rides_fleet_vehicle_idx on public.rides(fleet_vehicle_id, completed_at);
create index if not exists rides_driver_completed_idx on public.rides(driver_id, completed_at);

-- La app puede consultar el rango sin guardar valores que se vuelvan obsoletos.
create or replace view public.profile_ranks as
select p.id as profile_id,
       case
         when coalesce(p.rating,0) >= 4.7 and coalesce(p.completed_trips,0) >= 100 then 'star'
         when coalesce(p.rating,0) >= 4.3 and coalesce(p.completed_trips,0) >= 40 then 'pro'
         else 'start'
       end as rank_key,
       case
         when coalesce(p.rating,0) >= 4.7 and coalesce(p.completed_trips,0) >= 100 then 'Estrella MOVIX'
         when coalesce(p.rating,0) >= 4.3 and coalesce(p.completed_trips,0) >= 40 then 'MOVIX Pro'
         else 'MOVIX Inicial'
       end as rank_label,
       (lower(coalesce(p.role,'')) in ('cliente','client','user') and coalesce(p.rating,0) < 3) as low_rating_alert
from public.profiles p;

-- Completa rutas antiguas con un punto de recogida y uno de entrega.
insert into public.ride_stops (ride_id, stop_type, sequence, address, latitude, longitude)
select r.id, 'pickup', 1, r.origin_address, r.origin_latitude, r.origin_longitude
from public.rides r where r.origin_address is not null
on conflict (ride_id, stop_type, sequence) do nothing;

insert into public.ride_stops (ride_id, stop_type, sequence, address, latitude, longitude)
select r.id, 'delivery', 1, r.destination_address, r.destination_latitude, r.destination_longitude
from public.rides r where r.destination_address is not null
on conflict (ride_id, stop_type, sequence) do nothing;

alter table public.ride_stops enable row level security;
alter table public.fleet_vehicles enable row level security;
alter table public.fleet_drivers enable row level security;

drop policy if exists "ride participants read stops" on public.ride_stops;
create policy "ride participants read stops" on public.ride_stops for select using (
  exists(select 1 from public.rides r where r.id=ride_id and (r.client_id=auth.uid() or r.driver_id=auth.uid()))
);
drop policy if exists "clients manage requested ride stops" on public.ride_stops;
create policy "clients manage requested ride stops" on public.ride_stops for all using (
  exists(select 1 from public.rides r where r.id=ride_id and r.client_id=auth.uid())
) with check (
  exists(select 1 from public.rides r where r.id=ride_id and r.client_id=auth.uid())
);
drop policy if exists "owners manage vehicles" on public.fleet_vehicles;
create policy "owners manage vehicles" on public.fleet_vehicles for all using (owner_id=auth.uid()) with check (owner_id=auth.uid());
drop policy if exists "owners manage fleet drivers" on public.fleet_drivers;
create policy "owners manage fleet drivers" on public.fleet_drivers for all using (owner_id=auth.uid()) with check (owner_id=auth.uid());

grant select on public.profile_ranks to authenticated;
grant select, insert, update, delete on public.ride_stops, public.fleet_vehicles, public.fleet_drivers to authenticated;

notify pgrst, 'reload schema';
