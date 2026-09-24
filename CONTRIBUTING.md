# Guia de contribuição

Obrigado pelo interesse em contribuir com o Trajetória.

## Preparação

1. Consulte o README e a documentação de arquitetura.
2. Compile o núcleo C++ a partir da revisão que será modificada.
3. Execute `python run-tests.py` e registre o resultado.
4. Desenvolva a alteração em uma branch própria, com escopo definido.

## Critérios para alterações

- Preserve a execução do mesmo núcleo físico no terminal e na API.
- Mantenha unidades SI e documente convenções de tempo, ângulo e referencial.
- Não modifique massa, recuperação ou qualquer histórico durante avaliações intermediárias do integrador.
- Trate mudanças de dinâmica como eventos explícitos.
- Inclua testes independentes para alterações numéricas: soluções analíticas, invariantes ou referências verificáveis.
- Não relaxe tolerâncias de testes somente para ocultar uma regressão.
- Atualize contratos, exemplos e documentação quando modificar formatos de entrada ou saída.
- Utilize português do Brasil nas mensagens da interface e na documentação pública.
- Preserve o tema institucional branco e a navegação por teclado.

## Envio da contribuição

Descreva o problema, o comportamento resultante e a forma de verificação. Se houver limitação conhecida, explicite seu impacto. Identifique dados sintéticos e experimentais; não declare precisão física com base apenas em testes computacionais.

Antes do commit, execute `python scripts/verificar_publicacao.py` com as alterações preparadas no índice. Consulte [SECURITY.md](SECURITY.md). Não inclua compiladores, binários, arquivos `.env`, registros locais ou dados de terceiros sem autorização.
