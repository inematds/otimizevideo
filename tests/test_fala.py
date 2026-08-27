from otv.util.fala import forma_fala


def test_termo_em_ingles_fica_em_ingles():
    # REGRA DO USUÁRIO (2026-08-27): termo em inglês pode ser falado em inglês -- nada de
    # reescrita fonética ("deplói", "dizáin"), que era o comportamento anterior.
    assert forma_fala("o deploy do design novo") == "o deploy do design novo"


def test_nome_proprio_em_ingles_intacto():
    t = forma_fala("A DeepMind lançou o AlphaFold e a OpenAI respondeu")
    assert t == "A DeepMind lançou o AlphaFold e a OpenAI respondeu"


def test_ia_vira_inteligencia_artificial_nunca_soletrada():
    # REGRA DO USUÁRIO: "IA" na tela é "inteligência artificial" na fala, sempre.
    assert forma_fala("a IA cresceu 50%") == "a inteligência artificial cresceu 50 por cento"
    assert forma_fala("as IAs de hoje") == "as inteligências artificiais de hoje"
    assert forma_fala("the AI revolution") == "the inteligência artificial revolution"
    assert "I A" not in forma_fala("a IA venceu")


def test_simbolo_expandido():
    assert "180 dólares" in forma_fala("investiu $180")


def test_url_vira_ponto_falado():
    assert forma_fala("acesse inema.club") == "acesse inema ponto club"


def test_sigla_que_viraria_palavra_continua_soletrada():
    # "DNA" lido como palavra vira "dina"; soletrar é sobre legibilidade, não sobre sotaque
    assert forma_fala("o DNA humano") == "o D N A humano"


def test_texto_sem_termo_nenhum_fica_igual():
    original = "os ratos voltaram a enxergar depois de quatro semanas"
    assert forma_fala(original) == original


def test_vazio_nao_quebra():
    assert forma_fala("") == "" and forma_fala(None) is None
