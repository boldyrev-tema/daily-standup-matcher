import pymorphy3

_morph = pymorphy3.MorphAnalyzer()


def lemmatize(tokens: list[str]) -> list[str]:
    return [_morph.parse(token)[0].normal_form for token in tokens]
