"""Regras compartilhadas do rebanho (usadas pelo carregador e pelo gerador do painel)."""
import re
from datetime import date

GRUPOS = ["Bovinos", "Bubalinos", "Ovinos", "Caprinos", "Suínos", "Equídeos", "Aves", "Aquicultura", "Abelhas", "Outras espécies"]
UNIDADES = ["cabeças", "cabeças", "cabeças", "cabeças", "cabeças", "cabeças", "aves", "indivíduos", "colmeias", "animais"]

# código da coluna (sem 'rebanho_' e '_total')  ->  (nome, índice do grupo em GRUPOS)
ESPECIES = {
    "bovino": ("Bovino", 0),
    "bubalino": ("Bubalino", 1),
    "ovino": ("Ovino", 2),
    "caprino": ("Caprino", 3),
    "suino": ("Suíno", 4),
    "javali": ("Javali", 4),
    "cateto": ("Cateto", 4),
    "queixada": ("Queixada", 4),
    "equino": ("Equino", 5),
    "muar": ("Muar", 5),
    "asinino": ("Asinino", 5),
    "galinha": ("Galinha", 6),
    "peru": ("Peru", 6),
    "pato": ("Pato", 6),
    "ganso": ("Ganso", 6),
    "marreco": ("Marreco", 6),
    "faisao_chucar": ("Faisão/chucar", 6),
    "galinha_angola": ("Galinha-d'angola", 6),
    "codorna": ("Codorna", 6),
    "perdiz": ("Perdiz", 6),
    "ratitas": ("Ratitas (avestruz, ema)", 6),
    "aves_nao_destinadas_producao_carne_ovos": ("Aves ornamentais/silvestres", 6),
    "abelhas_apis_mellifera_colmeia_rainha": ("Abelha Apis mellifera (colmeias)", 8),
    "abelhas_nativa_sem_ferrao_colmeia_rainha": ("Abelha nativa sem ferrão (colmeias)", 8),
    "outras_especies": ("Outras espécies", 9),
    "capivara": ("Capivara", 9),
    "porquinho_da_india": ("Porquinho-da-índia", 9),
    "repteis_nao_hidrobios": ("Répteis não hidróbios", 9),
    "peixe_ornamental": ("Peixe ornamental", 7),
    "tilapia_nilo": ("Tilápia do Nilo", 7),
    "outras_tilapias": ("Outras tilápias", 7),
    "camarao_marinho": ("Camarão marinho", 7),
    "outros_crustaceos": ("Outros crustáceos", 7),
    "bagre_africano": ("Bagre africano", 7),
    "bagre_do_canal": ("Bagre do canal", 7),
    "camarao_gigante_malasia": ("Camarão gigante da Malásia", 7),
    "carpa_cabeca_grande": ("Carpa cabeça grande", 7),
    "carpa_capim": ("Carpa capim", 7),
    "carpa_comum_hungara": ("Carpa comum/húngara", 7),
    "carpa_prateada": ("Carpa prateada", 7),
    "curimata": ("Curimatã", 7),
    "jundia": ("Jundiá", 7),
    "matrincha": ("Matrinchã", 7),
    "mexilhao": ("Mexilhão", 7),
    "ostra_mangue": ("Ostra de mangue", 7),
    "ostra_pacifico": ("Ostra do Pacífico", 7),
    "outras_especies_animais_aquaticos": ("Outros animais aquáticos", 7),
    "outras_ostras": ("Outras ostras", 7),
    "outras_camaroes_marinhos": ("Outros camarões marinhos", 7),
    "outros_invertebrados_ornamentais": ("Outros invertebrados ornamentais", 7),
    "outros_moluscos": ("Outros moluscos", 7),
    "outros_peixes_nao_ornamentais": ("Outros peixes (não ornamentais)", 7),
    "outros_repteis_hidrobios": ("Outros répteis hidróbios", 7),
    "pacu_caranha": ("Pacu/caranha", 7),
    "piaucu": ("Piaçu", 7),
    "piau_verdadeiro": ("Piau verdadeiro", 7),
    "pintado_surubim": ("Pintado/surubim", 7),
    "pirapitinga": ("Pirapitinga", 7),
    "pirarucu": ("Pirarucu", 7),
    "ra_touro": ("Rã-touro", 7),
    "tambacu": ("Tambacu", 7),
    "tambaqui": ("Tambaqui", 7),
    "tartaruga_da_amazonia": ("Tartaruga-da-amazônia", 7),
    "truta": ("Truta", 7),
    "vieira": ("Vieira", 7),
}

# Tamanho do rebanho por propriedade (faixas) e limite de plausibilidade por grupo (acima = valor suspeito)
FAIXAS_LIM = [1, 10, 50, 100, 500, 1000, 10000]
FAIXAS_TXT = ["1 a 9", "10 a 49", "50 a 99", "100 a 499", "500 a 999", "1.000 a 9.999", "10.000 ou mais"]
LIMITE_GRUPO = {0: 100000, 1: 100000, 2: 100000, 3: 100000, 4: 100000, 5: 100000, 6: 1e+07, 7: 1e+10, 8: 10000, 9: 1e+06}


def codigo_coluna(col):
    """'rebanho_bovino_total' -> 'bovino'; 'rebanho_mexilhao_total.1' -> 'mexilhao'."""
    c = re.sub(r"\.\d+$", "", col)
    return re.sub(r"^rebanho_|_total$", "", c)


def data_do_nome(arquivo):
    """'..._01_10_2026.csv' ou '... 01.10.2026.csv' -> date(2026, 10, 1). Retorna None se não achar."""
    m = re.search(r"(\d{2})[._\-/ ](\d{2})[._\-/ ](\d{4})", arquivo)
    if not m:
        return None
    d, mth, a = map(int, m.groups())
    return date(a, mth, d)
