-- Histórico de cargas da planilha. Rode uma vez no SQL Editor.
create table if not exists adagri.carga_log (
  id               bigint generated always as identity primary key,
  arquivo          text        not null,
  arquivo_modificado_em timestamptz,          -- data de modificação do arquivo da planilha
  carregado_em     timestamptz not null default now(), -- quando a carga foi feita
  total_linhas     bigint      not null,
  emissao_min      date,
  emissao_max      date                          -- última GTA emitida nesta carga
);
alter table adagri.carga_log enable row level security;

-- Última atualização (uma linha), para o painel mostrar "Atualizado em".
-- Não contém dado pessoal, então pode ser exposta ao painel.
create or replace view adagri.ultima_atualizacao as
select arquivo, arquivo_modificado_em, carregado_em, total_linhas, emissao_min, emissao_max
from adagri.carga_log
order by carregado_em desc
limit 1;

grant select on adagri.ultima_atualizacao to anon, authenticated;
