-- Conferência da carga do rebanho (data de referência 01/10/2026).
-- Rode no SQL Editor depois do carregar_rebanho.py e compare com os valores esperados.

-- 1) Totais do cadastro. Esperado: propriedades 261899, produtores 379697, vinculos 401138, 9 valores suspeitos
select * from adagri.rebanho_qualidade where data_referencia = '2026-10-01';

-- 2) Municípios no resumo. Esperado: 184
select count(*) as municipios, sum(propriedades) as propriedades
from adagri.rebanho_municipio where data_referencia = '2026-10-01';   -- 184 e 261899

-- 3) Totais por espécie (faixa 7 = todas). Esperado: bovino 3814043, ovino 3101164, suino 1372169
select especie, sum(quantidade) as total
from adagri.rebanho_cubo_especie
where data_referencia = '2026-10-01' and faixa = 7 and especie in ('bovino','ovino','suino')
group by especie order by total desc;

-- 4) Propriedades com bovinos. Esperado: 118115
select sum(propriedades) as propriedades_com_bovino
from adagri.rebanho_cubo_especie
where data_referencia = '2026-10-01' and faixa = 7 and especie = 'bovino';

-- 5) Municípios com mais bovinos. Esperado: QUIXERAMOBIM 126346, MORADA NOVA 121697, ACOPIARA 115091
select m.municipio_nome, sum(c.quantidade) as bovinos
from adagri.rebanho_cubo_especie c
join adagri.rebanho_municipio m
  on m.data_referencia = c.data_referencia and m.municipio_codigo = c.municipio_codigo
where c.data_referencia = '2026-10-01' and c.faixa = 7 and c.especie = 'bovino'
group by 1 order by 2 desc limit 3;

-- 6) Valores suspeitos (ficam fora dos totais). Esperado: 9, o maior é outros_crustaceos em Fortaleza
select s.especie, m.municipio_nome, s.quantidade, s.limite
from adagri.rebanho_suspeito s
left join adagri.rebanho_municipio m
  on m.data_referencia = s.data_referencia and m.municipio_codigo = s.municipio_codigo
where s.data_referencia = '2026-10-01' order by s.quantidade desc;

-- 7) Data do arquivo registrada. Esperado: data_referencia = 2026-10-01
select * from adagri.ultima_atualizacao_rebanho;

-- 8) Espaço ocupado pelas tabelas do schema adagri (para acompanhar o limite do plano)
select relname as tabela, pg_size_pretty(pg_total_relation_size(c.oid)) as tamanho
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'adagri' and c.relkind = 'r'
order by pg_total_relation_size(c.oid) desc;
