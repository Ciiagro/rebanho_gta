-- Usuário só para as cargas e consultas do schema adagri.
-- Ele NÃO enxerga nem altera nenhuma outra tabela do seu banco, e NÃO muda a senha principal.
-- 1) Troque TROQUE_POR_UMA_SENHA por uma senha nova (só letras e números, 12+ caracteres) e rode no SQL Editor.
-- 2) No .env, use: SUPABASE_DB_URL=postgresql://carga_adagri.CODIGO_DO_PROJETO:SUA_NOVA_SENHA@HOST_DO_POOLER:5432/postgres
--    (copie o HOST em Connect > Session pooler; o CODIGO_DO_PROJETO é o mesmo que aparece no usuário postgres.CODIGO...)

create role carga_adagri login password 'TROQUE_POR_UMA_SENHA' bypassrls;

grant usage on schema adagri to carga_adagri;
grant select, insert, update, delete, truncate on all tables in schema adagri to carga_adagri;
grant usage, select on all sequences in schema adagri to carga_adagri;

-- vale também para tabelas criadas depois (por exemplo, futuras cargas)
alter default privileges in schema adagri grant select, insert, update, delete, truncate on tables to carga_adagri;
alter default privileges in schema adagri grant usage, select on sequences to carga_adagri;

-- Conferência: deve voltar uma linha com rolbypassrls = true e acesso_adagri = true
select rolname, rolbypassrls, has_schema_privilege('carga_adagri', 'adagri', 'USAGE') as acesso_adagri
from pg_roles where rolname = 'carga_adagri';

-- Tamanho do banco (acompanhe: o plano gratuito trava em 500 MB)
select pg_size_pretty(pg_database_size(current_database())) as tamanho_do_banco;
