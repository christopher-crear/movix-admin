-- DIAGNÓSTICO COMPLETO DE SUPABASE PARA MOVIX
-- Es solo lectura: no crea, modifica ni elimina datos.
-- Ejecuta todo el archivo en Supabase > SQL Editor y descarga/copia el único
-- resultado JSON de la columna "reporte_movix".

WITH
schemas_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'esquema', n.nspname,
        'propietario', pg_get_userbyid(n.nspowner)
    ) ORDER BY n.nspname), '[]'::jsonb) AS data
    FROM pg_namespace n
    WHERE n.nspname NOT LIKE 'pg_%'
      AND n.nspname <> 'information_schema'
),
relations_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'esquema', n.nspname,
        'nombre', c.relname,
        'tipo', CASE c.relkind
            WHEN 'r' THEN 'tabla'
            WHEN 'p' THEN 'tabla_particionada'
            WHEN 'v' THEN 'vista'
            WHEN 'm' THEN 'vista_materializada'
            WHEN 'S' THEN 'secuencia'
            WHEN 'f' THEN 'tabla_externa'
            ELSE c.relkind::text
        END,
        'propietario', pg_get_userbyid(c.relowner),
        'rls_activo', c.relrowsecurity,
        'rls_forzado', c.relforcerowsecurity
    ) ORDER BY n.nspname, c.relname), '[]'::jsonb) AS data
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname NOT LIKE 'pg_%'
      AND n.nspname <> 'information_schema'
      AND c.relkind IN ('r','p','v','m','S','f')
),
columns_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'esquema', c.table_schema,
        'tabla', c.table_name,
        'posicion', c.ordinal_position,
        'columna', c.column_name,
        'tipo', c.data_type,
        'tipo_udt', c.udt_name,
        'permite_null', c.is_nullable,
        'valor_defecto', c.column_default,
        'identidad', c.is_identity,
        'generada', c.is_generated
    ) ORDER BY c.table_schema, c.table_name, c.ordinal_position), '[]'::jsonb) AS data
    FROM information_schema.columns c
    WHERE c.table_schema NOT LIKE 'pg_%'
      AND c.table_schema <> 'information_schema'
),
constraints_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'esquema', n.nspname,
        'tabla', rel.relname,
        'nombre', con.conname,
        'tipo', CASE con.contype
            WHEN 'p' THEN 'PRIMARY KEY'
            WHEN 'f' THEN 'FOREIGN KEY'
            WHEN 'u' THEN 'UNIQUE'
            WHEN 'c' THEN 'CHECK'
            WHEN 'x' THEN 'EXCLUDE'
            ELSE con.contype::text
        END,
        'definicion', pg_get_constraintdef(con.oid, true),
        'tabla_referenciada', CASE WHEN con.confrelid <> 0 THEN con.confrelid::regclass::text END
    ) ORDER BY n.nspname, rel.relname, con.conname), '[]'::jsonb) AS data
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_namespace n ON n.oid = rel.relnamespace
    WHERE n.nspname NOT LIKE 'pg_%'
      AND n.nspname <> 'information_schema'
),
indexes_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'esquema', schemaname,
        'tabla', tablename,
        'indice', indexname,
        'definicion', indexdef
    ) ORDER BY schemaname, tablename, indexname), '[]'::jsonb) AS data
    FROM pg_indexes
    WHERE schemaname NOT LIKE 'pg_%'
      AND schemaname <> 'information_schema'
),
triggers_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'esquema', event_object_schema,
        'tabla', event_object_table,
        'trigger', trigger_name,
        'evento', event_manipulation,
        'momento', action_timing,
        'accion', action_statement
    ) ORDER BY event_object_schema, event_object_table, trigger_name), '[]'::jsonb) AS data
    FROM information_schema.triggers
    WHERE event_object_schema NOT LIKE 'pg_%'
      AND event_object_schema <> 'information_schema'
),
policies_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'esquema', p.schemaname,
        'tabla', p.tablename,
        'politica', p.policyname,
        'permisiva', p.permissive,
        'roles', p.roles,
        'comando', p.cmd,
        'condicion_using', p.qual,
        'condicion_check', p.with_check
    ) ORDER BY p.schemaname, p.tablename, p.policyname), '[]'::jsonb) AS data
    FROM pg_policies p
),
grants_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'esquema', g.table_schema,
        'tabla', g.table_name,
        'beneficiario', g.grantee,
        'permiso', g.privilege_type,
        'otorgable', g.is_grantable
    ) ORDER BY g.table_schema, g.table_name, g.grantee, g.privilege_type), '[]'::jsonb) AS data
    FROM information_schema.role_table_grants g
    WHERE g.table_schema NOT LIKE 'pg_%'
      AND g.table_schema <> 'information_schema'
),
enums_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'esquema', n.nspname,
        'tipo', t.typname,
        'valores', e.valores
    ) ORDER BY n.nspname, t.typname), '[]'::jsonb) AS data
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    JOIN LATERAL (
        SELECT jsonb_agg(enumlabel ORDER BY enumsortorder) AS valores
        FROM pg_enum
        WHERE enumtypid = t.oid
    ) e ON e.valores IS NOT NULL
    WHERE n.nspname NOT LIKE 'pg_%'
),
storage_buckets_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'bucket', b.id,
        'nombre', b.name,
        'publico', b.public,
        'limite_bytes', b.file_size_limit,
        'tipos_permitidos', b.allowed_mime_types,
        'total_objetos', coalesce(o.total_objetos, 0)
    ) ORDER BY b.id), '[]'::jsonb) AS data
    FROM storage.buckets b
    LEFT JOIN (
        SELECT bucket_id, count(*) AS total_objetos
        FROM storage.objects
        GROUP BY bucket_id
    ) o ON o.bucket_id = b.id
),
profile_files AS (
    SELECT p.id,
           coalesce(to_jsonb(p)->>'role', '') AS rol,
           f.campo,
           f.valor
    FROM public.profiles p
    CROSS JOIN LATERAL (VALUES
        ('profile_photo_url',        nullif(to_jsonb(p)->>'profile_photo_url', '')),
        ('avatar_url',               nullif(to_jsonb(p)->>'avatar_url', '')),
        ('identification_photo_url', nullif(to_jsonb(p)->>'identification_photo_url', '')),
        ('license_photo_url',        nullif(to_jsonb(p)->>'license_photo_url', '')),
        ('registration_photo_url',   nullif(to_jsonb(p)->>'registration_photo_url', '')),
        ('insurance_photo_url',      nullif(to_jsonb(p)->>'insurance_photo_url', '')),
        ('vehicle_photo_url',        nullif(to_jsonb(p)->>'vehicle_photo_url', ''))
    ) AS f(campo, valor)
    WHERE f.valor IS NOT NULL
),
profile_files_limited AS (
    SELECT * FROM profile_files ORDER BY id, campo LIMIT 250
),
profile_files_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'perfil_id', pf.id,
        'rol', pf.rol,
        'campo', pf.campo,
        'valor_guardado', pf.valor,
        'formato_detectado', CASE
            WHEN pf.valor LIKE 'storage://%' THEN 'storage_uri'
            WHEN pf.valor LIKE 'https://%/storage/v1/object/public/%' THEN 'url_publica_supabase'
            WHEN pf.valor LIKE 'https://%/storage/v1/object/sign/%' THEN 'url_firmada_supabase'
            WHEN pf.valor LIKE 'https://%' THEN 'url_https_externa'
            WHEN pf.valor LIKE '/storage/v1/%' THEN 'ruta_relativa_api_storage'
            WHEN pf.valor LIKE '%/%' THEN 'ruta_objeto_sin_bucket_o_url'
            ELSE 'solo_nombre_archivo'
        END,
        'coincidencias_storage', coalesce(matches.objects, '[]'::jsonb)
    ) ORDER BY pf.id, pf.campo), '[]'::jsonb) AS data
    FROM profile_files_limited pf
    LEFT JOIN LATERAL (
        SELECT jsonb_agg(jsonb_build_object(
            'bucket', o.bucket_id,
            'objeto', o.name,
            'mime_type', o.metadata->>'mimetype',
            'tamano', o.metadata->>'size',
            'creado', o.created_at
        ) ORDER BY o.bucket_id, o.name) AS objects
        FROM storage.objects o
        WHERE pf.valor = o.name
           OR pf.valor = o.bucket_id || '/' || o.name
           OR pf.valor = 'storage://' || o.bucket_id || '/' || o.name
           OR split_part(pf.valor, '?', 1) LIKE '%/' || o.bucket_id || '/' || o.name
    ) matches ON true
),
storage_sample_info AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'bucket', sample.bucket_id,
        'objeto', sample.name,
        'mime_type', sample.metadata->>'mimetype',
        'tamano', sample.metadata->>'size',
        'creado', sample.created_at,
        'actualizado', sample.updated_at
    ) ORDER BY sample.bucket_id, sample.name), '[]'::jsonb) AS data
    FROM (
        SELECT bucket_id, name, metadata, created_at, updated_at
        FROM storage.objects
        ORDER BY created_at DESC NULLS LAST
        LIMIT 250
    ) sample
)
SELECT jsonb_pretty(jsonb_build_object(
    'generado_en', now(),
    'base_de_datos', current_database(),
    'usuario_ejecucion', current_user,
    'version_postgresql', version(),
    'esquemas', (SELECT data FROM schemas_info),
    'tablas_vistas_secuencias', (SELECT data FROM relations_info),
    'columnas', (SELECT data FROM columns_info),
    'restricciones_y_relaciones', (SELECT data FROM constraints_info),
    'indices', (SELECT data FROM indexes_info),
    'triggers', (SELECT data FROM triggers_info),
    'politicas_rls', (SELECT data FROM policies_info),
    'permisos', (SELECT data FROM grants_info),
    'tipos_enum', (SELECT data FROM enums_info),
    'buckets_storage', (SELECT data FROM storage_buckets_info),
    'archivos_guardados_en_profiles', (SELECT data FROM profile_files_info),
    'muestra_objetos_storage', (SELECT data FROM storage_sample_info)
)) AS reporte_movix;
