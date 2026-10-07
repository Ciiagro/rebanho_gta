-- Rebanho: SÓ OS RESUMOS que o painel usa (alguns milhares de linhas, menos de 2 MB no banco).
-- Rode uma vez no SQL Editor. Sem CPF/CNPJ, nomes, contatos, endereços e sem código de produtor/propriedade.
-- Cada carga tem uma data de referência (a data do arquivo).

create table if not exists adagri.especie_rebanho (
  codigo text primary key,
  nome   text not null,
  grupo  text not null
);

-- Total por município x espécie x faixa de tamanho (faixa 7 = todas as faixas)
create table if not exists adagri.rebanho_cubo_especie (
  data_referencia  date     not null,
  municipio_codigo bigint   not null,
  especie          text     not null,
  faixa            smallint not null,
  propriedades     integer  not null,
  quantidade       bigint   not null,
  primary key (data_referencia, municipio_codigo, especie, faixa)
);

-- Idem por grupo de animais (0 bovinos, 1 bubalinos, 2 ovinos, 3 caprinos, 4 suínos, 5 equídeos, 6 aves, 7 aquicultura, 8 abelhas, 9 outras espécies)
create table if not exists adagri.rebanho_cubo_grupo (
  data_referencia  date     not null,
  municipio_codigo bigint   not null,
  grupo            smallint not null,
  faixa            smallint not null,
  propriedades     integer  not null,
  quantidade       bigint   not null,
  primary key (data_referencia, municipio_codigo, grupo, faixa)
);

create table if not exists adagri.rebanho_municipio (
  data_referencia             date    not null,
  municipio_codigo            bigint  not null,
  municipio_nome              text,
  propriedades                integer not null,
  produtores                  integer not null,
  propriedades_com_rebanho    integer not null,
  propriedades_com_coordenada integer not null,
  primary key (data_referencia, municipio_codigo)
);

-- Valores fora do limite de plausibilidade (ficam fora dos totais)
create table if not exists adagri.rebanho_suspeito (
  id               bigint generated always as identity primary key,
  data_referencia  date   not null,
  especie          text   not null,
  municipio_codigo bigint not null,
  quantidade       bigint not null,
  limite           bigint not null
);

create table if not exists adagri.rebanho_qualidade (
  data_referencia          date primary key,
  propriedades             integer not null,
  produtores               integer not null,
  vinculos                 integer not null,
  propriedades_com_rebanho integer not null,
  sem_coordenada           integer not null,
  coordenada_fora_ce       integer not null,
  valores_suspeitos        integer not null
);

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

alter table adagri.especie_rebanho     enable row level security;
alter table adagri.rebanho_cubo_especie enable row level security;
alter table adagri.rebanho_cubo_grupo   enable row level security;
alter table adagri.rebanho_municipio    enable row level security;
alter table adagri.rebanho_suspeito     enable row level security;
alter table adagri.rebanho_qualidade    enable row level security;
alter table adagri.carga_rebanho_log    enable row level security;

create or replace view adagri.ultima_atualizacao_rebanho as
select arquivo, data_referencia, carregado_em, linhas_arquivo, propriedades, produtores, registros_rebanho
from adagri.carga_rebanho_log
order by carregado_em desc
limit 1;
grant select on adagri.ultima_atualizacao_rebanho to anon, authenticated;
