-- Conferência: os valores abaixo devem bater com o painel.

-- 1) Total de guias: esperado 186973
select count(*) as total from adagri.gta;

-- 2) Período: esperado 2026-01-01 a 2026-09-29
select min(dataemissao), max(dataemissao) from adagri.gta;

-- 3) Guias por mês: esperado jan 18454, fev 17156, mar 20969, abr 19491, mai 20864, jun 23002, jul 23886, ago 22143, set 21008
select to_char(dataemissao,'MM') as mes, count(*) from adagri.gta group by 1 order by 1;

-- 4) Espécies: esperado bovino 88212, galinha 58526, camarão marinho 11011
select especie, count(*) from adagri.gta group by 1 order by 2 desc limit 5;

-- 5) Destino fora do Ceará: esperado 21484 (PI 6143, PE 3653, RN 2053)
select ufdestino, count(*) from adagri.gta where ufdestino <> 'CE' group by 1 order by 2 desc limit 3;

-- 6) Município de origem líder: esperado Quixadá 14407
select nomemunicipioorigem, count(*) from adagri.gta group by 1 order by 2 desc limit 1;

-- 7) Data da atualização (depois da carga): esperado emissao_max = 2026-09-29
select * from adagri.ultima_atualizacao;
