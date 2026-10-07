# ADAGRI: banco no Supabase + painéis (GTAs e Rebanho)

## Arquivos
- `sql/` : 01_tabela_gta, 02_testes, 03_log_atualizacao, 04_rebanho (opcional), 05_testes_rebanho, 06_rebanho_resumo, 07_usuario_carga (segurança)  (rodar no SQL Editor do Supabase)
- GTAs: `carregar_gta.py`, `gerar_painel.py`, `painel_template.html`
- Rebanho: `carregar_rebanho.py`, `gerar_painel_rebanho.py`, `painel_rebanho_template.html`, `rebanho_comum.py`, `rebanho_cubos.py`
- Consulta local: `consultar.py`
- Comuns: `mapa_ce.json`, `testar_conexao.py`, `.env` (crie a partir de `.env.example`; NUNCA suba para o Git)

## Instalação (uma vez)
`pip install pandas numpy openpyxl psycopg2-binary python-dotenv`

## GTAs
1. SQL Editor: `sql/01_tabela_gta.sql` e depois `sql/03_log_atualizacao.sql`
2. `python carregar_gta.py "GTA CORRETO.xlsx"`   (planilha nova: acrescente `--limpar`)
3. `python gerar_painel.py`  -> `painel_gta_ceara.html`

## Rebanho (cadastro FAEC): só os resumos, bem leve no banco
O painel usa só totais por município, espécie e faixa de tamanho. Por isso o banco guarda só esses resumos
(cerca de 16 mil linhas, menos de 2 MB). O CSV completo fica no seu computador.
1. SQL Editor: rodar `sql/06_rebanho_resumo.sql` (uma vez)
2. Teste sem gravar: `python carregar_rebanho.py "Produtores_Propriedades_Rebanhos_-_FAEC_-_01_10_2026.csv" --teste`
3. Carga: `python carregar_rebanho.py "Produtores_Propriedades_Rebanhos_-_FAEC_-_01_10_2026.csv"`
   - A data de referência vem do nome do arquivo (01_10_2026 = 01/10/2026). Sem data no nome: `--data 2026-10-01`.
   - Repetir uma data já carregada: `--substituir`. Arquivo de outra data entra como nova foto, sem apagar a anterior.
4. Conferir: rodar `sql/05_testes_rebanho.sql` e comparar com os valores esperados (o último item mostra o espaço ocupado).
5. `python gerar_painel_rebanho.py`  -> `painel_rebanho_ceara.html`  (`--data AAAA-MM-DD` escolhe a foto)
- Não vão para o banco: CPF/CNPJ, nome, RG, e-mail, telefones, endereço, confrontantes, nem códigos de produtor/propriedade.
- Valores absurdos ficam fora dos totais e aparecem no quadro "Qualidade dos dados". Limites em `rebanho_comum.py` (LIMITE_GRUPO).
- Se aparecer "espécies novas no arquivo", acrescente nome e grupo em `rebanho_comum.py` (ESPECIES).
- Opcional: `sql/04_rebanho.sql` + `--detalhado` guardam também linha a linha (~150 MB). Só use se precisar consultar propriedade por propriedade.

## Consulta de produtor/propriedade e "quem mais movimenta" (cruza rebanho com GTAs)
Ferramenta LOCAL: roda só no seu computador (http://127.0.0.1:8765) e mostra dados pessoais. Nada vai para o banco, painel ou Git.
```
python consultar.py --rebanho "Produtores_Propriedades_Rebanhos_-_FAEC_-_01_10_2026.csv" --gta-xlsx "GTA CORRETO.xlsx"
```
- Sem `--gta-xlsx`, lê as GTAs do banco (precisa do `.env`). Sem `--rebanho`, procura o CSV na pasta.
- A 1ª vez leva alguns minutos; depois abre em segundos (cache em `.cache_consulta/`, que tem dados pessoais e já está no `.gitignore`).
- Arquivos novos: `python consultar.py --atualizar`.
- Aba "Buscar": nome, CPF/CNPJ ou código do produtor/propriedade. Mostra propriedades, rebanho, GTAs de saída e de entrada.
- Aba "Quem mais movimenta": ranking por propriedade ou produtor, por grupo, município e período, com a razão movimentado/rebanho (vermelho = movimentou mais do que o rebanho cadastrado). Botão "Baixar CSV".
- A ligação GTA x cadastro é feita pelo código da propriedade de origem (99,7% das GTAs casam) e pelo CPF/CNPJ.
- Em propriedade com vários produtores, a GTA não é atribuída a um produtor só (só pelo CPF da guia).
- Feche com Ctrl+C ao terminar.

## Painéis juntos
Coloque `painel_gta_ceara.html` e `painel_rebanho_ceara.html` na mesma pasta: os botões no topo levam de um para o outro.

## Subir para o Git (sem segredos)
O `.gitignore` já bloqueia `.env`, planilhas e CSV (dados pessoais) e os painéis gerados. Use repositório **privado**.
```
git init
git add .
git status        # CONFIRA: .env, .xlsx e .csv NÃO podem aparecer
git commit -m "Painéis ADAGRI"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git push -u origin main
```

## Segurança do banco
- `sql/07_usuario_carga.sql` cria o usuário `carga_adagri`, que só acessa o schema `adagri`. Use-o no `.env` em vez da senha principal.
- Não use `--detalhado` no rebanho (~150 MB). O plano gratuito deixa o banco somente leitura ao passar de 500 MB, e isso afeta todos os apps.
- `consultar.py` só lê, roda em 127.0.0.1 e mostra dados pessoais: feche com Ctrl+C ao terminar.
- Nunca suba `.env`, `.cache_consulta/`, planilhas ou CSV para o Git (o `.gitignore` já bloqueia).

## Aviso de cota do Supabase (grace period / erro 402)
- O aviso fala da COTA DA ORGANIZAÇÃO. Veja em Organization > Usage qual limite estourou (banco, egress, storage...).
- `sql/08_diagnostico_e_economia.sql`: mostra o que ocupa espaço e libera o que é seguro (índices extras das GTAs).
- Se o banco for o problema e a maior parte for de outros apps, as opções são: liberar espaço, plano Pro, ou gerar os painéis direto dos arquivos, sem banco.

## Grupos de animais (lista única)
Bovinos, Bubalinos, Ovinos, Caprinos, Suínos, Equídeos, Aves, Aquicultura, Abelhas, Outras espécies.
A lista fica em `rebanho_comum.py` e vale para os dois painéis e para a consulta.
Se você já tinha carregado o rebanho antes desta versão, recarregue os resumos:
`python carregar_rebanho.py "SEU_ARQUIVO.csv" --substituir`  e depois `python gerar_painel_rebanho.py`.
(O gerador avisa e para se os resumos do banco forem de uma versão antiga.)
Para o painel de GTAs basta rodar `python gerar_painel.py` de novo; não precisa recarregar as GTAs.

## Atalhos de duplo clique (Windows)
- `atualizar_rebanho.bat`: carrega o CSV de rebanho da pasta (com --substituir) e gera o painel de rebanho. Use quando chegar arquivo novo.
- `gerar_paineis.bat`: só gera os painéis de GTAs e de rebanho de novo, sem carregar nada.
