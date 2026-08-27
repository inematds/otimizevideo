from otv.util.fala import forma_fala


def test_termo_em_ingles_vira_grafia_fonetica():
    # o fonemizador do TTS lê a partir da grafia escrita -- "deploy" sai "dê-plô-i"
    assert forma_fala("o deploy do design novo") == "o deplói do dizáin novo"


def test_nome_proprio_de_ia_e_biotech():
    t = forma_fala("A DeepMind lançou o AlphaFold e a OpenAI respondeu")
    assert "DipMáind" in t and "AlfaFôld" in t and "Ôupen A I" in t


def test_sigla_e_simbolo_expandidos():
    assert forma_fala("a IA cresceu 50%") == "a I A cresceu 50 por cento"
    assert "180 dólares" in forma_fala("investiu $180")


def test_url_vira_ponto_falado():
    assert forma_fala("acesse inema.club") == "acesse inema ponto club"


def test_termo_composto_vence_o_isolado():
    # "machine learning" tem que casar antes de qualquer troca de palavra solta
    assert "mâchin lârning" in forma_fala("isso é machine learning aplicado")


def test_caixa_alta_preservada():
    assert "DIZÁIN" in forma_fala("é tudo DESIGN")


def test_texto_sem_termo_nenhum_fica_igual():
    original = "os ratos voltaram a enxergar depois de quatro semanas"
    assert forma_fala(original) == original


def test_vazio_nao_quebra():
    assert forma_fala("") == "" and forma_fala(None) is None
