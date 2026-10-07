-- Diagnóstico de espaço e economia SEGURA. Rode no SQL Editor do projeto, um bloco por vez.
-- O aviso do Supabase fala de COTA da organização. Antes de apagar qualquer coisa, veja qual limite estourou
-- em Organization > Usage (banco, egress, storage...). Estes blocos só ajudam se for o tamanho do BANCO.

-- 1) Tamanho total do banco (plano gratuito: 500 MB)
select pg_size_pretty(pg_database_size(current_database())) as tamanho_do_banco;

-- 2) Quanto cada schema ocupa (mostra se o peso é do adagri ou dos seus outros aplicativos)
select n.nspname as schema, pg_size_pretty(sum(pg_total_relation_size(c.oid))) as tamanho
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind = 'r' and n.nspname not in ('pg_catalog', 'information_schema')
group by n.nspname
order by sum(pg_total_relation_size(c.oid)) desc;

-- 3) As 15 maiores tabelas do banco inteiro
select n.nspname as schema, c.relname as tabela, pg_size_pretty(pg_total_relation_size(c.oid)) as tamanho,
       pg_size_pretty(pg_relation_size(c.oid)) as so_dados, pg_size_pretty(pg_indexes_size(c.oid)) as indices
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind = 'r' and n.nspname not in ('pg_catalog', 'information_schema')
order by pg_total_relation_size(c.oid) desc limit 15;

-- 4) ECONOMIA SEGURA: índices extras da adagri.gta (os painéis e a consulta não precisam deles; a chave primária fica)
drop index if exists adagri.gta_dataemissao_idx;
drop index if exists adagri.gta_especie_idx;
drop index if exists adagri.gta_finalidade_idx;
drop index if exists adagri.gta_origem_idx;
drop index if exists adagri.gta_ufdestino_idx;

-- 5) SÓ SE você rodou o 04_rebanho.sql (rebanho linha a linha, ~150 MB) e não precisa dele, tire o "--" das linhas abaixo:
-- drop table if exists adagri.rebanho;
-- drop table if exists adagri.produtor_propriedade;
-- drop table if exists adagri.propriedade;

-- 6) Rode o bloco 1 de novo para ver quanto liberou.
-- Obs.: apagar LINHAS não diminui o arquivo na hora; apagar TABELAS ou ÍNDICES sim.
