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
    assert forma_fala("a IA cresceu 50%") == "a inteligência artificial cresceu cinquenta por cento"
    assert forma_fala("as IAs de hoje") == "as inteligências artificiais de hoje"
    assert forma_fala("the AI revolution") == "the inteligência artificial revolution"
    assert "I A" not in forma_fala("a IA venceu")


def test_simbolo_expandido():
    assert "cento e oitenta dólares" in forma_fala("investiu $180")
    # "US$" e "R$" precisam sair inteiros: a regra do "$" solto deixava o "US" para trás e
    # o TTS lia "USmil e quinhentos dólares" (achado de 2026-09-01)
    assert forma_fala("custa US$ 1.500") == "custa mil e quinhentos dólares"
    assert forma_fala("sai por R$ 250") == "sai por duzentos e cinquenta reais"


def test_numero_vira_extenso():
    """REGRA DO USUÁRIO (2026-09-01): número e valor não podem sair com pronúncia misturada.

    O TTS lia dígito cru com a fonética que bem entendesse — na mesma narração conviviam
    "92%", "2025" e "223 milhões", cada um dito de um jeito. Por extenso só há uma leitura.
    """
    assert forma_fala("92% de semelhança") == "noventa e dois por cento de semelhança"
    assert forma_fala("em abril de 2025") == "em abril de dois mil e vinte e cinco"
    assert forma_fala("mais de 223 milhões") == "mais de duzentos e vinte e três milhões"
    assert forma_fala("são 65 anos") == "são sessenta e cinco anos"


def test_milhar_e_decimal():
    assert forma_fala("custou 1.500 reais") == "custou mil e quinhentos reais"
    assert forma_fala("subiu 0,5 ponto") == "subiu zero vírgula cinco ponto"
    assert forma_fala("mede 1,75 metro") == "mede um vírgula setenta e cinco metro"


def test_numero_gigante_fica_como_esta():
    """Sequência longa não é número de fala (id, código): melhor deixar do que inventar."""
    t = forma_fala("o id 1234567890123456789 falhou")
    assert "1234567890123456789" in t


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
