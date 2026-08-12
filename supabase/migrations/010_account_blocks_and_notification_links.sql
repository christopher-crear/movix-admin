-- MOVIX V17
-- Sincroniza el bloqueo del panel con la app, impide acciones de cuentas
-- suspendidas y permite descartar notificaciones con un gesto de deslizamiento.
-- Ejecutar una sola vez en Supabase > SQL Editor. Es idempotente.

alter table public.profiles
  add column if not exists is_active boolean not null default true,
  add column if not exists is_blocked boolean not null default false,
  add column if not exists blocked_at timestamptz,
  add column if not exists blocked_reason text;

update public.profiles
set is_blocked = true
where is_active = false and is_blocked = false;

create or replace function public.movix_sync_profile_block()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if tg_op = 'INSERT' then
    new.is_blocked := coalesce(new.is_blocked, false) or not coalesce(new.is_active, true);
    new.is_active := not new.is_blocked;
  elsif new.is_blocked is distinct from old.is_blocked then
    new.is_active := not new.is_blocked;
  elsif new.is_active is distinct from old.is_active then
    new.is_blocked := not new.is_active;
  end if;

  if new.is_blocked then
    new.blocked_at := coalesce(new.blocked_at, now());
    new.blocked_reason := coalesce(nullif(btrim(new.blocked_reason), ''), 'Cuenta suspendida por administración');
  else
    new.blocked_at := null;
    new.blocked_reason := null;
  end if;
  return new;
end;
$$;

drop trigger if exists movix_sync_profile_block_trigger on public.profiles;
create trigger movix_sync_profile_block_trigger
before insert or update of is_active, is_blocked, blocked_at, blocked_reason
on public.profiles
for each row execute function public.movix_sync_profile_block();

create or replace function public.movix_account_can_act(check_user uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce((
    select p.is_active and not p.is_blocked
    from public.profiles p
    where p.id = check_user
  ), false);
$$;

revoke all on function public.movix_account_can_act(uuid) from public;
grant execute on function public.movix_account_can_act(uuid) to authenticated, service_role;

-- Una política RESTRICTIVE se combina con las políticas ya creadas por la app.
-- Aunque el JWT siga vigente, una cuenta bloqueada no puede INSERT/UPDATE/DELETE.
do $$
declare
  table_name text;
  command_name text;
  policy_name text;
begin
  foreach table_name in array array[
    'rides', 'driver_reviews', 'driver_monthly_payments', 'device_tokens'
  ] loop
    if to_regclass(format('public.%I', table_name)) is not null then
      execute format('alter table public.%I enable row level security', table_name);
      foreach command_name in array array['insert', 'update', 'delete'] loop
        policy_name := format('movix_active_account_%s_%s', table_name, command_name);
        execute format('drop policy if exists %I on public.%I', policy_name, table_name);
        if command_name = 'insert' then
          execute format(
            'create policy %I on public.%I as restrictive for insert to authenticated with check (public.movix_account_can_act(auth.uid()))',
            policy_name, table_name
          );
        elsif command_name = 'update' then
          execute format(
            'create policy %I on public.%I as restrictive for update to authenticated using (public.movix_account_can_act(auth.uid())) with check (public.movix_account_can_act(auth.uid()))',
            policy_name, table_name
          );
        else
          execute format(
            'create policy %I on public.%I as restrictive for delete to authenticated using (public.movix_account_can_act(auth.uid()))',
            policy_name, table_name
          );
        end if;
      end loop;
    end if;
  end loop;
end $$;

-- Un perfil bloqueado tampoco puede editarse para quitarse el bloqueo. No se
-- restringe INSERT porque el perfil todavía no existe durante el registro.
do $$
begin
  drop policy if exists movix_active_account_profiles_update on public.profiles;
  create policy movix_active_account_profiles_update
    on public.profiles as restrictive for update to authenticated
    using (public.movix_account_can_act(auth.uid()))
    with check (public.movix_account_can_act(auth.uid()));
  drop policy if exists movix_active_account_profiles_delete on public.profiles;
  create policy movix_active_account_profiles_delete
    on public.profiles as restrictive for delete to authenticated
    using (public.movix_account_can_act(auth.uid()));
end $$;

-- Metadatos opcionales para que una notificación pueda abrir una pantalla.
alter table if exists public.notifications
  add column if not exists action_url text,
  add column if not exists action_label text,
  add column if not exists metadata jsonb not null default '{}'::jsonb;

-- El usuario solo puede borrar sus propias notificaciones. Esto es lo que debe
-- invocar Flutter al completar el gesto de deslizar.
do $$
begin
  if to_regclass('public.notifications') is not null then
    alter table public.notifications enable row level security;
    drop policy if exists movix_delete_own_notification on public.notifications;
    create policy movix_delete_own_notification
      on public.notifications for delete to authenticated
      using (auth.uid() = user_id);
  end if;
end $$;

grant delete on table public.notifications to authenticated;

create or replace function public.dismiss_notification(notification_id uuid)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
declare
  deleted_count integer;
begin
  delete from public.notifications
  where id = notification_id and user_id = auth.uid();
  get diagnostics deleted_count = row_count;
  return deleted_count > 0;
end;
$$;

revoke all on function public.dismiss_notification(uuid) from public;
grant execute on function public.dismiss_notification(uuid) to authenticated;

select id, email, is_active, is_blocked, blocked_reason
from public.profiles
order by updated_at desc nulls last
limit 20;
