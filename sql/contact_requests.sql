-- Respaldo manual para la tabla de solicitudes de la landing pública.
-- En una instalación normal NO es necesario ejecutar este archivo:
-- `python manage.py migrate` crea la misma tabla mediante la migración 0002.
-- Úsalo únicamente si administras el esquema manualmente desde Supabase SQL Editor.

create extension if not exists pgcrypto;

create table if not exists public.contact_requests (
    id uuid primary key default gen_random_uuid(),
    full_name varchar(160) not null,
    email varchar(254) not null,
    phone varchar(30) not null default '',
    request_type varchar(30) not null default 'service'
        check (request_type in ('service', 'driver', 'company', 'support', 'other')),
    subject varchar(180) not null,
    message varchar(2000) not null,
    status varchar(20) not null default 'new'
        check (status in ('new', 'read', 'responded', 'closed')),
    admin_response varchar(4000) not null default '',
    responded_by varchar(150) not null default '',
    responded_at timestamptz null,
    ip_address inet null,
    user_agent varchar(300) not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists contact_status_created_idx
    on public.contact_requests (status, created_at desc);
create index if not exists contact_email_idx
    on public.contact_requests (email);

alter table public.contact_requests enable row level security;

-- La landing escribe mediante Django/PostgreSQL y el administrador utiliza el
-- backend protegido. No se expone una política pública a Supabase REST.
revoke all on table public.contact_requests from anon, authenticated;
