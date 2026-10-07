-- OPCIONAL (ocupa ~150 MB): rebanho linha a linha. O painel NÃO precisa disto; use sql/06_rebanho_resumo.sql.
-- Rode uma vez no SQL Editor. NÃO guarda CPF/CNPJ, nome, RG, e-mail, telefone nem endereço (LGPD).
-- Cada carga tem uma data de referência (a data do arquivo), então dá para guardar fotos de datas diferentes.

create table if not exists adagri.especie_rebanho (
  codigo text primary key,
  nome   text not null,
  grupo  text not null
);

create table if not exists adagri.propriedade (
  data_referencia    date   not null,
  propriedade_codigo bigint not null,
  municipio_codigo   bigint not null,
  municipio_nome     text,
  latitude           numeric(10,6),
  longitude          numeric(10,6),
  area_total         numeric(14,2),
  primary key (data_referencia, propriedade_codigo)
);
create index if not exists propriedade_municipio_idx on adagri.propriedade (data_referencia, municipio_codigo);

-- Todos os vínculos produtor x propriedade do cadastro (inclusive os sem rebanho)
create table if not exists adagri.produtor_propriedade (
  data_referencia    date   not null,
  produtor_codigo    bigint not null,
  propriedade_codigo bigint not null,
  primary key (data_referencia, produtor_codigo, propriedade_codigo)
);

-- Rebanho em formato "longo": só espécies com animais (quantidade > 0)
create table if not exists adagri.rebanho (
  data_referencia    date   not null,
  produtor_codigo    bigint not null,
  propriedade_codigo bigint not null,
  especie            text   not null,
  quantidade         bigint not null,
  primary key (data_referencia, produtor_codigo, propriedade_codigo, especie)
);
create index if not exists rebanho_especie_idx on adagri.rebanho (data_referencia, especie);

-- Histórico das cargas de rebanho (traz a data do arquivo)
create table if not exists adagri.carga_rebanho_log (
  id                bigint generated always as identity primary key,
  arquivo           text        not null,
  data_referencia   date        not null,
  carregado_em      timestamptz not null default now(),
  linhas_arquivo    bigint,
  propriedades      bigint,
  produtores        bigint,
  registros_rebanho bigint
);

alter table adagri.especie_rebanho      enable row level security;
alter table adagri.propriedade          enable row level security;
alter table adagri.produtor_propriedade enable row level security;
alter table adagri.rebanho              enable row level security;
alter table adagri.carga_rebanho_log    enable row level security;

create or replace view adagri.ultima_atualizacao_rebanho as
select arquivo, data_referencia, carregado_em, linhas_arquivo, propriedades, produtores, registros_rebanho
from adagri.carga_rebanho_log
order by carregado_em desc
limit 1;
grant select on adagri.ultima_atualizacao_rebanho to anon, authenticated;
